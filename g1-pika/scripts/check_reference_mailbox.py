from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from reference_mailbox import ReferenceMailbox


class Tests(unittest.TestCase):
    def publish(self,mailbox,seq=0,issued=0.,finished=.01):
        mailbox.publish(session='s',seq=seq,issued_at=issued,finished_at=finished,reference={'absolute_target':[1,2,3]})
    def test_hold_not_integrate(self):
        mailbox=ReferenceMailbox('s',.1); self.publish(mailbox)
        a=mailbox.read(.02); b=mailbox.read(.04)
        self.assertEqual(a['reference'],b['reference'])
        a['reference']['absolute_target'][0]=999
        self.assertEqual(mailbox.read(.06)['reference']['absolute_target'][0],1)
    def test_newest(self):
        mailbox=ReferenceMailbox('s',.1); self.publish(mailbox)
        self.publish(mailbox,1,.033,.045)
        self.assertEqual(mailbox.read(.06)['seq'],1)
    def test_stale_latches(self):
        mailbox=ReferenceMailbox('s',.1); self.publish(mailbox)
        with self.assertRaises(ValueError): mailbox.read(.2)
        with self.assertRaises(RuntimeError): self.publish(mailbox,1,.2,.21)
    def test_duplicate(self):
        mailbox=ReferenceMailbox('s',.1); self.publish(mailbox)
        with self.assertRaises(ValueError): self.publish(mailbox)
    def test_slow_compute(self):
        mailbox=ReferenceMailbox('s',.1)
        with self.assertRaises(ValueError): self.publish(mailbox,finished=.11)
    def test_stop_and_empty(self):
        mailbox=ReferenceMailbox('s',.1); self.assertIsNone(mailbox.read(0.))
        mailbox.stop()
        with self.assertRaises(RuntimeError): mailbox.read(0.)


if __name__=='__main__': unittest.main()
