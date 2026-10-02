// Read-only DDS application: no command types, DataWriter or SDK clients.
#include <dds/dds.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <net/if.h>
#include "State.h"
#include "sample_clock.h"
#include "state_crc.h"

static double now(void) {
  struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec + t.tv_nsec * 1e-9;
}
int main(int argc,char **argv) {
  int stream=0,verify_crc=0;
  for(int i=1;i<argc;i++) {
    if(strcmp(argv[i],"--stream")==0 && !stream) stream=1;
    else if(strcmp(argv[i],"--verify-crc")==0 && !verify_crc) verify_crc=1;
    else {fprintf(stderr,"Usage: receive_state [--stream] [--verify-crc]\n"); return 2;}
  }
  const char *iface=getenv("G1_STATE_INTERFACE");
  if(!iface || !*iface || strspn(iface,"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")!=strlen(iface) || !if_nametoindex(iface)) {
    fprintf(stderr,"G1_STATE_INTERFACE must name an existing network interface\n"); return 2;
  }
  char uri[512];
  snprintf(uri,sizeof(uri),"<CycloneDDS><Domain id=\"0\"><General><NetworkInterfaceAddress>%s</NetworkInterfaceAddress></General></Domain></CycloneDDS>",iface);
  setenv("CYCLONEDDS_URI",uri,1);
  dds_entity_t p=dds_create_participant(0,NULL,NULL);
  if(p<0) {fprintf(stderr,"participant error %d\n",p); return 2;}
  dds_entity_t t=dds_create_topic(p,&unitree_hg_msg_dds__LowState__desc,"rt/lowstate",NULL,NULL);
  dds_qos_t *qos=dds_create_qos();
  dds_qset_reliability(qos,DDS_RELIABILITY_BEST_EFFORT,DDS_SECS(1));
  dds_qset_history(qos,DDS_HISTORY_KEEP_LAST,1);
  dds_entity_t r=t<0?t:dds_create_reader(p,t,qos,NULL); dds_delete_qos(qos);
  if(r<0) {fprintf(stderr,"reader error %d\n",r); dds_delete(p); return 2;}
  unsigned count=0, invalid=0, changes=0; double start=now(),last_time=0,max_gap=0;
  unitree_hg_msg_dds__LowState_ last={0};
  double next_emit=0;
  while(now()-start<(stream?60:5)) {
    void *samples[1]={NULL}; dds_sample_info_t info[1];
    int n=dds_take(r,samples,info,1,1);
    if(n<0) {fprintf(stderr,"take error %d\n",n); dds_delete(p); return 2;}
    if(n>0) {
      if(info[0].valid_data) {
        unitree_hg_msg_dds__LowState_ *s=samples[0]; int valid=1;
        uint32_t calculated_crc=verify_crc?lowstate_crc32(s):0;
        if(verify_crc && calculated_crc!=s->crc) {
          fprintf(stderr,"LowState CRC mismatch: tick=%u received=%08x calculated=%08x; receiver stopped\n",
                  s->tick,s->crc,calculated_crc);
          dds_return_loan(r,samples,n); dds_delete(p); return 3;
        }
        double norm=0;
        for(int i=0;i<4;i++) norm+=s->imu_state.quaternion[i]*s->imu_state.quaternion[i];
        if(!isfinite(norm)||norm<.5||norm>1.5) valid=0;
        for(int i=0;i<35;i++) if(!isfinite(s->motor_state[i].q)||!isfinite(s->motor_state[i].dq)) valid=0;
        for(int i=0;i<3;i++) if(!isfinite(s->imu_state.gyroscope[i])) valid=0;
        if(valid) {
          double stamp=now();
          if(count && s->tick!=last.tick) changes++;
          if(count && stamp-last_time>max_gap) max_gap=stamp-last_time;
          last=*s; last_time=stamp; count++;
          if(stream && stamp>=next_emit) {
            printf("{\"receive_monotonic_s\":%.9f,\"tick\":%u,\"mode_pr\":%u,\"mode_machine\":%u,\"crc_verified\":%s,",
                   stamp,s->tick,s->mode_pr,s->mode_machine,verify_crc?"true":"false");
            if(verify_crc) printf("\"crc_received\":%u,\"crc_calculated\":%u,\"crc_native_size_bytes\":2092,",s->crc,calculated_crc);
            printf("\"q\":[");
            for(int i=0;i<35;i++) printf("%s%.9g",i?",":"",s->motor_state[i].q);
            printf("],\"dq\":[");
            for(int i=0;i<35;i++) printf("%s%.9g",i?",":"",s->motor_state[i].dq);
            printf("],\"raw_motor_state\":[");
            for(int i=0;i<35;i++) printf("%s%u",i?",":"",s->motor_state[i].motorstate);
            printf("],\"motor_modes\":[");
            for(int i=0;i<35;i++) printf("%s%u",i?",":"",s->motor_state[i].mode);
            printf("],\"quaternion\":[");
            for(int i=0;i<4;i++) printf("%s%.9g",i?",":"",s->imu_state.quaternion[i]);
            printf("],\"gyroscope\":[");
            for(int i=0;i<3;i++) printf("%s%.9g",i?",":"",s->imu_state.gyroscope[i]);
            printf("]}\n"); fflush(stdout);
            next_emit=next_sample_deadline(next_emit,stamp);
          }
        } else invalid++;
      }
      dds_return_loan(r,samples,n);
    }
    struct timespec pause={0,1000000}; nanosleep(&pause,NULL);
  }
  int passed=count>=20 && changes>=10 && invalid==0;
  if(stream) {dds_delete(p); return passed?0:1;}
  printf("{\"passed\":%s,\"scope\":\"G1_state_subscription_only\",\"motion_commands_sent\":false,\"crc_verified\":%s,\"samples\":%u,\"invalid\":%u,\"tick_changes\":%u,\"max_receive_gap_s\":%.6f,\"tick\":%u,\"mode_machine\":%u,\"q\":[",passed?"true":"false",verify_crc?"true":"false",count,invalid,changes,max_gap,last.tick,last.mode_machine);
  for(int i=0;i<35;i++) printf("%s%.9g",i?",":"",last.motor_state[i].q);
  printf("],\"quaternion\":[");
  for(int i=0;i<4;i++) printf("%s%.9g",i?",":"",last.imu_state.quaternion[i]);
  printf("]}\n");
  dds_delete(p); return passed?0:1;
}
