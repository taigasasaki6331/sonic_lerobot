// Compile/API validation only. Do not instantiate/call against G1 yet.
// Current default build rejects ALL IO; enabling compile flag is NOT authority.
#include "unitree_body_transport.hpp"
#include <unitree/robot/channel/channel_publisher.hpp>
#include <unitree/robot/b2/motion_switcher/motion_switcher_client.hpp>
#include <unitree/idl/hg/LowCmd_.hpp>
#include <unitree/dds_wrapper/common/crc.h>
#include <cstring>
#include <new>
#include <type_traits>
#ifndef G1_PIKA_ENABLE_BODY_IO
#define G1_PIKA_ENABLE_BODY_IO 0
#endif

namespace g1_pika {
UnitreeBodySession::UnitreeBodySession(const std::string& interface_name,const std::string& session,
    TrialContract contract,Joints lower,Joints upper,Joints velocity,Joints stop_kd)
  :transport_(interface_name),adapter_(transport_,contract,lower,upper),
   mailbox(session,lower,upper,velocity),owner(adapter_,stop_kd) {}
using Command=unitree_hg::msg::dds_::LowCmd_;
using Publisher=unitree::robot::ChannelPublisher<Command>;
using Switcher=unitree::robot::b2::MotionSwitcherClient;
static void build_permission() {
  if(!G1_PIKA_ENABLE_BODY_IO) throw std::logic_error("Build-only SDK transport: hardware IO disabled");
}
struct UnitreeBodyTransport::Impl {
  std::string interface;
  std::unique_ptr<Switcher> switcher;
  std::unique_ptr<Publisher> publisher;
  explicit Impl(std::string name):interface(std::move(name)) {
    if(interface.empty() || interface.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")!=std::string::npos)
      throw std::invalid_argument("Explicit G1 network interface required");
  }
};
UnitreeBodyTransport::UnitreeBodyTransport(const std::string& name):impl_(std::make_unique<Impl>(name)) {}
UnitreeBodyTransport::~UnitreeBodyTransport()=default; // no automatic Stop/Release/Select.
void UnitreeBodyTransport::open_query_channel() {
  build_permission();
  if(impl_->switcher) throw std::logic_error("Query channel already open");
  unitree::robot::ChannelFactory::Instance()->Init(0,impl_->interface);
  impl_->switcher=std::make_unique<Switcher>(); impl_->switcher->SetTimeout(.1f); impl_->switcher->Init();
}
ModeReply UnitreeBodyTransport::query_mode() {
  build_permission(); if(!impl_->switcher) throw std::logic_error("Query channel missing");
  ModeReply result; result.status=impl_->switcher->CheckMode(result.form,result.name); return result;
}
int UnitreeBodyTransport::release_mode() {
  build_permission(); if(!impl_->switcher) throw std::logic_error("Query channel missing");
  return impl_->switcher->ReleaseMode();
}
void UnitreeBodyTransport::open_body_publisher() {
  build_permission(); if(!impl_->switcher || impl_->publisher) throw std::logic_error("Publisher initialization phase");
  impl_->publisher=std::make_unique<Publisher>("rt/lowcmd"); impl_->publisher->InitChannel();
}
bool UnitreeBodyTransport::write_body(uint8_t machine,const MotorValues& values) {
  build_permission(); if(!impl_->publisher) throw std::logic_error("Body publisher missing");
  for(size_t i=0;i<29;i++) {
    for(double value:{values.q[i],values.dq[i],values.tau[i],values.kp[i],values.kd[i]})
      if(!std::isfinite(value) || std::abs(value)>std::numeric_limits<float>::max())
        throw std::invalid_argument("Invalid float32 SDK motor value");
    if(values.kp[i]<0 || values.kd[i]<0) throw std::invalid_argument("Negative SDK gain");
  }
  static_assert(std::is_trivially_copyable<Command>::value);
  static_assert(sizeof(Command)==1004);
  alignas(Command) std::array<unsigned char,sizeof(Command)> backing{};
  auto *command=new(backing.data()) Command;
  if(reinterpret_cast<unsigned char*>(&command->crc())-backing.data()!=sizeof(Command)-4)
    throw std::logic_error("SDK CRC native layout changed");
  command->mode_pr()=0; command->mode_machine()=machine;
  for(size_t i=0;i<29;i++) {
    auto &motor=command->motor_cmd()[i]; motor.mode()=1;
    motor.q()=static_cast<float>(values.q[i]); motor.dq()=static_cast<float>(values.dq[i]);
    motor.tau()=static_cast<float>(values.tau[i]); motor.kp()=static_cast<float>(values.kp[i]);
    motor.kd()=static_cast<float>(values.kd[i]);
  }
  // Six unused body slots/reserve/padding remain zero. No Dex3/PIKA publishing.
  std::array<uint32_t,sizeof(Command)/4> words{}; std::memcpy(words.data(),command,sizeof(Command));
  command->crc()=crc32_core(words.data(),words.size()-1);
  bool result=impl_->publisher->Write(*command,0); command->~Command(); return result;
}
int UnitreeBodyTransport::select_mode(const std::string& name) {
  build_permission(); if(!impl_->switcher || name.empty()) throw std::logic_error("Explicit prior mode required");
  return impl_->switcher->SelectMode(name);
}
void UnitreeBodyTransport::close_body_publisher() {
  build_permission();
  if(impl_->publisher) {impl_->publisher->CloseChannel(); impl_->publisher.reset();}
}
}
