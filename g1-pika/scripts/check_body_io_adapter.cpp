// Fake transport only; no SDK, DDS, robot, sockets or physical confirmation.
#include "body_io_adapter.hpp"
#include <cassert>
#include <iostream>
#include <vector>
using namespace g1_pika;
struct Fake:Transport {
  std::vector<std::string> calls;
  std::string mode="original-controller";
  int query_status=0,release_status=0;
  bool write_result=true;
  MotorValues last;
  uint8_t machine=0;
  void open_query_channel() override {calls.push_back("query-open");}
  ModeReply query_mode() override {calls.push_back("query"); return {query_status,"fake",mode};}
  int release_mode() override {calls.push_back("release"); if(!release_status) mode.clear(); return release_status;}
  void open_body_publisher() override {calls.push_back("publisher-open");}
  bool write_body(uint8_t value,const MotorValues& m) override {calls.push_back("write"); machine=value; last=m; return write_result;}
  void close_body_publisher() override {calls.push_back("publisher-close");}
  int select_mode(const std::string& name) override {calls.push_back("select:"+name); return 0;}
};
template<class Fn> void rejected(Fn fn) {bool caught=false; try {fn();} catch(const std::exception&) {caught=true;} assert(caught);}
Joints filled(double value) {Joints r; r.fill(value); return r;}
TrialContract test_contract() {return {true,true,true,true,false};} // ARTIFICIAL, not operator evidence.
LocalEvidence local() {return {true,0,5,.02};}
MotorValues motors() {MotorValues r; r.kp.fill(10); r.kd.fill(1); return r;}
void armed(BodyIoAdapter& a) {a.open_query_channel(); assert(a.release_once(local())==0); a.open_publisher(local());}

int main() {
  unsigned tests=0;
  {Fake f; {BodyIoAdapter a(f,{},filled(-1),filled(1)); assert(f.calls.empty());
    rejected([&]{a.open_query_channel();}); rejected([&]{a.release_once(local());});
    rejected([&]{a.open_publisher(local());}); rejected([&]{a.publish(local(),motors());});
    rejected([&]{a.damping_candidate(filled(1));});} assert(f.calls.empty()); tests++;}
  for(int missing=0;missing<5;missing++) {
    Fake f; auto contract=test_contract();
    if(missing==0) contract.hardware_output_enabled=false;
    if(missing==1) contract.explicit_trial_permission=false;
    if(missing==2) contract.support_and_stop_procedure_confirmed=false;
    if(missing==3) contract.actual_configuration_confirmed=false;
    if(missing==4) contract.diagnostic_only=true;
    BodyIoAdapter a(f,contract,filled(-1),filled(1)); rejected([&]{a.open_query_channel();});
    assert(f.calls.empty()); tests++;
  }
  {Fake f; BodyIoAdapter a(f,test_contract(),filled(-1),filled(1)); a.open_query_channel();
    assert(a.query_mode().name=="original-controller");
    assert((f.calls==std::vector<std::string>{"query-open","query"})); tests++;}
  {Fake f; BodyIoAdapter a(f,test_contract(),filled(-1),filled(1)); armed(a);
    assert(a.publish(local(),motors())); assert(f.machine==5);
    auto stop=a.damping_candidate(filled(2)); assert(a.stop_latched());
    assert(stop.sdk_write_accepted && !stop.physical_stop_confirmed);
    for(int i=0;i<29;i++) assert(f.last.q[i]==0 && f.last.dq[i]==0 && f.last.tau[i]==0 && f.last.kp[i]==0 && f.last.kd[i]==2);
    size_t count=f.calls.size(); rejected([&]{a.publish(local(),motors());});
    rejected([&]{a.restore_original_mode("");}); assert(f.calls.size()==count);
    assert(a.restore_original_mode("ARTIFICIAL_TEST_CONFIRMATION_NOT_PHYSICAL")==0);
    assert(f.calls[f.calls.size()-2]=="publisher-close"); assert(f.calls.back()=="select:original-controller"); tests++;}
  {Fake f; f.query_status=1; BodyIoAdapter a(f,test_contract(),filled(-1),filled(1)); a.open_query_channel();
    rejected([&]{a.release_once(local());}); assert(f.calls.back()=="query");
    size_t count=f.calls.size(); rejected([&]{a.open_publisher(local());}); assert(f.calls.size()==count); tests++;}
  {Fake f; f.release_status=1; BodyIoAdapter a(f,test_contract(),filled(-1),filled(1)); a.open_query_channel();
    assert(a.release_once(local())==1); size_t count=f.calls.size();
    rejected([&]{a.open_publisher(local());}); assert(f.calls.size()==count); tests++;}
  {Fake f; BodyIoAdapter a(f,test_contract(),filled(-1),filled(1)); a.open_query_channel();
    assert(a.release_once(local())==0); size_t count=f.calls.size();
    rejected([&]{a.release_once(local());}); assert(f.calls.size()==count); tests++;}
  for(int invalid=0;invalid<4;invalid++) {
    Fake f; BodyIoAdapter a(f,test_contract(),filled(-1),filled(1)); armed(a);
    LocalEvidence e=local();
    if(invalid==0) e.age_s=.101;
    if(invalid==1) e.crc_verified=false;
    if(invalid==2) e.mode_machine=6;
    if(invalid==3) e.mode_pr=1;
    size_t count=f.calls.size(); rejected([&]{a.publish(e,motors());}); assert(f.calls.size()==count); tests++;
    if(invalid==2 || invalid==3) {
      rejected([&]{a.damping_candidate(filled(2));}); assert(f.calls.size()==count);
      rejected([&]{a.restore_original_mode("ARTIFICIAL_CONFIRMATION");}); assert(f.calls.size()==count);
    }
  }
  {Fake f; BodyIoAdapter a(f,test_contract(),filled(-1),filled(1)); armed(a); auto m=motors(); m.q[0]=1.01;
    size_t count=f.calls.size(); rejected([&]{a.publish(local(),m);}); assert(f.calls.size()==count); tests++;}
  {Fake f; BodyIoAdapter a(f,test_contract(),filled(-1),filled(1)); armed(a); f.write_result=false;
    assert(!a.publish(local(),motors())); rejected([&]{a.publish(local(),motors());});
    auto stop=a.damping_candidate(filled(2)); assert(!stop.sdk_write_accepted && !stop.physical_stop_confirmed); tests++;}
  {Fake f; BodyIoAdapter a(f,test_contract(),filled(-1),filled(1)); armed(a);
    size_t count=f.calls.size(); rejected([&]{a.damping_candidate(filled(0));});
    assert(a.stop_latched() && f.calls.size()==count); rejected([&]{a.publish(local(),motors());}); tests++;}
  {Fake f; BodyIoAdapter a(f,test_contract(),filled(-1),filled(1)); armed(a);
    size_t count=f.calls.size(); a.latch_body_identity_loss(); assert(a.stop_latched());
    rejected([&]{a.publish(local(),motors());}); rejected([&]{a.damping_candidate(filled(2));});
    rejected([&]{a.restore_original_mode("ARTIFICIAL_CONFIRMATION");}); assert(f.calls.size()==count); tests++;}
  std::cout<<"{\"fake_transport_checks\":"<<tests<<",\"robot_commands_sent\":false,\"physical_stop_confirmed\":false}\n";
}
