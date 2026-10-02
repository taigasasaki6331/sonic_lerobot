"""Pinned motor constants and model bounds for a file-only lifecycle rehearsal."""
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from audit_motion_record import joint_limits, PARAMETERS, PARAMETERS_SHA, ROOT
from sonic_startup_ablation import sha, vector


def load_profile():
    if sha(PARAMETERS) != PARAMETERS_SHA: raise ValueError('Pinned motor constants changed')
    source = '''#include <vector>
#include <iostream>
#include <iomanip>
#include "policy_parameters.hpp"
int main(){std::cout<<std::setprecision(17);
for(auto v:default_angles)std::cout<<v<<' ';std::cout<<'\\n';
for(auto v:kps)std::cout<<v<<' ';std::cout<<'\\n';
for(auto v:kds)std::cout<<v<<' ';std::cout<<'\\n';}
'''
    with tempfile.TemporaryDirectory(prefix='g1-body-profile-') as directory:
        path = Path(directory)/'profile.cpp'; path.write_text(source); binary = Path(directory)/'profile'
        subprocess.run(['g++','-std=c++17','-O2','-I'+str(PARAMETERS.parent),str(path),'-o',str(binary)],check=True,timeout=30)
        lines = subprocess.check_output([str(binary)],text=True,timeout=5).splitlines()
    if len(lines) != 3: raise ValueError('Motor constant schema changed')
    values = {key:list(map(float,line.split())) for key,line in zip(('defaults','kp','kd'),lines)}
    for row in values.values(): vector(row,29)
    urdf = ROOT/'artifacts/models/g1_pika_closed.urdf'; limits = joint_limits(urdf)
    tree = ET.fromstring(urdf.read_bytes()); velocity = []
    for limit in limits:
        joint = next(j for j in tree.findall('joint') if j.get('name') == limit['name'])
        velocity.append(float(joint.find('limit').attrib['velocity']))
    vector(velocity,29)
    if any(v <= 0 for v in velocity): raise ValueError('Invalid model velocity limit')
    return dict(**values, names=[j['name'] for j in limits], lower=[j['lower_rad'] for j in limits],
                upper=[j['upper_rad'] for j in limits], velocity=velocity,
                source_parameters_sha256=PARAMETERS_SHA, source_urdf_sha256=sha(urdf))
