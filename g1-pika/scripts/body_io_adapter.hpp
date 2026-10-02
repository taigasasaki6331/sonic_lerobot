// Explicit adapter boundary. No SDK include, network, thread or implicit IO.
// Trial permission/support/stop-plan inputs are operator/runtime contracts,
// NOT physical facts established by this library or diagnostic lifecycle ACKs.
#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>

namespace g1_pika {
using Joints=std::array<double,29>;
struct MotorValues { Joints q{},dq{},tau{},kp{},kd{}; };
struct ModeReply { int status; std::string form,name; };
struct LocalEvidence {
  bool crc_verified=false;
  uint8_t mode_pr=0,mode_machine=0;
  double age_s=std::numeric_limits<double>::infinity();
};
struct TrialContract {
  bool hardware_output_enabled=false;
  bool explicit_trial_permission=false;
  bool support_and_stop_procedure_confirmed=false;
  bool actual_configuration_confirmed=false;
  bool diagnostic_only=true;
};
struct StopResult { bool sdk_write_accepted=false; bool physical_stop_confirmed=false; };

class Transport {
public:
  virtual ~Transport()=default;
  virtual void open_query_channel()=0;
  virtual ModeReply query_mode()=0;
  virtual int release_mode()=0;
  virtual void open_body_publisher()=0;
  virtual bool write_body(uint8_t machine,const MotorValues&)=0;
  virtual void close_body_publisher()=0;
  virtual int select_mode(const std::string&)=0;
};

class BodyIoAdapter {
  Transport& transport_;
  TrialContract contract_;
  Joints lower_,upper_;
  bool query_open_=false,publisher_open_=false,stopped_=false,fault_=false,release_attempted_=false;
  bool identity_lost_=false,restored_=false;
  std::string original_mode_;
  uint8_t machine_=0;
  bool have_machine_=false;
  void permission() const {
    if(!contract_.hardware_output_enabled || !contract_.explicit_trial_permission ||
       !contract_.support_and_stop_procedure_confirmed || !contract_.actual_configuration_confirmed ||
       contract_.diagnostic_only) throw std::logic_error("Physical trial contract absent; adapter IO prohibited");
  }
  void local(const LocalEvidence& e) {
    if(e.crc_verified && (e.mode_pr!=0 || (have_machine_ && machine_!=e.mode_machine))) identity_lost_=true;
    if(!e.crc_verified || e.mode_pr!=0 || !std::isfinite(e.age_s) || e.age_s<0 || e.age_s>.1 ||
       (have_machine_ && machine_!=e.mode_machine)) {
      fault_=true; throw std::logic_error("Fresh same-host CRC/P-R/machine evidence required");
    }
    machine_=e.mode_machine; have_machine_=true;
  }
  void finite(const MotorValues& m,bool damping=false) const {
    for(size_t i=0;i<29;i++) {
      for(double v:{m.q[i],m.dq[i],m.tau[i],m.kp[i],m.kd[i]})
        if(!std::isfinite(v) || std::abs(v)>std::numeric_limits<float>::max())
          throw std::invalid_argument("Nonfinite/float32-overflow motor value");
      if(m.kp[i]<0 || m.kd[i]<0 || (!damping && (m.q[i]<lower_[i] || m.q[i]>upper_[i])))
        throw std::invalid_argument("Motor bounds/gains invalid");
    }
  }
public:
  // Single G1 IO-owner thread only; not a scheduler or a thread-safe controller.
  // No IO in constructor/destructor. Record-only config can never open IO.
  BodyIoAdapter(Transport& transport,TrialContract contract,Joints lower,Joints upper)
    :transport_(transport),contract_(contract),lower_(lower),upper_(upper) {
    for(size_t i=0;i<29;i++) if(!std::isfinite(lower[i]) || !std::isfinite(upper[i]) || lower[i]>=upper[i])
      throw std::invalid_argument("Explicit joint bounds required");
  }
  void open_query_channel() {
    permission(); if(query_open_ || fault_ || stopped_) throw std::logic_error("Adapter query phase");
    try {transport_.open_query_channel(); query_open_=true;}
    catch(...) {fault_=true; throw;}
  }
  ModeReply query_mode() {
    permission(); if(!query_open_ || fault_ || stopped_) throw std::logic_error("Adapter mode phase");
    try {
      auto reply=transport_.query_mode();
      if(reply.status!=0) throw std::runtime_error("CheckMode RPC failed; no release allowed");
      return reply;
    } catch(...) {fault_=true; throw;}
  }
  int release_once(const LocalEvidence& evidence) {
    permission(); local(evidence);
    if(publisher_open_ || stopped_ || release_attempted_) throw std::logic_error("Repeated/late release prohibited");
    release_attempted_=true;
    auto reply=query_mode(); original_mode_=reply.name;
    // Explicit single attempt. No constructor release, retries or spin loop.
    if(original_mode_.empty()) return 0;
    try {
      int status=transport_.release_mode();
      if(status!=0) fault_=true;
      return status; // RPC status is not proof of a physical ownership lease.
    } catch(...) {fault_=true; throw;}
  }
  void open_publisher(const LocalEvidence& evidence) {
    permission(); local(evidence);
    if(publisher_open_ || stopped_) throw std::logic_error("Publisher phase");
    auto reply=query_mode();
    if(!reply.name.empty()) {fault_=true; throw std::logic_error("Existing controller still active");}
    try {transport_.open_body_publisher(); publisher_open_=true;}
    catch(...) {fault_=true; throw;}
  }
  bool publish(const LocalEvidence& evidence,const MotorValues& motors) {
    permission(); local(evidence);
    if(!publisher_open_ || fault_ || stopped_) throw std::logic_error("Body publisher not armed");
    try {
      finite(motors); bool result=transport_.write_body(machine_,motors);
      if(!result) fault_=true;
      return result;
    } catch(...) {fault_=true; throw;}
  }
  StopResult damping_candidate(const Joints& explicitly_selected_kd) {
    permission(); stopped_=true; // latch BEFORE SDK write; never join GPU/RPC workers first.
    if(!publisher_open_ || !have_machine_ || identity_lost_)
      throw std::logic_error("No initialized body writer or body identity changed; physical fallback required");
    MotorValues m; m.kd=explicitly_selected_kd;
    for(double v:m.kd) if(!std::isfinite(v) || v<=0) throw std::invalid_argument("Explicit positive damping gains required");
    finite(m,true);
    try {
      bool result=transport_.write_body(machine_,m); if(!result) fault_=true;
      return {result,false};
    }
    catch(...) {fault_=true; throw;}
    // No physical-stop confirmation or guaranteed latency; SDK Write may block.
  }
  int restore_original_mode(const std::string& operator_stop_confirmation_record) {
    permission();
    if(!stopped_ || restored_ || identity_lost_ || operator_stop_confirmation_record.empty())
      throw std::logic_error("Explicit physical-stop observation required before restore");
    if(original_mode_.empty()) throw std::logic_error("No previously observed controller to restore");
    // Do not restore automatically in destructor/error cleanup.
    if(publisher_open_) {transport_.close_body_publisher(); publisher_open_=false;}
    restored_=true;
    return transport_.select_mode(original_mode_);
  }
  bool stop_latched() const {return stopped_;}
  // Local owner-loop notification; no SDK call. Identity loss forbids old
  // machine commands, including damping/restore, even without publish().
  void latch_body_identity_loss() {identity_lost_=true; fault_=true; stopped_=true;}
};
}
