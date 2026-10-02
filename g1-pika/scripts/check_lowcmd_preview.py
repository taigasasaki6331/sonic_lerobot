"""Actual pinned data-class layout/CRC checks, without SDK transport."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from lowcmd_preview import binary, preview, crc_words


def command():
    return dict(schema='abstract_29_joint_record_NOT_Unitree_LowCmd',hardware_output_enabled=False,
        robot_commands_sent=False,writer_seq=0,q=[i*.01 for i in range(29)],dq=[0.]*29,tau=[0.]*29,kp=[10.]*29,kd=[1.]*29)


class Tests(unittest.TestCase):
    def test_layout_reserved_slots_crc_and_determinism(self):
        with binary() as executable:
            result=preview([command(),command()],fixture_machine_id=7,executable=executable)
        self.assertEqual(result[0],result[1])
        self.assertEqual(result[0]['size_bytes'],1004)
        self.assertIs(result[0]['robot_commands_sent'],False)
        self.assertEqual(result[0]['mode_machine_source'],'fixture_only_NOT_detected_robot_id')

    def test_bad_modes_or_numbers_rejected_before_compiler_or_process(self):
        for key,value in (('hardware_output_enabled',True),('robot_commands_sent',True),('schema','LowCmd'),
                          ('q',[float('nan')]*29),('q',[1e39]*29),('kd',[-1.]*29)):
            row=command(); row[key]=value
            with self.assertRaises(ValueError): preview([row],fixture_machine_id=0,executable=None)
        for value in (True,-1,256,'0'):
            with self.assertRaises(ValueError): preview([command()],fixture_machine_id=value,executable=None)

    def test_crc_word_boundary_and_empty_seed(self):
        self.assertEqual(crc_words(b''),0xffffffff)
        with self.assertRaises(ValueError): crc_words(b'\0')


if __name__=='__main__': unittest.main()
