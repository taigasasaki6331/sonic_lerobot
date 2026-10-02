// Data-only oracle: no DDS participant/client/publisher; SDK classes + CRC only.
#include "state_crc.h"
#include "LowState_data.hpp"
#include "crc.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <new>
#include <type_traits>

int main() {
  using State=unitree_hg::msg::dds_::LowState_;
  static_assert(std::is_trivially_copyable<State>::value);
  static_assert(sizeof(State)==sizeof(unitree_hg_msg_dds__LowState_));
  for(unsigned seed=0;seed<128;seed++) {
    unitree_hg_msg_dds__LowState_ input,canonical;
    std::memset(&input,0xa5,sizeof(input)); // DDS allocator padding must not leak.
    input.version[0]=seed; input.version[1]=seed+1;
    input.mode_pr=0; input.mode_machine=5; input.tick=0xfffffff0u+seed;
    for(int i=0;i<4;i++) input.imu_state.quaternion[i]=(float)(seed+i)/128.f;
    for(int i=0;i<3;i++) {
      input.imu_state.gyroscope[i]=-(float)(seed+i)/64.f;
      input.imu_state.accelerometer[i]=(float)(seed+i)/32.f;
      input.imu_state.rpy[i]=-(float)(seed+i)/256.f;
    }
    input.imu_state.temperature=(int16_t)(-200+(int)seed);
    for(int i=0;i<35;i++) {
      auto &s=input.motor_state[i];
      s.mode=(uint8_t)(seed+i); s.q=(float)((int)seed-i)/128.f;
      s.dq=-(float)(seed+i)/64.f; s.ddq=(float)(seed+i)/32.f;
      s.tau_est=-(float)(seed+i)/16.f; s.vol=(float)(seed+i)/8.f;
      for(int j=0;j<2;j++) {s.temperature[j]=(int16_t)(seed+i+j); s.sensor[j]=0x80000000u+seed+i+j;}
      s.motorstate=0xf0000000u+seed+i;
      for(int j=0;j<4;j++) s.reserve[j]=seed+i+j;
    }
    for(int i=0;i<40;i++) input.wireless_remote[i]=(uint8_t)(seed+i);
    for(int i=0;i<4;i++) input.reserve[i]=seed+i;
    input.crc=0;
    canonical_lowstate(&input,&canonical);
    alignas(State) std::array<unsigned char,sizeof(State)> backing{};
    State *sdk=new(backing.data()) State;
    std::copy(std::begin(input.version),std::end(input.version),sdk->version().begin());
    sdk->mode_pr()=input.mode_pr; sdk->mode_machine()=input.mode_machine; sdk->tick()=input.tick;
    auto &imu=sdk->imu_state();
    std::copy(std::begin(input.imu_state.quaternion),std::end(input.imu_state.quaternion),imu.quaternion().begin());
    std::copy(std::begin(input.imu_state.gyroscope),std::end(input.imu_state.gyroscope),imu.gyroscope().begin());
    std::copy(std::begin(input.imu_state.accelerometer),std::end(input.imu_state.accelerometer),imu.accelerometer().begin());
    std::copy(std::begin(input.imu_state.rpy),std::end(input.imu_state.rpy),imu.rpy().begin());
    imu.temperature()=input.imu_state.temperature;
    for(int i=0;i<35;i++) {
      auto &d=sdk->motor_state()[i]; const auto &s=input.motor_state[i];
      d.mode()=s.mode; d.q()=s.q; d.dq()=s.dq; d.ddq()=s.ddq; d.tau_est()=s.tau_est; d.vol()=s.vol;
      std::copy(std::begin(s.temperature),std::end(s.temperature),d.temperature().begin());
      std::copy(std::begin(s.sensor),std::end(s.sensor),d.sensor().begin());
      d.motorstate()=s.motorstate;
      std::copy(std::begin(s.reserve),std::end(s.reserve),d.reserve().begin());
    }
    std::copy(std::begin(input.wireless_remote),std::end(input.wireless_remote),sdk->wireless_remote().begin());
    std::copy(std::begin(input.reserve),std::end(input.reserve),sdk->reserve().begin());
    assert(std::memcmp(&canonical,sdk,sizeof(State))==0);
    std::array<uint32_t,sizeof(State)/4> words{};
    std::memcpy(words.data(),sdk,sizeof(State));
    auto crc=crc32_core(words.data(),words.size()-1);
    assert(crc==lowstate_crc32(&input));
    input.crc=crc; assert(lowstate_crc32(&input)==input.crc);
    input.motor_state[17].q+=.125f; assert(lowstate_crc32(&input)!=input.crc);
    input.motor_state[17].q-=.125f;
    input.crc^=1; assert(lowstate_crc32(&input)!=input.crc);
    // Emit canonical native bytes; Python independently verifies the CRC.
    sdk->crc()=crc;
    std::cout<<std::hex<<std::setfill('0');
    for(auto b:backing) std::cout<<std::setw(2)<<static_cast<unsigned>(b);
    std::cout<<'\n'<<std::dec;
    sdk->~State();
  }
}
