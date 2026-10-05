// Shared memory/SDK lifecycle. Every IO operation stays on one owner thread.
// Record provenance is never promoted to physical ownership, pose or stop proof.
#pragma once
#include "body_writer.hpp"
#include <functional>
#include <thread>
#include <vector>

namespace g1_pika {
enum class OwnerPhase { idle,initialized,ownership_pending,owned,initializing,tracking,
                        stop_required,stopped,recovery_pending,recovered,closed,fault };
inline const char* owner_phase_name(OwnerPhase p) {
  switch(p) {
    case OwnerPhase::idle:return "idle";
    case OwnerPhase::initialized:return "initialized";
    case OwnerPhase::ownership_pending:return "ownership_pending";
    case OwnerPhase::owned:return "owned";
    case OwnerPhase::initializing:return "initializing";
    case OwnerPhase::tracking:return "tracking";
    case OwnerPhase::stop_required:return "stop_required";
    case OwnerPhase::stopped:return "stopped";
    case OwnerPhase::recovery_pending:return "recovery_pending";
    case OwnerPhase::recovered:return "recovered";
    case OwnerPhase::closed:return "closed";
    case OwnerPhase::fault:return "fault";
  }
  return "invalid";
}
struct OwnerStatus {
  OwnerPhase phase=OwnerPhase::idle;
  std::vector<OwnerPhase> history{OwnerPhase::idle};
  bool recovery_acknowledged=false,fault_latched=false;
};
class BodyOwnerLifecycle final:public WriterSink {
  BodyIoAdapter& adapter_; Joints stop_kd_;
  mutable std::mutex mutex_; OwnerStatus status_;
  std::optional<std::thread::id> thread_; bool stop_attempted_=false,recovery_attempted_=false;
  void bind() {
    std::lock_guard<std::mutex> lock(mutex_);
    if(!thread_) thread_=std::this_thread::get_id();
    if(*thread_!=std::this_thread::get_id()) throw std::logic_error("Single IO owner thread required");
  }
  void move(OwnerPhase p) {
    std::lock_guard<std::mutex> lock(mutex_); status_.phase=p;
    if(p==OwnerPhase::fault) status_.fault_latched=true;
    if(status_.history.back()!=p) {
      if(status_.history.size()==32) status_.history.erase(status_.history.begin()+1);
      status_.history.push_back(p);
    }
  }
  void require(OwnerPhase p) const {
    if(snapshot().phase!=p) throw std::logic_error("Owner lifecycle phase invalid");
  }
public:
  using EvidenceReader=std::function<LocalEvidence()>;
  BodyOwnerLifecycle(BodyIoAdapter& adapter,Joints stop_kd):adapter_(adapter),stop_kd_(stop_kd) {
    for(double kd:stop_kd_) if(!std::isfinite(kd) || kd<=0 || kd>std::numeric_limits<float>::max())
      throw std::invalid_argument("Explicit owner stop gains required");
  }
  OwnerStatus snapshot() const {std::lock_guard<std::mutex> lock(mutex_); return status_;}
  void initialize() {
    bind(); require(OwnerPhase::idle);
    try {adapter_.open_query_channel(); adapter_.query_mode(); move(OwnerPhase::initialized);}
    catch(...) {move(OwnerPhase::fault); throw;}
  }
  void acquire(const EvidenceReader& evidence) {
    bind(); require(OwnerPhase::initialized); move(OwnerPhase::ownership_pending);
    try {
      if(adapter_.release_once(evidence(),evidence)!=0) throw std::runtime_error("Owner release failed");
      adapter_.open_publisher(evidence(),evidence);
      evidence(); // Recheck cancellation/freshness after potentially blocking setup.
      move(OwnerPhase::owned);
    } catch(...) {move(OwnerPhase::fault); throw;}
  }
  void begin_initialization() {bind(); require(OwnerPhase::owned); move(OwnerPhase::initializing);}
  void confirm_initial_pose(AdapterScope provenance) {
    bind(); require(OwnerPhase::initializing);
    if(provenance!=adapter_.scope()) throw std::logic_error("Initial-pose provenance mismatch");
    move(OwnerPhase::tracking);
  }
  bool publish_reference(const LocalEvidence& e,const WriterReference& ref) override {
    bind(); auto phase=snapshot().phase;
    if(ref.phase==WriterReference::Phase::initializing || ref.phase==WriterReference::Phase::settling) {
      if(phase!=OwnerPhase::initializing) throw std::logic_error("Cannot reenter initialization");
    } else if(ref.phase==WriterReference::Phase::ready || ref.phase==WriterReference::Phase::tracking) {
      if(phase==OwnerPhase::initializing) {
        if(adapter_.scope()!=AdapterScope::record_only)
          throw std::logic_error("Physical initial-pose check required before normal control");
        confirm_initial_pose(AdapterScope::record_only);
      }
    } else throw std::logic_error("Explicit local reference phase required");
    return publish(e,ref.motors);
  }
  bool publish(const LocalEvidence& e,const MotorValues& motors) override {
    bind(); auto p=snapshot().phase;
    if(p!=OwnerPhase::initializing && p!=OwnerPhase::tracking) throw std::logic_error("Owner not controlling");
    try {bool ok=adapter_.publish(e,motors); if(!ok) move(OwnerPhase::fault); return ok;}
    catch(...) {move(OwnerPhase::fault); throw;}
  }
  StopResult stop_candidate(bool identity_lost) override {
    bind(); if(stop_attempted_) throw std::logic_error("Owner stop already attempted");
    stop_attempted_=true; move(OwnerPhase::stop_required); // BEFORE any transport call.
    try {
      if(identity_lost) {
        adapter_.latch_body_identity_loss(); throw std::logic_error("Body identity lost; physical fallback required");
      }
      auto result=adapter_.damping_candidate(stop_kd_);
      move(result.sdk_write_accepted?OwnerPhase::stopped:OwnerPhase::fault);
      return {result.sdk_write_accepted,false};
    } catch(...) {move(OwnerPhase::fault); throw;}
  }
  StopResult stop_candidate_for(bool identity_lost,bool fault) override {
    bind(); if(fault) move(OwnerPhase::fault); return stop_candidate(identity_lost);
  }
  void recover(AdapterScope provenance,const std::string& stop_observation,const EvidenceReader& evidence) {
    bind(); auto p=snapshot().phase;
    if((p!=OwnerPhase::stopped && p!=OwnerPhase::fault) || !stop_attempted_ || recovery_attempted_ ||
       provenance!=adapter_.scope() || stop_observation.empty())
      throw std::logic_error("Explicit matching stop observation required for recovery");
    recovery_attempted_=true; move(OwnerPhase::recovery_pending);
    try {
      adapter_.validate_recovery_evidence(evidence());
      if(adapter_.restore_original_mode(stop_observation)!=0) throw std::runtime_error("Owner restore failed");
      {std::lock_guard<std::mutex> lock(mutex_); status_.recovery_acknowledged=true;}
      move(OwnerPhase::recovered);
    } catch(...) {move(OwnerPhase::fault); throw;}
  }
  void close() {
    bind(); auto p=snapshot().phase;
    if(p==OwnerPhase::closed) return;
    if(p!=OwnerPhase::idle && p!=OwnerPhase::initialized && p!=OwnerPhase::stopped &&
       p!=OwnerPhase::fault && p!=OwnerPhase::recovered) throw std::logic_error("Stop required before owner close");
    try {adapter_.close_publisher(); move(OwnerPhase::closed);}
    catch(...) {move(OwnerPhase::fault); throw;}
  }
};
}
