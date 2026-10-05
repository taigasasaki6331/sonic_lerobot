// SDK-free owner protocol checks; fake permissions/observations are artificial.
#include "body_owner_lifecycle.hpp"
#include <iostream>
#include <memory>
using namespace g1_pika;
void check(bool ok) {if(!ok) throw std::runtime_error("Owner assertion failed");}
template<class F> void rejects(F f) {bool failed=false; try {f();} catch(const std::exception&) {failed=true;} check(failed);}
Joints fill(double v) {Joints j; j.fill(v); return j;}
struct Fake:Transport {
  bool memory=true,fail_query=false,keep_mode=false,fail_open=false,fail_write=false,throw_write=false,fail_stop=false;
  int release_status=0,restore_status=0; std::string mode="previous-controller";
  std::vector<std::string> calls;
  bool record_only() const override {return memory;}
  void open_query_channel() override {calls.push_back("query_open");}
  ModeReply query_mode() override {calls.push_back("query"); return {fail_query?1:0,"fake",mode};}
  int release_mode() override {calls.push_back("release"); if(!keep_mode && !release_status) mode.clear(); return release_status;}
  void open_body_publisher() override {calls.push_back("open"); if(fail_open) throw std::runtime_error("Partial open");}
  bool write_body(uint8_t,const MotorValues& m) override {
    bool stop=m.kp[0]==0; calls.push_back(stop?"stop":"write");
    if(!stop && throw_write) throw std::runtime_error("Write exception");
    return stop?!fail_stop:!fail_write;
  }
  void close_body_publisher() override {calls.push_back("close");}
  int select_mode(const std::string& name) override {check(name=="previous-controller"); calls.push_back("restore"); return restore_status;}
  size_t count(const std::string& s) const {return std::count(calls.begin(),calls.end(),s);}
};
struct Rig {
  Fake transport; BodyIoAdapter adapter; BodyOwnerLifecycle owner;
  Rig(AdapterScope scope=AdapterScope::record_only,TrialContract contract={})
    :adapter(transport,contract,fill(-1),fill(1),scope),owner(adapter,fill(2)) {}
  static LocalEvidence local() {return {true,0,5,.01};}
  void start() {owner.initialize(); owner.acquire(local); owner.begin_initialization();}
  bool ref(WriterReference::Phase p) {
    WriterReference r; r.phase=p; r.motors.kp=fill(10); r.motors.kd=fill(1); return owner.publish_reference(local(),r);
  }
  void stop() {check(owner.stop_candidate(false).sdk_write_accepted); check(adapter.stop_latched());}
};
int main() {
  int cases=0;
  {Rig r; check(r.transport.calls.empty()); r.owner.initialize(); check(!r.transport.count("release")); r.owner.close(); ++cases;}
  {Rig r; r.start(); check(r.ref(WriterReference::Phase::initializing)); check(r.ref(WriterReference::Phase::settling));
   check(r.ref(WriterReference::Phase::ready)); check(r.ref(WriterReference::Phase::tracking)); r.stop();
   r.owner.recover(AdapterScope::record_only,"ARTIFICIAL stop",Rig::local);
   check(r.owner.snapshot().recovery_acknowledged); check(r.transport.calls[r.transport.calls.size()-2]=="close");
   rejects([&]{r.owner.recover(AdapterScope::record_only,"again",Rig::local);});
   rejects([&]{r.owner.initialize();}); rejects([&]{r.ref(WriterReference::Phase::tracking);}); r.owner.close(); ++cases;}
  {Rig r; r.start(); r.stop(); r.owner.close(); check(!r.transport.count("restore")); ++cases;}
  {Rig r; r.transport.memory=false; rejects([&]{r.owner.initialize();}); check(r.transport.calls.empty()); ++cases;}
  {Rig r; r.transport.fail_query=true; rejects([&]{r.owner.initialize();}); check(!r.transport.count("release")); ++cases;}
  {Rig r; r.transport.release_status=1; r.owner.initialize(); rejects([&]{r.owner.acquire(Rig::local);});
   rejects([&]{r.owner.acquire(Rig::local);}); check(r.transport.count("release")==1 && !r.transport.count("open")); ++cases;}
  {Rig r; r.transport.keep_mode=true; r.owner.initialize(); rejects([&]{r.owner.acquire(Rig::local);}); check(!r.transport.count("open")); ++cases;}
  {Rig r; r.owner.initialize(); int reads=0; rejects([&]{r.owner.acquire([&]{if(++reads==3) throw std::runtime_error("Cancelled"); return Rig::local();});});
   check(r.transport.count("release")==1 && !r.transport.count("open"));
   Rig before; before.owner.initialize(); reads=0;
   rejects([&]{before.owner.acquire([&]{if(++reads==2) throw std::runtime_error("Cancelled during query"); return Rig::local();});});
   check(!before.transport.count("release") && !before.transport.count("open")); ++cases;}
  {Rig r; r.transport.fail_open=true; r.owner.initialize(); rejects([&]{r.owner.acquire(Rig::local);});
   rejects([&]{r.owner.stop_candidate(false);}); r.owner.close(); check(!r.transport.count("write") && r.transport.count("close")==1); ++cases;}
  {Rig r; r.start(); r.transport.fail_write=true; check(!r.ref(WriterReference::Phase::initializing));
   check(r.owner.snapshot().fault_latched); r.stop(); rejects([&]{r.owner.stop_candidate(false);}); check(r.transport.count("stop")==1); ++cases;}
  {Rig r; r.start(); r.transport.throw_write=true; rejects([&]{r.ref(WriterReference::Phase::initializing);});
   r.stop(); check(r.owner.snapshot().fault_latched); ++cases;}
  {Rig r; r.start(); r.transport.fail_stop=true; check(!r.owner.stop_candidate(false).sdk_write_accepted);
   r.owner.close(); check(r.owner.snapshot().fault_latched && !r.transport.count("restore")); ++cases;}
  {Rig r; r.start(); rejects([&]{r.owner.stop_candidate(true);});
   rejects([&]{r.owner.recover(AdapterScope::record_only,"ARTIFICIAL stop",Rig::local);});
   check(!r.transport.count("stop") && !r.transport.count("restore")); r.owner.close(); ++cases;}
  {Rig r; r.start(); r.stop(); r.transport.restore_status=1;
   rejects([&]{r.owner.recover(AdapterScope::record_only,"ARTIFICIAL stop",Rig::local);});
   rejects([&]{r.owner.recover(AdapterScope::record_only,"retry",Rig::local);}); check(r.transport.count("restore")==1); r.owner.close(); ++cases;}
  {Rig r; r.owner.initialize(); bool rejected=false; std::thread t([&]{try {r.owner.acquire(Rig::local);} catch(...) {rejected=true;}}); t.join();
   check(rejected && !r.transport.count("release")); r.owner.close(); ++cases;}
  {Rig r(AdapterScope::physical_trial,{true,true,true,true,false}); r.transport.memory=false; r.start();
   rejects([&]{r.ref(WriterReference::Phase::ready);}); rejects([&]{r.owner.confirm_initial_pose(AdapterScope::record_only);});
   r.owner.confirm_initial_pose(AdapterScope::physical_trial); check(r.ref(WriterReference::Phase::tracking)); r.stop();
   rejects([&]{r.owner.recover(AdapterScope::record_only,"diagnostic ACK",Rig::local);}); check(!r.transport.count("restore")); r.owner.close(); ++cases;}
  {Rig r; r.start(); MotorValues m; m.q=fill(2); rejects([&]{r.owner.publish(Rig::local(),m);}); check(!r.transport.count("write")); r.stop(); ++cases;}
  {Rig r; r.start(); check(r.ref(WriterReference::Phase::ready)); rejects([&]{r.ref(WriterReference::Phase::initializing);}); r.stop();
   rejects([&]{r.owner.recover(AdapterScope::record_only,"ARTIFICIAL stop",[]{return LocalEvidence{true,0,5,.101};});});
   check(!r.transport.count("restore")); r.owner.close(); ++cases;}
  std::cout<<"{\"fake_owner_checks\":"<<cases<<",\"robot_commands_sent\":false,\"physical_stop_confirmed\":false}\n";
}
