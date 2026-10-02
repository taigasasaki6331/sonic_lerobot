// SIMULATION ONLY. Reuses BodyIoAdapter/WriterKernel + actual fixed LowCmd
// DATA classes, but NO SDK client, DDS participant, publisher, sockets or IO.
// All ownership/CRC/health/stop evidence below is explicitly SIMULATED.
#include "body_writer.hpp"
#include "LowCmd_data.hpp"
#include "CRC_data.h"
#include <cstring>
#include <new>
#include <type_traits>
using namespace g1_pika;
using Command=unitree_hg::msg::dds_::LowCmd_;
static_assert(sizeof(Command)==1004 && std::is_trivially_copyable<Command>::value);
static_assert(__BYTE_ORDER__==__ORDER_LITTLE_ENDIAN__);
static thread_local std::string last_error;

struct SimulationTransport final:Transport {
  std::array<unsigned char,1004> packet{};
  unsigned writes=0,releases=0,restores=0;
  bool opened=false; std::string mode="simulation-controller";
  void open_query_channel() override {} // NO network.
  ModeReply query_mode() override {return {0,"simulation",mode};}
  int release_mode() override {mode.clear(); releases++; return 0;}
  void open_body_publisher() override {opened=true;} // Memory buffer ONLY.
  bool write_body(uint8_t machine,const MotorValues& values) override {
    if(!opened) throw std::logic_error("Simulation buffer closed");
    alignas(Command) std::array<unsigned char,1004> storage{};
    auto* command=new(storage.data()) Command;
    command->mode_pr()=0; command->mode_machine()=machine;
    for(size_t i=0;i<29;i++) {
      auto& m=command->motor_cmd()[i]; m.mode()=1;
      m.q()=static_cast<float>(values.q[i]); m.dq()=static_cast<float>(values.dq[i]);
      m.tau()=static_cast<float>(values.tau[i]); m.kp()=static_cast<float>(values.kp[i]); m.kd()=static_cast<float>(values.kd[i]);
    }
    if(reinterpret_cast<unsigned char*>(&command->crc())-storage.data()!=1000)
      throw std::logic_error("LowCmd CRC layout changed");
    std::array<uint32_t,251> words{}; std::memcpy(words.data(),storage.data(),1004);
    command->crc()=crc32_core(words.data(),250); packet=storage; command->~Command(); writes++; return true;
  }
  void close_body_publisher() override {opened=false;}
  int select_mode(const std::string& name) override {mode=name; restores++; return 0;}
};
struct SimulationGateway {
  SimulationTransport transport;
  BodyIoAdapter adapter;
  WriterKernel kernel;
  WriterSnapshot input;
  Joints kd;
  bool begun=false,stopped=false;
  uint64_t references=0,ticks=0;
  SimulationGateway(Joints lower,Joints upper,Joints kp,Joints damping,Joints initial)
    // ARTIFICIAL simulation contract. Cannot instantiate a hardware transport.
    :adapter(transport,{true,true,true,true,false},lower,upper),kd(damping) {
    WriterReference ref; ref.session="simulation-only"; ref.motors.q=initial; ref.motors.kp=kp; ref.motors.kd=kd;
    for(size_t i=0;i<29;i++) if(!std::isfinite(kp[i]) || kp[i]<=0 || !std::isfinite(kd[i]) || kd[i]<=0 ||
      !std::isfinite(initial[i]) || initial[i]<lower[i] || initial[i]>upper[i])
      throw std::invalid_argument("Invalid simulation motor profile");
    input.reference=ref;
  }
  static WriterTime stamp(double seconds) {
    if(!std::isfinite(seconds) || seconds<0 || seconds>3600) throw std::invalid_argument("Simulation clock invalid");
    return WriterTime(std::chrono::nanoseconds(std::llround(seconds*1e9)));
  }
  void begin() {
    if(begun || stopped) throw std::logic_error("Simulation gateway already started/stopped");
    LocalEvidence artificial{true,0,5,0}; adapter.open_query_channel();
    if(adapter.release_once(artificial)!=0) throw std::runtime_error("Simulation release failed");
    adapter.open_publisher(artificial); input.local_phase_validated=true; begun=true;
  }
  void reference(double now,uint64_t sequence,const double* q) {
    if(!begun || stopped || sequence!=references) throw std::logic_error("Simulation reference phase/sequence");
    auto time=stamp(now);
    if(references && time<=input.reference->received_at) throw std::logic_error("Simulation reference clock reversed");
    for(size_t i=0;i<29;i++) if(!std::isfinite(q[i])) throw std::invalid_argument("Nonfinite simulation target");
    input.reference->received_at=time; input.reference->sequence=sequence;
    std::copy(q,q+29,input.reference->motors.q.begin()); references++;
  }
  void tick(double now,unsigned char* out) {
    if(!begun || stopped || !references) throw std::logic_error("Simulation gateway not running");
    WriterBody body; body.received_at=stamp(now); body.tick=static_cast<uint32_t>(++ticks);
    body.crc_verified=true; body.mode_machine=5; body.motor_health_checked=true;
    // Synthetic simulation evidence only, NEVER a physical LowState claim.
    input.body=body;
    auto decision=kernel.poll(body.received_at,input);
    if(decision.action!=WriterAction::publish) throw std::logic_error("Simulation writer deadline/phase: "+decision.reason);
    if(!adapter.publish(decision.evidence,input.reference->motors)) throw std::runtime_error("Simulation write failed");
    std::memcpy(out,transport.packet.data(),1004);
  }
  void stop() {
    if(stopped) return;
    stopped=true;
    if(!begun) return;
    auto result=adapter.damping_candidate(kd);
    if(!result.sdk_write_accepted) throw std::runtime_error("Simulation stop failed");
    if(adapter.restore_original_mode("SIMULATED_STOP_NOT_PHYSICAL_CONFIRMATION")!=0)
      throw std::runtime_error("Simulation restore failed");
  }
};
static Joints values(const double* p) {Joints v; std::copy(p,p+29,v.begin()); return v;}
template<class Fn> int call(Fn fn) {try {fn(); return 0;} catch(const std::exception& e) {last_error=e.what(); return -1;}}
extern "C" {
const char* g1_pika_sim_error() {return last_error.c_str();}
void* g1_pika_sim_create(const double* lower,const double* upper,const double* kp,const double* kd,const double* initial) {
  try {return new SimulationGateway(values(lower),values(upper),values(kp),values(kd),values(initial));}
  catch(const std::exception& e) {last_error=e.what(); return nullptr;}
}
int g1_pika_sim_begin(void* h) {return call([&]{static_cast<SimulationGateway*>(h)->begin();});}
int g1_pika_sim_reference(void* h,double now,uint64_t seq,const double* q) {
  return call([&]{static_cast<SimulationGateway*>(h)->reference(now,seq,q);});
}
int g1_pika_sim_tick(void* h,double now,unsigned char* out) {
  return call([&]{static_cast<SimulationGateway*>(h)->tick(now,out);});
}
int g1_pika_sim_stop(void* h) {return call([&]{static_cast<SimulationGateway*>(h)->stop();});}
int g1_pika_sim_counts(void* h,uint64_t* out) {
  auto& g=*static_cast<SimulationGateway*>(h);
  out[0]=g.references; out[1]=g.ticks; out[2]=g.transport.writes; out[3]=g.transport.releases; out[4]=g.transport.restores; return 0;
}
void g1_pika_sim_delete(void* h) {delete static_cast<SimulationGateway*>(h);}
}
