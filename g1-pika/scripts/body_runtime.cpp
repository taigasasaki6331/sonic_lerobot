// RECORD-ONLY native owner: same-host mailbox -> actual writer -> native memory.
// No SDK library/client/publisher can be selected by this exported API.
#include "body_writer.hpp"
#include "LowCmd_data.hpp"
#include "CRC_data.h"
#include <atomic>
#include <cstring>
#include <new>
#include <thread>
#include <type_traits>
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
  int select_mode(const std::string&) override {throw std::logic_error("No automatic ownership restore");}
  uint64_t copy(unsigned char* out) {
    std::lock_guard<std::mutex> lock(mutex_); std::memcpy(out,latest_.data(),1004); return publications_;
  }
};
class RecordRuntime {
public:
  WriterMailbox mailbox; MemoryTransport transport; BodyIoAdapter adapter; AdapterWriterSink sink;
  std::thread owner; std::atomic<bool> done{false}; WriterRunReport result;
  bool started=false;
  RecordRuntime(std::string session,Joints low,Joints high,Joints velocity,Joints kd)
    :mailbox(std::move(session),low,high,velocity),
     adapter(transport,{true,true,true,true,false},low,high),sink(adapter,kd) {}
  ~RecordRuntime() {mailbox.request_stop("record_runtime_destroyed"); if(owner.joinable()) owner.join();}
  void begin() {
    if(started || mailbox.snapshot().stop_requested) throw std::logic_error("Runtime cannot restart");
    auto input=mailbox.snapshot(); auto now=WriterClock::now();
    if(!input.body || !input.reference || now-input.body->received_at>writer_max_age)
      throw std::logic_error("Initial local body/reference required");
    started=true;
    owner=std::thread([this] {
      try {
        auto body=mailbox.snapshot().body.value();
        LocalEvidence e{body.crc_verified,body.mode_pr,body.mode_machine,
          std::chrono::duration<double>(WriterClock::now()-body.received_at).count()};
        adapter.open_query_channel();
        if(adapter.release_once(e)!=0) throw std::runtime_error("Record release failed");
        adapter.open_publisher(e);
        // ONLY record-only lifecycle initialization validated by this API.
        // Not usable as a real ownership/support/initial-pose assertion.
        mailbox.set_local_phase_validated(); result=run_body_writer(mailbox,sink);
        transport.close_body_publisher();
      } catch(const std::exception& e) {mailbox.request_stop(e.what()); result.reason=e.what();}
      done.store(true,std::memory_order_release);
    });
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
int g1_pika_record_reference(void* h,const char* session,uint64_t seq,double received,double age,
                           const double* q,const double* dq,const double* tau,const double* kp,const double* kd) {
  return guarded([&] {
    if(!session || !std::isfinite(age) || age<0 || age>.1) throw std::invalid_argument("Invalid reference age/session");
    WriterReference ref; ref.session=session; ref.sequence=seq; ref.received_at=stamp(received);
    ref.source_age_bound=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::duration<double>(age));
    ref.motors={joints(q),joints(dq),joints(tau),joints(kp),joints(kd)};
    auto& r=*static_cast<RecordRuntime*>(h);
    if(!r.mailbox.ingest_reference(ref,WriterClock::now())) throw std::logic_error("Reference rejected: "+r.mailbox.snapshot().reason);
  });
}
int g1_pika_record_begin(void* h) {return guarded([&] {static_cast<RecordRuntime*>(h)->begin();});}
int g1_pika_record_stop(void* h,const char* reason) {
  return guarded([&] {auto& r=*static_cast<RecordRuntime*>(h); r.mailbox.request_stop(reason?reason:"local_stop");
    if(r.owner.joinable()) r.owner.join();});
}
int g1_pika_record_snapshot(void* h,unsigned char* packet,uint64_t* counts,double* timings,char* reason,size_t capacity) {
  return guarded([&] {auto& r=*static_cast<RecordRuntime*>(h); bool done=r.done.load(std::memory_order_acquire);
    counts[0]=r.transport.copy(packet); counts[1]=done; counts[2]=r.mailbox.snapshot().stop_requested;
    counts[3]=done?r.result.publications:0; counts[4]=done?r.result.stop_attempted:0;
    counts[5]=done?r.result.stop_write_accepted:0;
    timings[0]=done?r.result.max_start_gap_s:0; timings[1]=done?r.result.max_sink_call_s:0;
    auto text=r.mailbox.snapshot().reason; if(!capacity) throw std::invalid_argument("Reason buffer required");
    std::strncpy(reason,text.c_str(),capacity-1); reason[capacity-1]=0;
  });
}
void g1_pika_record_delete(void* h) {delete static_cast<RecordRuntime*>(h);}
}
