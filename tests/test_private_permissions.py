import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent_memory as am


class PrivateMemoryTests(unittest.TestCase):
    def test_capture_merge_search_and_replacement_keep_private_modes_and_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            user = base / 'user'
            source = user / '.omp/agent/sessions/project/session.jsonl'
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps({'type':'message','id':'one','timestamp':'2026-09-05T10:00:00Z','message':{'role':'user','content':[{'type':'text','text':'literal synthetic text op://Example/item/field'}]}})+'\n')
            store = base / 'memory'
            env = {'HOME':str(user),'AGENT_MEMORY_HOME':str(store),'AGENT_MEMORY_HOST':'agent-box','AGENT_MEMORY_ROLE':'hub'}
            old = os.umask(0)
            try:
                with patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(am.main(['cycle']), 0)
                    original = (store/'memory.jsonl').read_bytes()
                    self.assertEqual(json.loads(original)['text'],'literal synthetic text op://Example/item/field')
                    for p in store.rglob('*'):
                        self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o700 if p.is_dir() else 0o600,str(p))
                    self.assertEqual(stat.S_IMODE(store.stat().st_mode),0o700)
                    (store/'logs/cycle.out.log').write_text('synthetic log\n')
                    (store/'logs/cycle.out.log').chmod(0o664)
                    (store/'out/agent-box.jsonl').chmod(0o664)
                    (store/'merge.sqlite').chmod(0o664)
                    (store/'in/legacy.jsonl').write_text(json.dumps({'key':'legacy/one','text':'legacy synthetic record','host':'legacy','role':'user','runtime':'omp'})+'\n')
                    (store/'in/legacy.jsonl').chmod(0o644)
                    # A new record exercises SQLite replacement without changing old text.
                    with source.open('a') as f:
                        f.write(json.dumps({'type':'message','id':'two','timestamp':'2026-09-05T10:01:00Z','message':{'role':'assistant','content':[{'type':'text','text':'second synthetic record'}]}})+'\n')
                    self.assertEqual(am.main(['cycle']),0)
                    self.assertTrue((store/'memory.jsonl').read_bytes().startswith(original))
                    for p in store.rglob('*'):
                        self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o700 if p.is_dir() else 0o600,str(p))
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(am.main(['search','literal synthetic']),0)
                    self.assertIn('literal synthetic',output.getvalue())
                    before = (store/'memory.jsonl').read_bytes()
                    self.assertEqual(am.main(['cycle']),0)
                    self.assertEqual((store/'memory.jsonl').read_bytes(),before)
            finally:
                self.assertEqual(os.umask(old),0)

    def test_rsync_keeps_private_modes_even_from_permissive_sender(self):
        if not Path('/usr/bin/rsync').exists(): self.skipTest('rsync unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary); src=base/'source'; dest=base/'dest'
            src.mkdir(); dest.mkdir()
            p=src/'memory.jsonl'; p.write_text('synthetic\n'); p.chmod(0o666)
            self.assertEqual(am.rsync_cmd([],str(p),str(dest/'memory.jsonl'))[0],0)
            self.assertEqual((dest/'memory.jsonl').read_text(),'synthetic\n')
            self.assertEqual(stat.S_IMODE((dest/'memory.jsonl').stat().st_mode),0o600)
            (dest/'memory.jsonl').chmod(0o664)
            self.assertEqual(am.rsync_cmd([],str(p),str(dest/'memory.jsonl'))[0],0)
            self.assertEqual(stat.S_IMODE((dest/'memory.jsonl').stat().st_mode),0o600)

    def test_unsafe_links_are_rejected_before_truncation(self):
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/'target'; target.write_text('keep this')
            for kind in ['symbolic','hard']:
                link=Path(temporary)/kind
                link.symlink_to(target) if kind=='symbolic' else os.link(target,link)
                with self.assertRaises(OSError): am.private_open(str(link),os.O_WRONLY|os.O_TRUNC)
                self.assertEqual(target.read_text(),'keep this')
                link.unlink()


class CodeOnlyInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.base=Path(self.temp.name)
        self.user=self.base/'user'; self.bundle=self.base/'bundle'; self.bundle.mkdir()
        shutil.copyfile(ROOT/'install.sh',self.bundle/'install.sh')
        self.previous=b'print("old collector")\n'; self.desired=b'print("new collector")\n'
        (self.bundle/'agent_memory.py').write_bytes(self.desired)
        self.target=self.user/'.local/lib/agent-memory/agent_memory.py'
        self.target.parent.mkdir(parents=True); self.target.write_bytes(self.previous); self.target.chmod(0o755)
        self.wrapper=self.user/'.local/bin/agent-memory'; self.wrapper.parent.mkdir(parents=True)
        self.wrapper.write_text('#!/bin/sh\nexec /usr/bin/python3 '+str(self.target)+' "$@"\n'); self.wrapper.chmod(0o755)
        (self.user/'.local/share/agent-memory').mkdir(parents=True)
        self.service=self.user/'Library/LaunchAgents/existing.plist'; self.service.parent.mkdir(parents=True); self.service.write_text('preserve schedule')

    def tearDown(self): self.temp.cleanup()

    def install(self, expected=None):
        env=dict(os.environ,HOME=str(self.user),AGENT_MEMORY_EXPECTED_SHA256=expected or hashlib.sha256(self.previous).hexdigest())
        return subprocess.run(['/bin/sh',str(self.bundle/'install.sh'),'--code-only'],env=env,capture_output=True,text=True)

    def test_upgrade_is_atomic_idempotent_and_reversible_without_launcher_changes(self):
        wrapper=self.wrapper.read_bytes(); service=self.service.read_bytes(); old_inode=self.target.stat().st_ino
        result=self.install(); self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.target.read_bytes(),self.desired); self.assertNotEqual(self.target.stat().st_ino,old_inode)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode),0o755)
        inode=self.target.stat().st_ino
        result=self.install(); self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.target.stat().st_ino,inode)
        backups=list(self.target.parent.glob('.code-only-backup-*')); self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),self.previous)
        (self.bundle/'agent_memory.py').write_bytes(self.previous)
        self.assertEqual(self.install(hashlib.sha256(self.desired).hexdigest()).returncode,0)
        self.assertEqual(self.target.read_bytes(),self.previous)
        self.assertEqual(self.wrapper.read_bytes(),wrapper); self.assertEqual(self.service.read_bytes(),service)

    def test_missing_installation_and_unexpected_code_are_not_modified(self):
        self.assertNotEqual(self.install('0'*64).returncode,0)
        self.assertEqual(self.target.read_bytes(),self.previous)
        self.wrapper.unlink()
        self.assertNotEqual(self.install().returncode,0)
        self.assertFalse(self.wrapper.exists()); self.assertEqual(self.target.read_bytes(),self.previous)


if __name__=='__main__': unittest.main()
