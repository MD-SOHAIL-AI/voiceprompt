"""Read-only JSON-RPC health checks for the three configured free UI MCPs."""
import concurrent.futures
import json
import queue
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVERS = {
    'playwright': ['@playwright/mcp@0.0.83', '--headless', '--browser=msedge'],
    'shadcn': ['shadcn@4.22.1', 'mcp'],
    'context7': ['@upstash/context7-mcp@4.4.4'],
}


def check(name, args):
    cache = ['--cache', str(Path.home() / '.codex/mcp-cache/context7')] if name == 'context7' else []
    process = subprocess.Popen(['cmd.exe', '/d', '/c', 'npx.cmd', *cache, '-y', *args],
                               cwd=ROOT / 'desktop', stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, encoding='utf-8', creationflags=0x08000000)
    messages = queue.Queue()

    def read():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                pass
    threading.Thread(target=read, daemon=True).start()

    def send(value):
        process.stdin.write(json.dumps(value) + '\n')
        process.stdin.flush()

    def request(serial, method, params):
        send({'jsonrpc': '2.0', 'id': serial, 'method': method, 'params': params})
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            value = messages.get(timeout=max(.1, deadline - time.monotonic()))
            if value.get('id') == serial:
                if 'error' in value:
                    raise RuntimeError(str(value['error']))
                return value['result']
        raise TimeoutError(method)

    try:
        hello = request(1, 'initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                        'clientInfo': {'name': 'VoicePrompt-readonly-check', 'version': '1'}})
        send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        catalog = request(2, 'tools/list', {})['tools']
        names = [item['name'] for item in catalog]
        tool, arguments = {
            'playwright': ('browser_tabs', {'action': 'list'}),
            'shadcn': ('get_project_registries', {}),
            'context7': ('resolve-library-id', {'libraryName': 'react', 'query': 'React useEffect cleanup documentation'}),
        }[name]
        if tool not in names:
            raise RuntimeError(f'Missing expected tool {tool}; available: {names}')
        result = request(3, 'tools/call', {'name': tool, 'arguments': arguments})
        if result.get('isError'):
            raise RuntimeError(str(result.get('content'))[:400])
        return {'server': name, 'ok': True, 'toolCount': len(names), 'readOnlyTool': tool,
                'version': hello.get('serverInfo', {}).get('version')}
    except Exception as exc:
        return {'server': name, 'ok': False, 'error': f'{type(exc).__name__}: {exc}'[:500]}
    finally:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)


if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda item: check(*item), SERVERS.items()))
    (ROOT / 'build').mkdir(exist_ok=True)
    (ROOT / 'build/ui-mcp-checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))
    raise SystemExit(0 if all(item['ok'] for item in results) else 1)
