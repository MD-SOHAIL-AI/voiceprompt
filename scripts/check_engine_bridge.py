"""Exercise the real source/frozen sidecar with disposable, credential-free data."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]


class Client:
    def __init__(self, command, profile):
        environment = dict(os.environ, VOICEPROMPT_ACCEPTANCE_DIR=str(profile))
        self.log_path = profile / 'engine-stderr.log'
        self.log = self.log_path.open('ab')
        self.process = subprocess.Popen(command, cwd=ROOT, env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
            creationflags=0x08000000 if os.name == 'nt' else 0)
        self.messages, self.serial, self.ready = queue.Queue(), 0, False
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except ValueError:
                self.messages.put({'invalid': True})
        self.messages.put({'eof': True})

    def request(self, method, **params):
        self.serial += 1
        value = {'version': 1, 'id': self.serial, 'method': method, 'params': params}
        self.process.stdin.write(json.dumps(value).encode('utf-8') + b'\n')
        self.process.stdin.flush()
        while True:
            reply = self.messages.get(timeout=30)
            if reply.get('eof'):
                raise RuntimeError('Engine exited: ' + self.log_path.read_text(encoding='utf-8', errors='replace')[-3500:])
            if reply.get('event') == 'fatal':
                raise RuntimeError(reply['payload']['message'])
            assert not reply.get('invalid'), 'stdout contained non-protocol data'
            if reply.get('id') == self.serial:
                if not reply.get('ok'):
                    raise RuntimeError(reply['error']['message'])
                self.ready = True
                return reply['result']

    def close(self):
        try:
            if self.process.poll() is None and self.ready:
                self.request('shutdown')
            elif self.process.poll() is None:
                self.process.stdin.close()
            self.process.wait(timeout=8)
            assert self.process.returncode == 0, self.process.returncode
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            self.log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path)
    args = parser.parse_args()
    profile = ROOT / '.tools' / ('bridge-profile-' + uuid.uuid4().hex)
    subprocess.run([sys.executable, str(ROOT / 'scripts/create_acceptance_profile.py'), str(profile)], check=True)
    command = [str(args.engine.resolve()), '--desktop-sidecar'] if args.engine else [sys.executable, '-u', '-m', 'voiceprompt.desktop_sidecar']
    client = Client(command, profile)
    try:
        state = client.request('bootstrap')
        assert state['version'] == 1 and state['runtime']['acceptanceProfile']
        assert state['credentials'] == {'gemini': False, 'openrouter': False}
        assert state['planner'] is not None, state['runtime']['plannerError']
        client.request('planner.task.save', title='Persistent bridge task', notes='Disposable integration fixture')
        client.request('planner.timer.start', title='Bridge timer', seconds=120)
        timer = client.request('planner.snapshot')['timer']
        client.request('planner.timer.action', action='pause', session=timer['session'])
        assert client.request('planner.snapshot')['timer']['status'] == 'paused'
        try:
            client.request('planner.timer.action', action='cancel', session='stale')
        except RuntimeError:
            pass
        else:
            raise AssertionError('Stale timer action was accepted')
        client.request('planner.timer.action', action='resume', session=timer['session'])
        client.request('planner.timer.action', action='cancel', session=timer['session'])
        try:
            client.request('credential.save', provider='gemini', key='fixture-not-a-key')
        except RuntimeError:
            pass
        else:
            raise AssertionError('Acceptance profile accessed credentials')
    finally:
        client.close()
    restarted = Client(command, profile)
    try:
        state = restarted.request('bootstrap')
        assert any(t['title'] == 'Persistent bridge task' for t in state['planner']['tasks'])
        assert state['planner']['timer']['status'] == 'cancelled'
    finally:
        restarted.close()
    result = {'mode': 'frozen' if args.engine else 'source', 'passed': True,
              'checks': ['Real bootstrap', 'Credential isolation', 'Task persistence after restart',
                         'Timer pause/resume/end', 'Stale action rejection', 'Graceful shutdown']}
    (ROOT / 'build').mkdir(exist_ok=True)
    (ROOT / 'build' / ('frozen-bridge.json' if args.engine else 'source-bridge.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
