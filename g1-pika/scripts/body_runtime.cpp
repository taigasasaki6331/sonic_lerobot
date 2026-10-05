// RECORD-ONLY native owner: same-host mailbox -> actual writer -> native memory.
// No SDK library/client/publisher can be selected by this exported API.
#include "body_owner_lifecycle.hpp"
#include "LowCmd_data.hpp"
#include "CRC_data.h"
#include <atomic>
#include <cstring>
#include <new>
#include <thread>
#include <type_traits>
#include <sstream>
using namespace g1_pika;
namespace {
thread_local std::string error;
using Command=unitree_hg::msg::dds_::LowCmd_;
Joints joints(const double* p) {
  if(!p) throw std::invalid_argument("Null motor vector");
  Joints result; std::copy(p,p+29,result.begin()); return result;
}
WriterTime stamp(double seconds) {
  if(!std::isfinite(seconds) || seconds<0) throw std::invalid_argument("Invalid local monotonic timestamp");
  return WriterTime(std::chrono::duration_cast<WriterClock::duration>(std::chrono::duration<double>(seconds)));
}
// Explicitly artificial ownership. No physical contract is promoted here.
class MemoryTransport final:public Transport {
  std::mutex mutex_; std::array<unsigned char,1004> latest_{};
  uint64_t publications_=0; bool query_=false,publisher_=false;
  std::string mode_="record-only-controller";
public:
  bool record_only() const override {return true;}
  void open_query_channel() override {query_=true;}
  ModeReply query_mode() override {
    if(!query_) throw std::logic_error("Record query not open");
    return {0,"record-only",mode_};
  }
  int release_mode() override {mode_.clear(); return 0;}
  void open_body_publisher() override {publisher_=true;}
  bool write_body(uint8_t machine,const MotorValues& m) override {
    if(!publisher_) throw std::logic_error("Record output not open");
    static_assert(sizeof(Command)==1004 && std::is_trivially_copyable<Command>::value);
    alignas(Command) std::array<unsigned char,1004> backing{};
    auto* c=new(backing.data()) Command; c->mode_pr()=0; c->mode_machine()=machine;
    for(size_t i=0;i<29;i++) {
      auto& v=c->motor_cmd()[i]; v.mode()=1; v.q()=m.q[i]; v.dq()=m.dq[i];
      v.tau()=m.tau[i]; v.kp()=m.kp[i]; v.kd()=m.kd[i];
    }
    std::array<uint32_t,251> words{}; std::memcpy(words.data(),c,1004);
    c->crc()=crc32_core(words.data(),250);
    std::lock_guard<std::mutex> lock(mutex_); std::memcpy(latest_.data(),c,1004);
    c->~Command(); ++publications_; return true;
  }
  void close_body_publisher() override {publisher_=false;}
  int select_mode(const std::string& name) override {mode_=name; return 0;}
  uint64_t copy(unsigned char* out) {
    std::lock_guard<std::mutex> lock(mutex_); std::memcpy(out,latest_.data(),1004); return publications_;
  }
};
class RecordRuntime {
public:
  WriterMailbox mailbox; MemoryTransport transport; BodyIoAdapter adapter; BodyOwnerLifecycle lifecycle;
  std::thread owner; std::atomic<bool> done{false},exited{false}; WriterRunReport result;
  std::mutex command_mutex; std::condition_variable command_wake;
  bool finish_requested=false,recover_requested=false,recovery_done=false;
  std::string recovery_record,recovery_error,shutdown_error;
  bool started=false;
  RecordRuntime(std::string session,Joints low,Joints high,Joints velocity,Joints kd)
    :mailbox(std::move(session),low,high,velocity),
     adapter(transport,{},low,high,AdapterScope::record_only),lifecycle(adapter,kd) {}
  ~RecordRuntime() {finish();}
  LocalEvidence evidence(bool recovery=false) {
    auto input=mailbox.snapshot(); auto now=WriterClock::now();
    if(input.identity_lost) adapter.latch_body_identity_loss();
    if((!recovery && input.stop_requested) || !input.body || input.body->received_at>now ||
       now-input.body->received_at>writer_max_age ||
       (!recovery && (!input.reference || input.reference->received_at>now ||
        now-input.reference->received_at>writer_max_age-input.reference->source_age_bound)))
      throw std::logic_error("Fresh local body/reference required; cancelled or expired");
    auto& b=*input.body;
    return {b.crc_verified,b.mode_pr,b.mode_machine,std::chrono::duration<double>(now-b.received_at).count()};
  }
  void stop(const std::string& reason,bool fault=false) {
    mailbox.request_stop(reason,fault);
    if(started) {
      std::unique_lock<std::mutex> lock(command_mutex);
      command_wake.wait(lock,[this]{return done.load(std::memory_order_acquire);});
    }
  }
  void recover(const std::string& record) {
    std::unique_lock<std::mutex> lock(command_mutex);
    if(!started || !done.load() || exited.load() || finish_requested || recover_requested)
      throw std::logic_error("Owner must be stopped and available for explicit recovery");
    recovery_record=record; recovery_error.clear(); recovery_done=false; recover_requested=true;
    command_wake.notify_all(); command_wake.wait(lock,[this]{return recovery_done;});
    if(!recovery_error.empty()) throw std::logic_error(recovery_error);
  }
  void finish() {
    stop("record_runtime_shutdown");
    {std::lock_guard<std::mutex> lock(command_mutex); finish_requested=true; command_wake.notify_all();}
    if(owner.joinable()) owner.join();
  }
  void begin() {
    if(started || mailbox.snapshot().stop_requested) throw std::logic_error("Runtime cannot restart");
    auto input=mailbox.snapshot(); auto now=WriterClock::now();
    if(!input.body || !input.reference || input.body->received_at>now ||
       now-input.body->received_at>writer_max_age || input.reference->received_at>now ||
       now-input.reference->received_at>writer_max_age-input.reference->source_age_bound)
      throw std::logic_error("Initial local body/reference required");
    started=true;
    try {owner=std::thread([this] {
      try {
        evidence(); lifecycle.initialize(); lifecycle.acquire([this]{return evidence();});
        lifecycle.begin_initialization();
        // ONLY record-only lifecycle initialization validated by this API.
        // Not usable as a real ownership/support/initial-pose assertion.
        mailbox.set_local_phase_validated(); result=run_body_writer(mailbox,lifecycle);
      } catch(const std::exception& e) {
        mailbox.request_stop(e.what()); result.reason=e.what(); result.stop_attempted=true;
        try {result.stop_write_accepted=lifecycle.stop_candidate_for(mailbox.snapshot().identity_lost,true).sdk_write_accepted;}
        catch(...) {result.stop_write_accepted=false;}
      }
      std::unique_lock<std::mutex> lock(command_mutex);
      done.store(true,std::memory_order_release); command_wake.notify_all();
      while(true) {
        command_wake.wait(lock,[this]{return finish_requested || recover_requested;});
        if(finish_requested) break;
        auto record=recovery_record; lock.unlock();
        std::string failure;
        try {lifecycle.recover(AdapterScope::record_only,record,[this]{return evidence(true);});}
        catch(const std::exception& e) {failure=e.what();}
        lock.lock(); recovery_error=failure; recover_requested=false; recovery_done=true; command_wake.notify_all();
      }
      lock.unlock();
      try {lifecycle.close();} catch(const std::exception& e) {shutdown_error=e.what();}
      exited.store(true,std::memory_order_release);
    });} catch(...) {started=false; mailbox.request_stop("record_owner_creation_failed"); throw;}
  }
};
template<class F> int guarded(F&& f) {
  try {f(); error.clear(); return 0;} catch(const std::exception& e) {error=e.what(); return -1;}
}
}
extern "C" {
const char* g1_pika_record_error() {return error.c_str();}
double g1_pika_record_now() {return std::chrono::duration<double>(WriterClock::now().time_since_epoch()).count();}
void* g1_pika_record_create(const char* session,const double* low,const double* high,const double* velocity,const double* kd) {
  try {if(!session) throw std::invalid_argument("Session required");
    return new RecordRuntime(session,joints(low),joints(high),joints(velocity),joints(kd));
  } catch(const std::exception& e) {error=e.what(); return nullptr;}
}
int g1_pika_record_body(void* h,double received,uint32_t tick,uint8_t pr,uint8_t machine,const uint32_t* raw) {
  return guarded([&] {
    if(!raw) throw std::invalid_argument("Local raw motor states required");
    WriterBody body; body.received_at=stamp(received); body.tick=tick; body.crc_verified=true;
    body.mode_pr=pr; body.mode_machine=machine; body.motor_health_checked=true;
    // Record-only criterion: raw bits zero. NOT firmware health certification.
    std::copy(raw,raw+29,body.motor_errors.begin()); auto& r=*static_cast<RecordRuntime*>(h);
    if(!r.mailbox.ingest_local_body(body,WriterClock::now()) && r.mailbox.snapshot().stop_requested)
      throw std::logic_error("Local body rejected: "+r.mailbox.snapshot().reason);
    // A duplicate tick is accepted as a no-op, never a freshness renewal.
  });
}
int g1_pika_record_reference(void* h,const char* session,uint64_t seq,double received,double age,int phase,
                           const double* q,const double* dq,const double* tau,const double* kp,const double* kd) {
  return guarded([&] {
    if(!session || !std::isfinite(age) || age<0 || age>.1) throw std::invalid_argument("Invalid reference age/session");
    WriterReference ref; ref.session=session; ref.sequence=seq; ref.received_at=stamp(received);
    if(phase<1 || phase>4) throw std::invalid_argument("Explicit local reference phase required");
    ref.phase=static_cast<WriterReference::Phase>(phase);
    ref.source_age_bound=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::duration<double>(age));
    ref.motors={joints(q),joints(dq),joints(tau),joints(kp),joints(kd)};
    auto& r=*static_cast<RecordRuntime*>(h);
    if(!r.mailbox.ingest_reference(ref,WriterClock::now())) throw std::logic_error("Reference rejected: "+r.mailbox.snapshot().reason);
  });
}
int g1_pika_record_begin(void* h) {return guarded([&] {static_cast<RecordRuntime*>(h)->begin();});}
int g1_pika_record_stop(void* h,const char* reason,int fault) {
  return guarded([&] {static_cast<RecordRuntime*>(h)->stop(reason?reason:"local_stop",fault!=0);});
}
int g1_pika_record_recover(void* h,const char* record) {
  return guarded([&] {if(!record || !*record) throw std::invalid_argument("Explicit stop observation required");
    static_cast<RecordRuntime*>(h)->recover(record);});
}
int g1_pika_record_finish(void* h) {
  return guarded([&] {auto& r=*static_cast<RecordRuntime*>(h); r.finish();
    if(!r.shutdown_error.empty()) throw std::runtime_error(r.shutdown_error);});
}
int g1_pika_record_lifecycle(void* h,char* out,size_t capacity) {
  return guarded([&] {auto s=static_cast<RecordRuntime*>(h)->lifecycle.snapshot();
    std::ostringstream json; json<<"{\"phase\":\""<<owner_phase_name(s.phase)<<"\",\"history\":[";
    for(size_t i=0;i<s.history.size();i++) {if(i) json<<','; json<<'\"'<<owner_phase_name(s.history[i])<<'\"';}
    json<<"],\"recovery_acknowledged\":"<<(s.recovery_acknowledged?"true":"false")
        <<",\"fault_latched\":"<<(s.fault_latched?"true":"false")<<'}';
    auto value=json.str(); if(value.size()+1>capacity) throw std::invalid_argument("Lifecycle buffer too small");
    std::memcpy(out,value.c_str(),value.size()+1);});
}
int g1_pika_record_snapshot(void* h,unsigned char* packet,uint64_t* counts,double* timings,char* reason,size_t capacity) {
  return guarded([&] {auto& r=*static_cast<RecordRuntime*>(h); bool done=r.done.load(std::memory_order_acquire);
    counts[0]=r.transport.copy(packet); counts[1]=r.exited.load(std::memory_order_acquire); counts[2]=r.mailbox.snapshot().stop_requested;
    counts[3]=done?r.result.publications:0; counts[4]=done?r.result.stop_attempted:0;
    counts[5]=done?r.result.stop_write_accepted:0;
    counts[6]=done;
    timings[0]=done?r.result.max_start_gap_s:0; timings[1]=done?r.result.max_sink_call_s:0;
    auto text=r.mailbox.snapshot().reason; if(!capacity) throw std::invalid_argument("Reason buffer required");
    std::strncpy(reason,text.c_str(),capacity-1); reason[capacity-1]=0;
  });
}
void g1_pika_record_delete(void* h) {delete static_cast<RecordRuntime*>(h);}
}
