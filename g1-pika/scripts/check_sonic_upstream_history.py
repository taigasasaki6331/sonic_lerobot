"""Execute pinned upstream history gatherers without constructing G1Deploy.

Only mock the logger storage; this does not test its time interpolation or DDS.
Extracted functions retain upstream Apache-2.0 licensing (vendor LICENSE).
"""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonic_observation import ObservationBuilder, UPSTREAM


def function(source, name):
    start = source.index('    bool '+name+'(')
    # These gatherers contain no braces inside string literals or comments.
    opening = source.index(' {\n', start) + 1
    depth = 1
    for end in range(opening+1, len(source)):
        depth += (source[end] == '{') - (source[end] == '}')
        if depth == 0:
            return source[start:end+1]
    raise ValueError('Unterminated upstream function')


class Tests(unittest.TestCase):
    def test_encoder_reference_slots(self):
        base = UPSTREAM/'gear_sonic_deploy/src/g1/g1_deploy_onnx_ref'
        raw = (base/'src/g1_deploy_onnx_ref.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '6fa5594c372e89b4df6fe8f49114225dbfa77c2088abaddf04c555657cb1300c')
        methods=['GatherMotionJointPositionsMultiFrame','GatherMotionJointVelocitiesMultiFrame',
                 'GatherMotionAnchorOrientationMutiFrame']
        code='''
#include "math_utils.hpp"
#include "policy_parameters.hpp"
#include <algorithm>
#include <iostream>
#include <iomanip>
#include <vector>
struct Entry { std::array<double,4> base_quat; };
struct Logger { Entry entry;
  std::vector<Entry> GetLatest(size_t n,double dt) { return {entry}; }
};
struct Motion {
  size_t timesteps=10;
  std::array<std::array<double,29>,10> q,dq;
  std::array<std::array<std::array<double,4>,1>,10> quat;
  size_t GetNumJoints() { return 29; }
  size_t GetNumBodyQuaternions() { return 1; }
  const double* JointPositions(int i) { return q[i].data(); }
  const double* JointVelocities(int i) { return dq[i].data(); }
  auto BodyQuaternions(int i) { return quat[i]; }
};
struct Gatherer {
  Motion* current_motion_; Logger* state_logger_;
  double control_dt_=.02; int current_frame_=0;
  int saved_frame_for_observation_window_=0;
  bool has_upper_body_data_=false;
  std::array<double,17> upper_body_joint_positions_buffer_{},upper_body_joint_velocities_buffer_{};
  struct { bool play=true; } operator_state;
  std::array<double,4> ComputeApplyDeltaHeading() {return {1.,0.,0.,0.};}
'''+ '\n'.join(function(raw.decode(), name) for name in methods)+'''
};
int main() {
  std::cout<<std::setprecision(17); int count; std::cin>>count;
  for(int s=0;s<count;++s) {
    Motion motion; Logger logger;
    for(auto& x:logger.entry.base_quat) std::cin>>x;
    for(int f=0;f<10;++f) {
      std::array<double,29> q,dq;
      for(auto& x:q) std::cin>>x;
      for(auto& x:dq) std::cin>>x;
      for(auto& x:motion.quat[f][0]) std::cin>>x;
      for(int j=0;j<29;++j) {
        motion.q[f][j]=q[mujoco_to_isaaclab[j]];
        motion.dq[f][j]=dq[mujoco_to_isaaclab[j]];
      }
    }
    Gatherer g{&motion,&logger}; std::vector<double> out(1247,0.);
    if(!g.GatherMotionJointPositionsMultiFrame(out,4,10,1) ||
       !g.GatherMotionJointVelocitiesMultiFrame(out,294,10,1) ||
       !g.GatherMotionAnchorOrientationMutiFrame(out,584,10,1)) return 2;
    for(auto x:out) std::cout<<static_cast<float>(x)<<' ';
    std::cout<<'\\n';
  }
  return std::cin.fail()?1:0;
}
'''
        rng=np.random.default_rng(421); builder=ObservationBuilder()
        inputs=[]; expected=[]
        for _ in range(32):
            q=rng.normal(size=(10,29)); dq=rng.normal(size=(10,29))
            quat=rng.normal(size=(10,4)); quat/=np.linalg.norm(quat,axis=1)[:,None]
            current=rng.normal(size=4); current/=np.linalg.norm(current)
            inputs.append(np.concatenate([current,np.concatenate([q,dq,quat],axis=1).ravel()]))
            expected.append(builder.encoder(q,dq,quat,current))
        with tempfile.TemporaryDirectory(prefix='sonic-ref-gather-') as tmp:
            source=Path(tmp)/'oracle.cpp'; source.write_text(code); binary=Path(tmp)/'oracle'
            subprocess.run(['g++','-std=c++17','-O2','-I'+str(base/'include'),
                            str(source),'-o',str(binary)],check=True,timeout=30)
            result=subprocess.run([str(binary)],input='32\n'+'\n'.join(
                ' '.join(map(str,row)) for row in inputs),text=True,
                capture_output=True,check=True,timeout=10)
        actual=np.asarray([[float(v) for v in line.split()] for line in result.stdout.splitlines()])
        np.testing.assert_allclose(actual,np.asarray(expected).astype(float),rtol=0,atol=1e-7)

    def test_all_decoder_history_slots(self):
        base = UPSTREAM/'gear_sonic_deploy/src/g1/g1_deploy_onnx_ref'
        raw = (base/'src/g1_deploy_onnx_ref.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '6fa5594c372e89b4df6fe8f49114225dbfa77c2088abaddf04c555657cb1300c')
        methods = ['GatherHisBaseAngularVelocity', 'GatherHisBodyJointPositions',
                   'GatherHisBodyJointVelocities', 'GatherHisLastActions', 'GatherHisGravityDir']
        code = '''
#include "math_utils.hpp"
#include "policy_parameters.hpp"
#include <algorithm>
#include <iostream>
#include <iomanip>
#include <vector>
struct Entry {
  std::vector<double> body_q,body_dq,last_action;
  std::array<double,4> base_quat;
  std::array<double,3> base_ang_vel;
};
struct Logger {
  std::vector<Entry> rows;
  std::vector<Entry> GetLatest(size_t n,double dt,bool newest) {
    if(n!=10 || dt!=.02 || newest) throw 1;
    return rows;
  }
};
struct Gatherer {
  Logger* state_logger_;
  double control_dt_=.02;
'''+ '\n'.join(function(raw.decode(), name) for name in methods)+'''
};
int main() {
  std::cout<<std::setprecision(17);
  int count; std::cin>>count;
  for(int sample=0;sample<count;++sample) {
    Logger logger;
    for(int f=0;f<10;++f) {
      Entry e; e.body_q.resize(29);e.body_dq.resize(29);e.last_action.resize(29);
      std::array<double,29> q,dq;
      for(auto& v:q) std::cin>>v;
      for(auto& v:dq) std::cin>>v;
      for(auto& v:e.base_ang_vel) std::cin>>v;
      for(auto& v:e.base_quat) std::cin>>v;
      for(auto& v:e.last_action) std::cin>>v;
      for(int i=0;i<29;++i) {
        e.body_q[i]=q[mujoco_to_isaaclab[i]]-default_angles[mujoco_to_isaaclab[i]];
        e.body_dq[i]=dq[mujoco_to_isaaclab[i]];
      }
      logger.rows.push_back(e);
    }
    Gatherer gather{&logger}; std::vector<double> out(930);
    if(!gather.GatherHisBaseAngularVelocity(out,0,10) ||
       !gather.GatherHisBodyJointPositions(out,30,10) ||
       !gather.GatherHisBodyJointVelocities(out,320,10) ||
       !gather.GatherHisLastActions(out,610,10) ||
       !gather.GatherHisGravityDir(out,900,10)) return 2;
    for(auto v:out) std::cout<<static_cast<float>(v)<<' ';
    std::cout<<'\\n';
  }
  return std::cin.fail()?1:0;
}
'''
        rng = np.random.default_rng(20260924)
        builder = ObservationBuilder()
        inputs=[]; expected=[]
        for _ in range(32):
            q=rng.normal(size=(10,29)); dq=rng.normal(size=(10,29))
            gyro=rng.normal(size=(10,3)); quat=rng.normal(size=(10,4))
            quat/=np.linalg.norm(quat,axis=1)[:,None]
            actions=rng.normal(size=(10,29))
            inputs.append(np.concatenate([q,dq,gyro,quat,actions],axis=1).ravel())
            expected.append(builder.decoder_tail(q,dq,gyro,quat,actions))
        with tempfile.TemporaryDirectory(prefix='sonic-gather-') as tmp:
            source=Path(tmp)/'oracle.cpp'; source.write_text(code)
            binary=Path(tmp)/'oracle'
            subprocess.run(['g++','-std=c++17','-O2','-I'+str(base/'include'),
                            str(source),'-o',str(binary)],check=True,timeout=30)
            result=subprocess.run([str(binary)],input='32\n'+'\n'.join(
                ' '.join(map(str,row)) for row in inputs),text=True,
                capture_output=True,check=True,timeout=10)
        actual=np.asarray([[float(v) for v in line.split()] for line in result.stdout.splitlines()])
        np.testing.assert_array_equal(actual,np.asarray(expected).astype(float))


if __name__ == '__main__': unittest.main()
