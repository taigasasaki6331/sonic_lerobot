"""Compile fake adapter tests and SDK bindings; never links/executes SDK IO."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from lowcmd_preview import SDK,INCLUDE,PINNED
from sonic_startup_ablation import sha

TRANSPORT_PINNED={
    'unitree/robot/channel/channel_publisher.hpp':'95a2bbdc8ab46ea6ab70f4609340dac33cee3b5bb336f41ac8be08fbc2bb1026',
    'unitree/robot/channel/channel_factory.hpp':'e0568b06205599de89543c8c11459660ecf9dc6203bf43a778b25afaf5a2d529',
    'unitree/robot/b2/motion_switcher/motion_switcher_client.hpp':'84336c912c9776afc2314b74f9e67ff10a1856747f2914289f89f3c07c942407',
}


class Tests(unittest.TestCase):
    def test_fake_transport_contract_release_publish_stop_restore(self):
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='g1-body-adapter-') as tmp:
            binary=Path(tmp)/'test'
            subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror',str(source/'check_body_io_adapter.cpp'),
                '-o',str(binary)],check=True,timeout=15)
            report=json.loads(subprocess.check_output([str(binary)],timeout=3))
        self.assertEqual(report['fake_transport_checks'],19)
        self.assertFalse(report['robot_commands_sent']); self.assertFalse(report['physical_stop_confirmed'])
    def test_actual_SDK_binding_API_compiles_in_both_gated_builds_without_execution(self):
        for name,digest in {**PINNED,**TRANSPORT_PINNED}.items(): self.assertEqual(sha(INCLUDE/name),digest)
        source=Path(__file__).resolve().parent
        # Syntax/object compilation only: no SDK linking, construction or IO.
        with tempfile.TemporaryDirectory(prefix='g1-sdk-object-') as tmp:
            for gate in ('0','1'):
                subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-c','-DG1_PIKA_ENABLE_BODY_IO='+gate,
                    '-I'+str(INCLUDE),'-I'+str(SDK/'thirdparty/include'),'-I'+str(SDK/'thirdparty/include/ddscxx'),
                    str(source/'unitree_body_transport.cpp'),'-o',str(Path(tmp)/('body-'+gate+'.o'))],
                    check=True,timeout=30)


if __name__=='__main__': unittest.main()
