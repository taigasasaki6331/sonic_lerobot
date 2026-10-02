// File/stdio-only preview. Uses pinned Unitree BSD-3-Clause data classes/CRC.
// No SDK clients, DDS participants, publishers, mode switches or hand drivers.
#include "LowCmd_data.hpp"
#include "unitree/dds_wrapper/common/crc.h"
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <new>
#include <type_traits>

int main() {
  using Command = unitree_hg::msg::dds_::LowCmd_;
  static_assert(std::is_trivially_copyable<Command>::value);
  static_assert(sizeof(Command) % 4 == 0);
  if (__BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__) return 2;
  int machine;
  while (std::cin >> machine) {
    if (machine < 0 || machine > 255) return 2;
    // Zero backing storage before construction, including struct padding.
    alignas(Command) std::array<unsigned char, sizeof(Command)> storage{};
    auto* command = new (storage.data()) Command;
    command->mode_pr() = 0; // P/R as used by the pinned upstream writer.
    command->mode_machine() = static_cast<uint8_t>(machine);
    for (int i = 0; i < 29; ++i) {
      double value[5];
      for (auto& v : value) {
        if (!(std::cin >> v) || !std::isfinite(v) || std::abs(v) > std::numeric_limits<float>::max()) return 2;
      }
      if (value[3] < 0 || value[4] < 0) return 2;
      auto& motor = command->motor_cmd()[i];
      motor.mode() = 1; motor.q() = static_cast<float>(value[0]);
      motor.dq() = static_cast<float>(value[1]); motor.tau() = static_cast<float>(value[2]);
      motor.kp() = static_cast<float>(value[3]); motor.kd() = static_cast<float>(value[4]);
    }
    // Six unused body slots and all reserved fields remain disabled and zero.
    const auto offset = reinterpret_cast<unsigned char*>(&command->crc()) - storage.data();
    if (offset != sizeof(Command)-4) return 2;
    std::array<uint32_t, sizeof(Command)/4> words{};
    std::memcpy(words.data(), command, sizeof(Command));
    command->crc() = crc32_core(words.data(), words.size()-1);
    std::cout << std::hex << std::setfill('0');
    for (auto value : storage) std::cout << std::setw(2) << static_cast<unsigned>(value);
    std::cout << '\n' << std::dec;
    command->~Command();
  }
  return std::cin.eof() ? 0 : 2;
}
