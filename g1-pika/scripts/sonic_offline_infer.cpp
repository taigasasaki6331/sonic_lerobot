// File-only encoder -> decoder runner. No SDK/DDS/socket initialization or linkage.
// Reuses upstream TRTInferenceEngine and motor mapping/constants unchanged.
#include "InferenceEngine.h"
#include "policy_parameters.hpp"
#include <nlohmann/json.hpp>
#include <cuda_runtime_api.h>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <chrono>
#include <algorithm>
#include <unistd.h>
#include <cstdio>

using json = nlohmann::json;

std::vector<float> infer(TRTInferenceEngine& engine, const std::vector<float>& input,
                         size_t expected_output, cudaStream_t stream) {
  const auto names=engine.GetInputTensorNames(), outputs=engine.GetOutputTensorNames();
  if(names.size()!=1 || outputs.size()!=1) throw std::runtime_error("Tensor count mismatch");
  std::vector<int64_t> dims;
  if(!engine.GetTensorShape(names[0],dims)) throw std::runtime_error("Missing input shape");
  size_t count=1; for(auto d:dims) {if(d<=0) throw std::runtime_error("Dynamic input unsupported"); count*=d;}
  if(count!=input.size()) throw std::runtime_error("Input size mismatch");
  if(!engine.GetTensorShape(outputs[0],dims)) throw std::runtime_error("Missing output shape");
  count=1; for(auto d:dims) {if(d<=0) throw std::runtime_error("Dynamic output unsupported"); count*=d;}
  if(count!=expected_output || engine.GetTensorDataType(names[0])!=DataType::FLOAT ||
      engine.GetTensorDataType(outputs[0])!=DataType::FLOAT) throw std::runtime_error("Tensor type/shape mismatch");
  for(float v:input) if(!std::isfinite(v)) throw std::runtime_error("Nonfinite input");
  engine.SetInputData(names[0],input.data(),input.size());
  if(!engine.Enqueue(stream) || cudaStreamSynchronize(stream)!=cudaSuccess)
    throw std::runtime_error("GPU inference failed");
  std::vector<float> result(expected_output);
  engine.GetOutputData(outputs[0],result.data(),result.size());
  for(float v:result) if(!std::isfinite(v)) throw std::runtime_error("Nonfinite output");
  return result;
}

void initialize(TRTInferenceEngine& encoder,TRTInferenceEngine& decoder,const char* enc,const char* dec) {
  Options options;
  std::string encoder_path,decoder_path;
  if(!ConvertONNXToTRT(options,enc,encoder_path)||!ConvertONNXToTRT(options,dec,decoder_path))
    throw std::runtime_error("Upstream model conversion failed");
  if(!encoder.Initialize(encoder_path,0)||!encoder.InitInputs()||!decoder.Initialize(decoder_path,0)||!decoder.InitInputs())
    throw std::runtime_error("Cannot initialize engine");
}

json infer_row(TRTInferenceEngine& encoder,TRTInferenceEngine& decoder,const json& row,
               cudaStream_t stream,std::vector<float>* history=nullptr) {
  const auto started=std::chrono::steady_clock::now();
  auto tokens=infer(encoder,row.at("encoder").get<std::vector<float>>(),64,stream);
  auto tail=row.at("decoder_tail").get<std::vector<float>>();
  if(tail.size()!=930) throw std::runtime_error("Expected 930 decoder history values");
  if(history) std::copy(history->begin(),history->end(),tail.begin()+610);
  std::vector<float> obs=tokens; obs.insert(obs.end(),tail.begin(),tail.end());
  auto action=infer(decoder,obs,29,stream);
  if(history) {
    std::rotate(history->begin(),history->begin()+29,history->end());
    std::copy(action.begin(),action.end(),history->end()-29);
  }
  std::vector<double> target(29);
  for(size_t i=0;i<29;i++) target[i]=action[isaaclab_to_mujoco[i]]*g1_action_scale[i]+default_angles[i];
  const double elapsed=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-started).count();
  json result={{"seq",row.at("seq")},{"token",tokens},{"raw_action_isaaclab",action},
               {"q_target_hardware",target},{"encoder_decoder_wall_ms",elapsed}};
  if(row.contains("gripper_width_m")) {
    const double width=row.at("gripper_width_m").get<double>();
    if(!std::isfinite(width)||width<0||width>.1) throw std::runtime_error("Invalid gripper width metadata");
    result["gripper_width_m"]=width; result["gripper_actuated"]=false;
  }
  return result;
}

int serve_stdio(const char* enc,const char* dec) {
  // Keep model/plugin logging on stderr, protocol JSON on the original stdout pipe.
  const int protocol_fd=dup(STDOUT_FILENO);
  if(protocol_fd<0 || dup2(STDERR_FILENO,STDOUT_FILENO)<0) throw std::runtime_error("Pipe setup failed");
  FILE* protocol=fdopen(protocol_fd,"w");
  if(!protocol) throw std::runtime_error("Protocol stream failed");
  auto send=[&](const json& value) {
    const auto line=value.dump()+"\n";
    if(fwrite(line.data(),1,line.size(),protocol)!=line.size() || fflush(protocol)!=0)
      throw std::runtime_error("Protocol write failed");
  };
  TRTInferenceEngine encoder,decoder;
  initialize(encoder,decoder,enc,dec);
  cudaStream_t stream;
  if(cudaStreamCreate(&stream)!=cudaSuccess) throw std::runtime_error("Cannot create CUDA stream");
  send({{"ready",true},{"mode","record_only"},{"hardware_output_enabled",false}});
  std::string line; int expected=0;
  while(std::getline(std::cin,line)) {
    if(line.size()>2000000) throw std::runtime_error("Oversized request");
    const auto request=json::parse(line);
    if(request.at("op")=="stop") {send({{"stopped",true}}); break;}
    if(request.at("op")!="infer" || !request.at("seq").is_number_integer() || request.at("seq")!=expected)
      throw std::runtime_error("Invalid inference request sequence");
    auto result=infer_row(encoder,decoder,request.at("row"),stream);
    send({{"seq",expected},{"result",result},{"hardware_output_enabled",false}});
    expected++;
    if(expected>=10000) throw std::runtime_error("Bounded request count exceeded");
  }
  cudaStreamDestroy(stream); fclose(protocol); return 0;
}

int main(int argc,char** argv) {
  try {
    if(argc==4 && std::string(argv[1])=="--stdio") return serve_stdio(argv[2],argv[3]);
    if(argc!=5 && argc!=6) throw std::runtime_error("Usage: offline encoder.onnx decoder.onnx input.json output.json [recurrent]");
    const bool recurrent=argc==6;
    if(recurrent && std::string(argv[5])!="recurrent") throw std::runtime_error("Unknown history mode");
    std::ifstream input(argv[3]); json request; input>>request;
    if(request.at("scope")!="diagnostic_repeated_snapshot_not_50hz_history" &&
       request.at("scope")!="diagnostic_real_body_history_zero_prior_actions")
      throw std::runtime_error("Unsupported request scope");
    if(recurrent && request.at("scope")!="diagnostic_real_body_history_zero_prior_actions")
      throw std::runtime_error("Recurrent diagnostic requires consecutive recorded body history");
    if(std::ifstream(argv[4]).good()) throw std::runtime_error("Output exists");
    TRTInferenceEngine encoder,decoder;
    // Upstream cache format has a 64-byte hash prefix: raw trtexec engines are incompatible.
    initialize(encoder,decoder,argv[1],argv[2]);
    cudaStream_t stream;
    if(cudaStreamCreate(&stream)!=cudaSuccess) throw std::runtime_error("Cannot create CUDA stream");
    json rows=json::array();
    std::vector<float> action_history(290,0.0f);
    int previous_seq=-1;
    for(const auto& row:request.at("frames")) {
      const int seq=row.at("seq").get<int>();
      if(recurrent && previous_seq>=0 && seq!=previous_seq+1)
        throw std::runtime_error("Gap in recurrent diagnostic sequence");
      previous_seq=seq;
      rows.push_back(infer_row(encoder,decoder,row,stream,recurrent?&action_history:nullptr));
    }
    cudaStreamDestroy(stream);
    json result={{"computation_completed",true},{"hardware_ready",false},{"robot_commands_sent",false},
      {"scope",request.at("scope")},{"source_sha256",request.at("source_sha256")},
      {"history",request.at("history")},{"reference",request.at("reference")},{"outputs",rows}};
    result["action_history_mode"]=recurrent?"prior_computed_outputs_zero_initialized_not_executed":"input_file";
    std::ofstream output(argv[4]); output<<result.dump(2)<<'\n';
    if(!output) throw std::runtime_error("Output write failed");
    return 0;
  } catch(const std::exception& e) {std::cerr<<e.what()<<'\n'; return 1;}
}
