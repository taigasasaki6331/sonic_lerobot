// Native 500 Hz owner loop. No SDK, sockets, publisher or implicit startup.
// Inputs MUST be submitted by a trusted same-host gateway. There is no peer
// API for local body/readiness. This is not a physical ownership/stop proof.
#pragma once
#include "body_io_adapter.hpp"
#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <optional>
#include <utility>

namespace g1_pika {
using WriterClock=std::chrono::steady_clock;
using WriterTime=WriterClock::time_point;
constexpr auto writer_period=std::chrono::microseconds(2000);
constexpr auto writer_max_gap=std::chrono::milliseconds(10);
constexpr auto writer_max_age=std::chrono::milliseconds(100);

struct WriterBody {
  WriterTime received_at;
  uint32_t tick=0;
  bool crc_verified=false;
  uint8_t mode_pr=0,mode_machine=0;
  // Set only after interpreting actual motor diagnostics on the local host.
  // The existing JSON reader does not yet supply this health evidence.
  bool motor_health_checked=false;
  std::array<uint32_t,29> motor_errors{};
};
struct WriterReference {
  enum class Phase { unspecified,initializing,settling,ready,tracking };
  Phase phase=Phase::unspecified; // Trusted same-host lifecycle; never a peer ACK.
  std::string session;
  uint64_t sequence=0;
  WriterTime received_at;
  std::chrono::nanoseconds source_age_bound{};
  MotorValues motors;
};
struct WriterSnapshot {
  std::optional<WriterBody> body;
  std::optional<WriterReference> reference;
  bool local_phase_validated=false,stop_requested=false,identity_lost=false;
  bool fault_stop=false;
  std::string reason;
};

// Bounded latest-value mailbox, not a target queue. Admission checks EVERY
// input before replacement, so a bad packet cannot be hidden by a later one.
// Times must be from this host's steady_clock, not a GPU timestamp.
class WriterMailbox {
  std::mutex mutex_;
  std::condition_variable wake_;
  WriterSnapshot value_;
  std::string session_;
  Joints lower_,upper_,velocity_;
  bool have_machine_=false;
  uint8_t machine_=0;
  std::optional<WriterTime> last_ingest_;
  bool reject(const std::string& reason,bool fault=true) {
    value_.fault_stop=value_.fault_stop || fault;
    value_.stop_requested=true;
    if(value_.reason.empty()) value_.reason=reason;
    wake_.notify_all(); return false;
  }
  bool clock(WriterTime now) {
    if(last_ingest_ && now<*last_ingest_) return reject("local_ingest_clock_reversed");
    last_ingest_=now; return true;
  }
public:
  WriterMailbox(std::string session,Joints lower,Joints upper,Joints velocity)
    :session_(std::move(session)),lower_(lower),upper_(upper),velocity_(velocity) {
    if(session_.empty() || session_.size()>128) throw std::invalid_argument("Writer session required");
    for(size_t i=0;i<29;i++)
      if(!std::isfinite(lower[i]) || !std::isfinite(upper[i]) || lower[i]>=upper[i] ||
         !std::isfinite(velocity[i]) || velocity[i]<=0)
        throw std::invalid_argument("Writer model limits required");
  }
  bool ingest_local_body(const WriterBody& body,WriterTime now) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(body.crc_verified && (body.mode_pr!=0 || (have_machine_ && body.mode_machine!=machine_)))
      value_.identity_lost=true;
    if(value_.stop_requested || !clock(now)) return false;
    if(!body.crc_verified || body.mode_pr!=0 || !body.motor_health_checked ||
       body.received_at>now || now-body.received_at>writer_max_age)
      return reject("local_body_crc_health_or_age_invalid");
    for(auto error:body.motor_errors) if(error) return reject("local_motor_error");
    if(have_machine_ && body.mode_machine!=machine_) return reject("local_machine_changed");
    if(value_.body) {
      if(now-value_.body->received_at>writer_max_age) return reject("local_body_gap_expired");
      uint32_t delta=body.tick-value_.body->tick;
      if(delta==0) {
        // Repeated tick never renews freshness, even if the peer sends it again.
        if(now-value_.body->received_at>writer_max_age) return reject("local_body_expired");
        return false;
      }
      if(delta>=0x80000000u || body.received_at<=value_.body->received_at)
        return reject("local_body_tick_or_clock_reversed");
      if(body.received_at-value_.body->received_at>writer_max_age)
        return reject("local_body_gap_expired");
    }
    value_.body=body; have_machine_=true; machine_=body.mode_machine; return true;
  }
  bool ingest_reference(const WriterReference& ref,WriterTime now) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(value_.stop_requested || !clock(now)) return false;
    if(ref.session!=session_ || ref.received_at>now || ref.source_age_bound.count()<0 ||
       ref.source_age_bound>writer_max_age || now-ref.received_at>writer_max_age-ref.source_age_bound)
      return reject("reference_session_or_age_invalid");
    if(value_.reference) {
      auto& prior=*value_.reference;
      if(prior.sequence==std::numeric_limits<uint64_t>::max() || ref.sequence!=prior.sequence+1 ||
         ref.received_at<=prior.received_at ||
         now-prior.received_at>writer_max_age-prior.source_age_bound)
        return reject("reference_sequence_clock_or_gap_invalid");
    } else if(ref.sequence!=0) return reject("reference_first_sequence_invalid");
    for(size_t i=0;i<29;i++) {
      const auto& m=ref.motors;
      for(double v:{m.q[i],m.dq[i],m.tau[i],m.kp[i],m.kd[i]})
        if(!std::isfinite(v) || std::abs(v)>std::numeric_limits<float>::max())
          return reject("reference_nonfinite_or_float32_overflow");
      if(m.q[i]<lower_[i] || m.q[i]>upper_[i] || m.kp[i]<0 || m.kd[i]<0 || std::abs(m.dq[i])>velocity_[i])
        return reject("reference_model_limit");
      if(value_.reference) {
        double dt=std::min(.02,std::chrono::duration<double>(ref.received_at-value_.reference->received_at).count());
        double step=std::abs(m.q[i]-value_.reference->motors.q[i]);
        if(step>.05 || step>velocity_[i]*dt+1e-12) return reject("reference_step_or_velocity_limit");
      }
    }
    value_.reference=ref; return true;
  }
  // A trusted LOCAL lifecycle must validate initialization, initial-reference
  // fit, ownership and support before this call. Not a network/diagnostic ACK.
  // The mailbox cannot establish these physical facts on its own.
  void set_local_phase_validated() {
    std::lock_guard<std::mutex> lock(mutex_);
    if(value_.stop_requested) throw std::logic_error("Writer stop is latched");
    value_.local_phase_validated=true;
  }
  void request_stop(const std::string& reason="local_stop_requested",bool fault=true) {
    std::lock_guard<std::mutex> lock(mutex_); reject(reason.empty()?"local_stop_requested":reason,fault);
  }
  WriterSnapshot snapshot() {std::lock_guard<std::mutex> lock(mutex_); return value_;}
  // New targets/body do not cause extra writes; only stop interrupts the wait.
  void wait_until(WriterTime deadline) {
    std::unique_lock<std::mutex> lock(mutex_);
    wake_.wait_until(lock,deadline,[&]{return value_.stop_requested;});
  }
};

enum class WriterAction { waiting,publish,stop };
struct WriterDecision {
  WriterAction action=WriterAction::waiting;
  std::string reason;
  LocalEvidence evidence;
};
// Inspect a snapshot using a timestamp acquired AFTER copying that snapshot.
// A concurrent local ingest may otherwise look falsely "from the future".
inline WriterDecision inspect_writer_inputs(WriterTime now,const WriterSnapshot& value) {
  auto stop=[](const std::string& reason) {return WriterDecision{WriterAction::stop,reason,{}};};
  if(value.stop_requested) return stop(value.reason.empty()?"local_stop_requested":value.reason);
  if(!value.body || !value.reference || !value.local_phase_validated) return {};
  const auto& body=*value.body; const auto& ref=*value.reference;
  if(!body.crc_verified || body.mode_pr!=0 || !body.motor_health_checked ||
     body.received_at>now || now-body.received_at>writer_max_age)
    return stop("writer_body_crc_health_or_age_invalid");
  for(auto error:body.motor_errors) if(error) return stop("writer_motor_error");
  if(ref.received_at>now || ref.source_age_bound.count()<0 || ref.source_age_bound>writer_max_age ||
     now-ref.received_at>writer_max_age-ref.source_age_bound)
    return stop("writer_reference_expired_or_invalid");
  return {WriterAction::publish,"",{true,0,body.mode_machine,std::chrono::duration<double>(now-body.received_at).count()}};
}
// Recheck immediately before a sink call; a poll result is not a lasting permit.
// The existing 10ms/100ms bounds apply to actual elapsed time, including delays
// in mailbox copies or scheduling between the poll and publication.
inline WriterDecision guard_writer_publication(WriterTime now,const WriterSnapshot& value,
    WriterTime polled_at,const std::optional<WriterTime>& previous_write,uint8_t expected_machine) {
  if(value.stop_requested) return {WriterAction::stop,value.reason.empty()?"local_stop_requested":value.reason,{}};
  if(now<polled_at || (previous_write && now<*previous_write))
    return {WriterAction::stop,"writer_clock_reversed",{}};
  if(now-polled_at>writer_max_gap || (previous_write && now-*previous_write>writer_max_gap))
    return {WriterAction::stop,"writer_deadline_gap",{}};
  auto result=inspect_writer_inputs(now,value);
  if(result.action==WriterAction::waiting) return {WriterAction::stop,"writer_local_phase_or_input_lost",{}};
  if(result.action==WriterAction::publish && result.evidence.mode_machine!=expected_machine)
    return {WriterAction::stop,"writer_machine_changed",{}};
  return result;
}
// Deterministic deadline/watchdog kernel; used by the actual native owner loop
// and by fake-clock fault injection. No lifecycle INIT or SDK RPC here.
class WriterKernel {
  bool stopped_=false,started_=false;
  std::optional<WriterTime> last_poll_,last_write_;
  std::optional<uint8_t> machine_;
  WriterDecision stop(const std::string& reason) {stopped_=true; return {WriterAction::stop,reason,{}};}
public:
  WriterDecision poll(WriterTime now,const WriterSnapshot& value) {
    if(stopped_) return {WriterAction::stop,"writer_stop_latched",{}};
    if(last_poll_ && now<*last_poll_) return stop("writer_clock_reversed");
    last_poll_=now;
    if(value.stop_requested) return stop(value.reason.empty()?"local_stop_requested":value.reason);
    if(started_ && last_write_ && now-*last_write_>writer_max_gap) return stop("writer_deadline_gap");
    auto inputs=inspect_writer_inputs(now,value);
    if(inputs.action==WriterAction::stop) return stop(inputs.reason);
    if(inputs.action==WriterAction::waiting) {
      if(started_) return stop("writer_local_phase_or_input_lost");
      return {};
    }
    if(machine_ && *machine_!=inputs.evidence.mode_machine) return stop("writer_machine_changed");
    // Never replay missed 2ms periods in a burst. At most one publication/poll.
    if(last_write_ && now-*last_write_<writer_period) return {};
    machine_=inputs.evidence.mode_machine; started_=true; last_write_=now;
    return inputs;
  }
  // poll() assumes an immediate sink for deterministic kernel callers. The
  // actual loop commits the guarded call's start, rather than an earlier poll.
  void publication_started(WriterTime now) {
    if(!last_write_ || now<*last_write_) throw std::logic_error("Writer publication clock invalid");
    last_write_=now;
  }
};

class WriterSink {
public:
  virtual ~WriterSink()=default;
  virtual bool publish(const LocalEvidence&,const MotorValues&)=0;
  virtual bool publish_reference(const LocalEvidence& e,const WriterReference& ref) {return publish(e,ref.motors);}
  virtual StopResult stop_candidate(bool identity_lost)=0;
  virtual StopResult stop_candidate_for(bool identity_lost,bool) {return stop_candidate(identity_lost);}
};
// Not instantiated by any hardware launcher. Caller must keep ALL adapter
// calls on this IO-owner thread, including prior explicit setup and restore.
class AdapterWriterSink:public WriterSink {
  BodyIoAdapter& adapter_; Joints kd_;
public:
  AdapterWriterSink(BodyIoAdapter& adapter,Joints explicitly_selected_kd):adapter_(adapter),kd_(explicitly_selected_kd) {
    for(double kd:kd_) if(!std::isfinite(kd) || kd<=0 || kd>std::numeric_limits<float>::max())
      throw std::invalid_argument("Explicit writer stop gains required");
  }
  bool publish(const LocalEvidence& e,const MotorValues& m) override {return adapter_.publish(e,m);}
  StopResult stop_candidate(bool identity_lost) override {
    if(identity_lost) {
      adapter_.latch_body_identity_loss();
      throw std::logic_error("Writer body identity lost; physical fallback required");
    }
    return adapter_.damping_candidate(kd_);
  }
};
struct WriterRunReport {
  uint64_t publications=0;
  std::string reason;
  bool stop_attempted=false,stop_write_accepted=false,physical_stop_confirmed=false;
  double max_start_gap_s=0,max_sink_call_s=0;
  double max_observed_gap_s=0,max_admission_delay_s=0,stop_body_age_s=-1,stop_reference_age_s=-1;
};
// Soft real-time steady-clock scheduling. Does NOT set RT priority/governor.
// A blocking SDK write cannot be interrupted here: independent physical
// fallback is still required, and shutdown/join alone is NOT a robot stop.
inline WriterRunReport run_body_writer(WriterMailbox& mailbox,WriterSink& sink) {
  WriterRunReport report; WriterKernel kernel;
  std::optional<WriterTime> prior_write;
  auto stop=[&](const std::string& reason) {
    auto before=mailbox.snapshot(); bool fault=before.stop_requested?before.fault_stop:true;
    mailbox.request_stop(reason,fault); report.reason=mailbox.snapshot().reason;
    // Stop is latched before calling sink. No GPU/RPC/join wait first.
    report.stop_attempted=true;
    auto final=mailbox.snapshot();
    auto detected=WriterClock::now();
    if(final.body) report.stop_body_age_s=std::chrono::duration<double>(detected-final.body->received_at).count();
    if(final.reference) report.stop_reference_age_s=std::chrono::duration<double>(detected-final.reference->received_at+
        final.reference->source_age_bound).count();
    bool identity_lost=final.identity_lost || reason=="writer_machine_changed";
    try {report.stop_write_accepted=sink.stop_candidate_for(identity_lost,fault).sdk_write_accepted;}
    catch(...) {report.stop_write_accepted=false;}
    // Never promote the sink's response to a physical-stop confirmation.
  };
  while(true) {
    auto input=mailbox.snapshot(); auto now=WriterClock::now();
    if(prior_write) report.max_observed_gap_s=std::max(report.max_observed_gap_s,
        std::chrono::duration<double>(now-*prior_write).count());
    auto decision=kernel.poll(now,input);
    if(decision.action==WriterAction::stop) {stop(decision.reason); return report;}
    if(decision.action==WriterAction::publish) {
      // A stop that won admission while we copied data must precede this write.
      // A request during the SDK call cannot retract an already in-flight write.
      auto latest=mailbox.snapshot(); auto begin=WriterClock::now();
      auto guarded=guard_writer_publication(begin,latest,now,prior_write,decision.evidence.mode_machine);
      report.max_admission_delay_s=std::max(report.max_admission_delay_s,std::chrono::duration<double>(begin-now).count());
      if(prior_write) report.max_observed_gap_s=std::max(report.max_observed_gap_s,
          std::chrono::duration<double>(begin-*prior_write).count());
      if(guarded.action==WriterAction::stop) {stop(guarded.reason); return report;}
      if(prior_write) report.max_start_gap_s=std::max(report.max_start_gap_s,std::chrono::duration<double>(begin-*prior_write).count());
      prior_write=begin; kernel.publication_started(begin);
      bool ok=false;
      try {ok=sink.publish_reference(guarded.evidence,*latest.reference);} catch(...) {}
      auto end=WriterClock::now();
      report.max_sink_call_s=std::max(report.max_sink_call_s,std::chrono::duration<double>(end-begin).count());
      if(!ok) {stop("writer_sink_failed"); return report;}
      report.publications++;
      // No normal write after a blocked/slow sink violates the 10ms budget.
      if(end-begin>writer_max_gap) {stop("writer_sink_blocked_past_deadline"); return report;}
      now=begin;
    }
    // Anchor to the actual poll, not a loop of expired deadlines/catch-up writes.
    mailbox.wait_until(now+writer_period);
  }
}
}
