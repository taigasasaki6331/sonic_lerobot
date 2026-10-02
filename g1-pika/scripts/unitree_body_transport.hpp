// Actual SDK bindings, BUILD-ONLY in current record-only project. No launcher.
#pragma once
#include "body_io_adapter.hpp"
#include <memory>

namespace g1_pika {
class UnitreeBodyTransport final:public Transport {
  struct Impl;
  std::unique_ptr<Impl> impl_;
public:
  explicit UnitreeBodyTransport(const std::string& interface_name);
  ~UnitreeBodyTransport();
  void open_query_channel() override;
  ModeReply query_mode() override;
  int release_mode() override;
  void open_body_publisher() override;
  bool write_body(uint8_t machine,const MotorValues&) override;
  void close_body_publisher() override;
  int select_mode(const std::string&) override;
};
}
