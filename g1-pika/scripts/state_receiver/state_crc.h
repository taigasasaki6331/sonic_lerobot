// Receive-only CRC check. Algorithm follows pinned Unitree crc32_core;
// SDK/license provenance and native layout comparison: check_state_crc.py.
// DDS/CDR does not carry C padding: reconstruct native zero padding explicitly.
#ifndef G1_PIKA_STATE_CRC_H
#define G1_PIKA_STATE_CRC_H
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "State.h"
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "Pinned Unitree native CRC contract requires little endian"
#endif
#ifdef __cplusplus
#define G1_STATE_ASSERT static_assert
#else
#define G1_STATE_ASSERT _Static_assert
#endif
G1_STATE_ASSERT(sizeof(unitree_hg_msg_dds__LowState_) == 2092,"LowState native size changed");
G1_STATE_ASSERT(sizeof(unitree_hg_msg_dds__MotorState_) == 56,"MotorState native size changed");
G1_STATE_ASSERT(sizeof(unitree_hg_msg_dds__IMUState_) == 56,"IMUState native size changed");
G1_STATE_ASSERT(offsetof(unitree_hg_msg_dds__LowState_,crc) == 2088,"CRC offset changed");
#undef G1_STATE_ASSERT

static inline void canonical_lowstate(const unitree_hg_msg_dds__LowState_ *src,
                                      unitree_hg_msg_dds__LowState_ *dst) {
  memset(dst,0,sizeof(*dst));
#define COPY_FIELD(d,s,k) memcpy(&(d)->k,&(s)->k,sizeof((d)->k))
  COPY_FIELD(dst,src,version); COPY_FIELD(dst,src,mode_pr);
  COPY_FIELD(dst,src,mode_machine); COPY_FIELD(dst,src,tick);
  COPY_FIELD(&dst->imu_state,&src->imu_state,quaternion);
  COPY_FIELD(&dst->imu_state,&src->imu_state,gyroscope);
  COPY_FIELD(&dst->imu_state,&src->imu_state,accelerometer);
  COPY_FIELD(&dst->imu_state,&src->imu_state,rpy);
  COPY_FIELD(&dst->imu_state,&src->imu_state,temperature);
  for(int i=0;i<35;i++) {
    const unitree_hg_msg_dds__MotorState_ *s=&src->motor_state[i];
    unitree_hg_msg_dds__MotorState_ *d=&dst->motor_state[i];
    COPY_FIELD(d,s,mode); COPY_FIELD(d,s,q); COPY_FIELD(d,s,dq);
    COPY_FIELD(d,s,ddq); COPY_FIELD(d,s,tau_est); COPY_FIELD(d,s,temperature);
    COPY_FIELD(d,s,vol); COPY_FIELD(d,s,sensor); COPY_FIELD(d,s,motorstate);
    COPY_FIELD(d,s,reserve);
  }
  COPY_FIELD(dst,src,wireless_remote); COPY_FIELD(dst,src,reserve); COPY_FIELD(dst,src,crc);
#undef COPY_FIELD
}

static inline uint32_t lowstate_crc32(const unitree_hg_msg_dds__LowState_ *src) {
  unitree_hg_msg_dds__LowState_ canonical;
  canonical_lowstate(src,&canonical);
  uint32_t words[sizeof(canonical)/4-1];
  memcpy(words,&canonical,sizeof(words));
  uint32_t crc=0xffffffffu;
  for(size_t i=0;i<sizeof(words)/sizeof(words[0]);i++) {
    for(int bit=31;bit>=0;bit--)
      crc=(crc<<1)^((crc&0x80000000u)?0x04c11db7u:0u)^
          ((words[i]&(1u<<bit))?0x04c11db7u:0u);
  }
  return crc;
}
#endif
