import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from recover_outputs import extract_outputs


class Tests(unittest.TestCase):
    def archive(self,folder,name='report.json',kind=None):
        path=Path(folder)/'input.tar.gz'
        with tarfile.open(path,'w:gz') as archive:
            member=tarfile.TarInfo(name); member.size=2
            if kind is not None: member.type=kind; member.linkname='/tmp/unrelated'
            archive.addfile(member,io.BytesIO(b'{}') if kind is None else None)
        return path

    def test_extract_and_identical_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=self.archive(folder); target=Path(folder)/'out'
            extract_outputs(archive,target); extract_outputs(archive,target)
            self.assertEqual((target/'report.json').read_bytes(),b'{}')

    def test_reject_paths_and_links(self):
        with tempfile.TemporaryDirectory() as folder:
            for name,kind in [('../outside',None),('/absolute',None),('link',tarfile.SYMTYPE),('hard',tarfile.LNKTYPE)]:
                archive=self.archive(folder,name,kind)
                with self.subTest(name=name),self.assertRaises(ValueError): extract_outputs(archive,Path(folder)/'out')

    def test_refuse_existing_changed_file(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=self.archive(folder); target=Path(folder)/'out'; target.mkdir()
            (target/'report.json').write_text('existing')
            with self.assertRaises(ValueError): extract_outputs(archive,target)
            self.assertEqual((target/'report.json').read_text(),'existing')


if __name__=='__main__': unittest.main()
