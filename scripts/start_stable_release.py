"""Start an explicitly requested stable release after successful main CI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

REPOSITORY = 'MD-SOHAIL-AI/voiceprompt'
ROOT = Path(__file__).resolve().parents[1]


def requested_commit(event):
    run = event.get('workflow_run', {})
    if (event.get('repository', {}).get('full_name') != REPOSITORY
            or run.get('head_repository', {}).get('full_name') != REPOSITORY
            or run.get('event') != 'push' or run.get('head_branch') != 'main'
            or run.get('status') != 'completed' or run.get('conclusion') != 'success'
            or '[publish-stable]' not in run.get('head_commit', {}).get('message', '')):
        raise ValueError('A marked, successful main push from this repository is required.')
    sha = run.get('head_sha', '')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('The verified source commit is invalid.')
    return sha


def run(command, root):
    return subprocess.run(command, cwd=root, check=True, capture_output=True,
                          text=True).stdout.strip()


def start(event, root=ROOT):
    sha = requested_commit(event)
    if run(['git', 'rev-parse', 'HEAD'], root) != sha:
        raise ValueError('The checkout does not match the completed CI run.')
    run(['git', 'merge-base', '--is-ancestor', sha, 'origin/main'], root)
    version = re.search(r'^version = "([^"]+)"',
                        (root / 'pyproject.toml').read_text(), re.M)[1]
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Only a stable application version can request publication.')
    if not (root / f'docs/release-notes-{version}.md').is_file():
        raise ValueError('Stable release notes are required.')
    run([sys.executable, 'scripts/verify_versions.py'], root)
    tag = f'v{version}'
    ref = f'refs/tags/{tag}'
    existing = json.loads(run(['gh', 'api',
        f'repos/{REPOSITORY}/git/matching-refs/tags/{tag}'], root))
    matches = [item for item in existing if item['ref'] == ref]
    if matches:
        target = matches[0].get('object', {})
        if len(matches) != 1 or target.get('type') != 'commit' or target.get('sha') != sha:
            raise ValueError('The release tag already belongs to another object. Never retag it.')
    else:
        created = json.loads(run(['gh', 'api', '--method', 'POST',
            f'repos/{REPOSITORY}/git/refs', '-f', f'ref={ref}', '-f', f'sha={sha}'], root))
        if (created.get('ref') != ref or created.get('object', {}).get('type') != 'commit'
                or created.get('object', {}).get('sha') != sha):
            raise ValueError('GitHub did not confirm the exact requested release tag.')
    # GITHUB_TOKEN tag pushes do not trigger another workflow. Dispatch explicitly;
    # the release still validates the tag and requires its production review.
    run(['gh', 'workflow', 'run', 'release.yml', '--repo', REPOSITORY, '--ref', tag], root)
    print(f'Started the guarded stable release for {tag} at {sha}.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', type=Path, required=True)
    options = parser.parse_args()
    try:
        start(json.loads(options.event.read_text(encoding='utf-8')))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'Stable release request failed: {error}', file=sys.stderr)
        raise SystemExit(1)
