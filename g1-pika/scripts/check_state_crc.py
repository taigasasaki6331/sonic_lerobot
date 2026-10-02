"""Offline canonical LowState layout/CRC vs pinned SDK C++ and Python; no DDS IO."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from lowcmd_preview import SDK,INCLUDE,crc_words
from sonic_startup_ablation import sha

PINNED={
    'unitree/idl/hg/LowState_.hpp':'e01be29667100a6f2cd829b3ea8a90f846271b20a0cde96331ceecfb4d46e042',
    'unitree/idl/hg/IMUState_.hpp':'0b078db5401a35c2421190adb98c0a7e94472ee798b20aa4d1a345513dc88b1b',
    'unitree/idl/hg/MotorState_.hpp':'9a461ce785c1d56e95c284065178935288d04fd3261090983ab0fd0c2c6d8f0d',
    'unitree/dds_wrapper/common/crc.h':'3175e111c6f8e68b69bc08dffd34ee13e581a83c81d537c41411f5a544afcb34',
}


def export_oracle(destination):
    destination=Path(destination); source=Path(__file__).resolve().parent/'state_receiver'
    for name,digest in PINNED.items():
        if sha(INCLUDE/name)!=digest: raise ValueError('Fixed state data/CRC changed: '+name)
    for name,digest in json.loads((source/'generated/manifest.json').read_bytes())['sha256'].items():
        if sha(source/name)!=digest: raise ValueError('Generated receiver source changed: '+name)
    license_text='/*\n'+(SDK/'LICENSE').read_text()+'\n*/\n'
    for name in ('IMUState','MotorState','LowState'):
        text=(INCLUDE/('unitree/idl/hg/'+name+'_.hpp')).read_text()
        marker='\n#include "dds/topic/TopicTraits.hpp"'
        if text.count(marker)!=1: raise ValueError('SDK class-only extraction changed')
        text=text.split(marker)[0]+'\n#endif\n'
        for dependency in ('IMUState','MotorState'):
            text=text.replace('"unitree/idl/hg/'+dependency+'_.hpp"','"'+dependency+'_data.hpp"')
        (destination/(name+'_data.hpp')).write_text(license_text+text)
    (destination/'crc.h').write_bytes((INCLUDE/'unitree/dds_wrapper/common/crc.h').read_bytes())
    (destination/'LICENSE.unitree').write_bytes((SDK/'LICENSE').read_bytes())
    for src,name in ((source/'generated/State.h','State.h'),(source/'state_crc.h','state_crc.h'),
                     (source/'check_state_crc.cpp','check_state_crc.cpp')):
        (destination/name).write_bytes(src.read_bytes())


def verify_native(output):
    rows=output.splitlines()
    if len(rows)!=128: raise ValueError('Expected 128 full state fixtures')
    for row in rows:
        data=bytes.fromhex(row.decode())
        if len(data)!=2092 or crc_words(data[:-4])!=int.from_bytes(data[-4:],'little'):
            raise ValueError('State size/independent CRC mismatch')
    return len(rows)


class Tests(unittest.TestCase):
    def test_C_layout_SDK_CRC_padding_corruption_and_python_oracle(self):
        with tempfile.TemporaryDirectory(prefix='g1-state-crc-') as folder:
            path=Path(folder); export_oracle(path); executable=path/'oracle'
            subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I'+str(path),
                '-I'+str(SDK/'thirdparty/include'),str(path/'check_state_crc.cpp'),'-o',str(executable)],
                check=True,timeout=30)
            result=subprocess.check_output([str(executable)],timeout=5)
            self.assertEqual(verify_native(result),128)
            # Receiver still compiles as C; no library load/DDS calls executed.
            subprocess.run(['gcc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror',
                '-I'+str(SDK/'thirdparty/include'),'-I'+str(Path(__file__).parent/'state_receiver/generated'),'-fsyntax-only',
                str(Path(__file__).parent/'state_receiver/receive_state.c')],check=True,timeout=15)
    def test_independent_oracle_rejects_corrupt_or_incomplete_output(self):
        with self.assertRaises(ValueError): verify_native(b'00\n')


if __name__=='__main__': unittest.main()
