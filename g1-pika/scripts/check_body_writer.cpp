// SDK-free writer tests: all body/health/readiness/permissions are ARTIFICIAL.
// No robot, DDS, sockets, devices, RT priority or physical stop confirmation.
#include "body_writer.hpp"
#include <atomic>
#include <cassert>
#include <iostream>
#include <thread>
#include <vector>
using namespace g1_pika;
using namespace std::chrono_literals;
Joints fill(double value) {Joints q; q.fill(value); return q;}
WriterTime time_at(double seconds) {return WriterTime(std::chrono::nanoseconds(std::llround(seconds*1e9)));}
WriterBody body_at(WriterTime now,uint32_t tick=1) {WriterBody b; b.received_at=now; b.tick=tick;
  b.crc_verified=true; b.mode_machine=5; b.motor_health_checked=true; return b;}
WriterReference ref_at(WriterTime now,uint64_t sequence=0) {WriterReference r;
  r.session="fake-session"; r.sequence=sequence; r.received_at=now; r.motors.kp.fill(10); r.motors.kd.fill(1); return r;}
void inputs(WriterMailbox& m,WriterTime now) {assert(m.ingest_local_body(body_at(now),now));
  assert(m.ingest_reference(ref_at(now),now)); m.set_local_phase_validated();}
struct Sink:WriterSink {
  std::atomic<unsigned> writes{0},stops{0};
  bool fail=false,throw_write=false,throw_stop=false,identity_seen=false;
  std::chrono::milliseconds delay{};
  bool publish(const LocalEvidence& e,const MotorValues&) override {
    assert(e.crc_verified && e.mode_machine==5 && e.mode_pr==0 && e.age_s<=.1);
    writes++; if(delay.count()) std::this_thread::sleep_for(delay);
    if(throw_write) throw std::runtime_error("fake write exception");
    return !fail;
  }
  StopResult stop_candidate(bool identity_lost) override {stops++; identity_seen=identity_lost;
    if(throw_stop) throw std::runtime_error("fake stop exception");
    return {true,true}; // malicious/incorrect sink confirmation must NOT be trusted.
  }
};
struct FakeTransport:Transport {
  unsigned writes=0; std::string mode="original";
  void open_query_channel() override {}
  ModeReply query_mode() override {return {0,"fake",mode};}
  int release_mode() override {mode.clear(); return 0;}
  void open_body_publisher() override {}
  bool write_body(uint8_t,const MotorValues&) override {writes++; return true;}
  void close_body_publisher() override {}
  int select_mode(const std::string&) override {return 0;}
};
int main() {
  unsigned checks=0;
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); WriterKernel k;
    assert(k.poll(time_at(0),m.snapshot()).action==WriterAction::waiting);
    assert(m.ingest_local_body(body_at(time_at(0)),time_at(0))); assert(m.ingest_reference(ref_at(time_at(0)),time_at(0)));
    assert(k.poll(time_at(0),m.snapshot()).action==WriterAction::waiting); checks++;}
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); inputs(m,time_at(0)); WriterKernel k;
    assert(k.poll(time_at(0),m.snapshot()).action==WriterAction::publish);
    assert(k.poll(time_at(.001),m.snapshot()).action==WriterAction::waiting);
    assert(k.poll(time_at(.002),m.snapshot()).action==WriterAction::publish);
    assert(k.poll(time_at(.009),m.snapshot()).action==WriterAction::publish);
    assert(k.poll(time_at(.009),m.snapshot()).action==WriterAction::waiting); // no catch-up burst
    auto r=k.poll(time_at(.020),m.snapshot()); assert(r.action==WriterAction::stop && r.reason=="writer_deadline_gap");
    assert(k.poll(time_at(.021),m.snapshot()).action==WriterAction::stop); checks++;}
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); inputs(m,time_at(0));
    assert(!m.ingest_local_body(body_at(time_at(.05)),time_at(.05))); // same tick
    assert(m.snapshot().body->received_at==time_at(0));
    assert(!m.ingest_local_body(body_at(time_at(.101)),time_at(.101)));
    assert(m.snapshot().stop_requested); checks++;}
  for(bool expire_body:{true,false}) {
    WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); inputs(m,time_at(0)); WriterKernel k;
    for(unsigned i=0;i<=51;i++) {
      auto t=time_at(.002*i);
      if(i && !expire_body) assert(m.ingest_local_body(body_at(t,i+1),t));
      if(i && expire_body) assert(m.ingest_reference(ref_at(t,i),t));
      auto r=k.poll(t,m.snapshot());
      if(i<=50) assert(r.action==WriterAction::publish);
      else assert(r.action==WriterAction::stop && r.reason==(expire_body?"writer_body_crc_health_or_age_invalid":"writer_reference_expired_or_invalid"));
    } checks++;
  }
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); auto r=ref_at(time_at(0)); r.source_age_bound=80ms;
    assert(m.ingest_reference(r,time_at(0))); assert(m.ingest_local_body(body_at(time_at(0)),time_at(0))); m.set_local_phase_validated();
    WriterKernel k; for(int i=0;i<=10;i++) assert(k.poll(time_at(.002*i),m.snapshot()).action==WriterAction::publish);
    assert(k.poll(time_at(.022),m.snapshot()).action==WriterAction::stop); checks++;}
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); inputs(m,time_at(0)); auto bad=ref_at(time_at(.02),1); bad.session="replay";
    assert(!m.ingest_reference(bad,time_at(.02))); assert(!m.ingest_reference(ref_at(time_at(.02),1),time_at(.02)));
    assert(m.snapshot().stop_requested && m.snapshot().reference->sequence==0); checks++;}
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); inputs(m,time_at(0));
    assert(!m.ingest_reference(ref_at(time_at(.02),2),time_at(.02))); checks++;}
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); inputs(m,time_at(0));
    auto bad=ref_at(time_at(.02),1); bad.motors.q[3]=.021; assert(!m.ingest_reference(bad,time_at(.02))); checks++;}
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); inputs(m,time_at(0));
    auto bad=ref_at(time_at(.001),1); bad.motors.q[3]=.002; assert(!m.ingest_reference(bad,time_at(.001))); checks++;}
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); inputs(m,time_at(0));
    auto bad=ref_at(time_at(.02),1); bad.motors.kd[28]=NAN; assert(!m.ingest_reference(bad,time_at(.02))); checks++;}
  for(int invalid=0;invalid<4;invalid++) {
    WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); inputs(m,time_at(0)); auto b=body_at(time_at(.02),2);
    if(invalid==0) b.motor_health_checked=false;
    if(invalid==1) b.motor_errors[28]=1;
    if(invalid==2) b.crc_verified=false;
    if(invalid==3) b.mode_machine=6;
    assert(!m.ingest_local_body(b,time_at(.02))); assert(m.snapshot().stop_requested);
    assert(m.snapshot().identity_lost==(invalid==3)); checks++;
  }
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); inputs(m,time_at(0));
    auto b=body_at(time_at(.02),2); b.mode_pr=1; assert(!m.ingest_local_body(b,time_at(.02))); assert(m.snapshot().identity_lost); checks++;}
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); inputs(m,time_at(0));
    assert(!m.ingest_local_body(body_at(time_at(-.01),2),time_at(-.01))); checks++;}
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); inputs(m,time_at(0)); WriterKernel k;
    unsigned publications=0;
    for(unsigned i=0;i<1500;i++) {
      auto now=time_at(.002*i);
      if(i && i%10==0) {assert(m.ingest_local_body(body_at(now,i/10+1),now)); auto r=ref_at(now,i/10);
        r.motors.q[0]=.001*(i/10); assert(m.ingest_reference(r,now));}
      auto r=k.poll(now,m.snapshot()); assert(r.action==WriterAction::publish); publications++;
    }
    assert(publications==1500 && m.snapshot().reference->sequence==149); checks++;}
  {FakeTransport f; BodyIoAdapter a(f,{true,true,true,true,false},fill(-1),fill(1));
    LocalEvidence e{true,0,5,0}; a.open_query_channel(); assert(a.release_once(e)==0); a.open_publisher(e);
    AdapterWriterSink sink(a,fill(2)); assert(sink.publish(e,MotorValues{})); unsigned before=f.writes;
    bool rejected=false; try {sink.stop_candidate(true);} catch(const std::logic_error&) {rejected=true;}
    assert(rejected && a.stop_latched() && f.writes==before); checks++;}
  std::vector<WriterRunReport> runs;
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); Sink sink;
    WriterRunReport report;
    std::thread owner([&]{report=run_body_writer(m,sink);});
    // Loop is running, but must not write before the local phase/input gates.
    std::this_thread::sleep_for(5ms); assert(sink.writes.load()==0);
    auto now=WriterClock::now(); inputs(m,now);
    for(unsigned i=0;i<20 && !sink.writes.load();i++) std::this_thread::sleep_for(1ms);
    m.request_stop("fake_operator_stop"); owner.join();
    assert(report.publications>0 && report.stop_attempted && sink.stops==1 && !report.physical_stop_confirmed);
    assert(report.reason=="fake_operator_stop" || report.reason=="writer_deadline_gap"); runs.push_back(report); checks++;}
  {WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); Sink sink;
    inputs(m,WriterClock::now()); WriterRunReport report;
    std::thread owner([&]{report=run_body_writer(m,sink);});
    for(unsigned i=1;i<=8;i++) {
      std::this_thread::sleep_for(10ms); auto now=WriterClock::now();
      if(m.snapshot().stop_requested) break;
      if(!m.ingest_local_body(body_at(now,i+1),now)) break;
      if(!m.ingest_reference(ref_at(now,i),now)) break;
    }
    m.request_stop("fake_stream_complete"); owner.join();
    assert(report.publications>0 && sink.stops==1 && !report.physical_stop_confirmed);
    runs.push_back(report); checks++;
  }
  for(int failure=0;failure<3;failure++) {
    WriterMailbox m("fake-session",fill(-1),fill(1),fill(1)); Sink sink;
    sink.fail=failure==0; sink.throw_write=failure==1; sink.throw_stop=failure==1;
    if(failure==2) sink.delay=25ms;
    inputs(m,WriterClock::now()); auto report=run_body_writer(m,sink);
    assert(sink.writes==1 && sink.stops==1 && report.stop_attempted && !report.physical_stop_confirmed);
    assert(report.reason==(failure==2?"writer_sink_blocked_past_deadline":"writer_sink_failed"));
    assert(m.snapshot().stop_requested); runs.push_back(report); checks++;
  }
  std::cout<<"{\"writer_checks\":"<<checks<<",\"scope\":\"SDK_free_fake_transport_artificial_inputs\",\"robot_commands_sent\":false,\"physical_stop_confirmed\":false,\"threaded_runs\":[";
  for(size_t i=0;i<runs.size();i++) {
    if(i) std::cout<<",";
    auto& r=runs[i];
    std::cout<<"{\"reason\":\""<<r.reason<<"\",\"publications\":"<<r.publications
      <<",\"max_start_gap_s\":"<<r.max_start_gap_s<<",\"max_sink_call_s\":"<<r.max_sink_call_s<<"}";
  } std::cout<<"]}\n";
}
