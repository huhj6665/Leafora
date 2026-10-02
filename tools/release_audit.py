"""Read-only publication audit. Reports locations, never credential values.

This is a heuristic check, not a guarantee that all confidential data is found.
Run with Python 3.10+ from a source checkout or a clean publication snapshot.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

EXCLUDED_DIRS = {
    '.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', '.idea', '.vscode', '.claude', '.codex',
    'dist', 'runtime', 'local', 'storage', 'outputs', 'test_images',
}
EXCLUDED_PATHS = {
    'prompts', 'docs/design', 'Web/frontend/src/assets/brand-explorations',
    'weixinapp/test/ui-preview', 'TLD_project/data/cache',
    'Web/scripts/mock_jetson/images',
}
EXCLUDED_FILES = {'AGENTS.md', 'PROJECT_STATUS.md', 'PROJECT_COORDINATION.md',
                  'project.private.config.json'}
BINARY_SUFFIXES = {'.pt', '.pth', '.onnx', '.engine', '.plan', '.db', '.sqlite',
                   '.sqlite3', '.pem', '.key', '.p12', '.pfx', '.crt', '.zip', '.7z'}
TEMP_SUFFIXES = {'.log', '.tmp', '.temp', '.bak', '.swp', '.pyc', '.pyo', '.tsbuildinfo'}
PRIVATE_PATTERNS = [
    ('provider-token', re.compile(r'(?:LTAI[\w]{12,}|AKIA[0-9A-Z]{16}|sk-[\w-]{20,}|gh[pousr]_[\w]{20,}|github_pat_[\w]{20,})')),
    ('private-key', re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ('personal-phone', re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')),
    ('personal-machine-path', re.compile(r'C:[/\\]+Users[/\\]+lenovo', re.I)),
    ('personal-wechat-appid', re.compile(r'wx[0-9a-f]{16}')),
]


def excluded(relative):
    parts = relative.parts
    path = relative.as_posix()
    name = relative.name
    if any(p in EXCLUDED_DIRS for p in parts) or name in EXCLUDED_FILES:
        return True
    if any(path == p or path.startswith(p + '/') for p in EXCLUDED_PATHS):
        return True
    if name in {'.env', 'device.env', '.DS_Store', 'Thumbs.db', 'desktop.ini'}:
        return True
    if name.startswith('.env.') and name != '.env.example':
        return True
    if name.startswith('~$') or (path.startswith('Web/docs/')
                               and name.endswith(('HANDOFF.md', 'REPORT.md'))):
        return True
    if relative.suffix.lower() in BINARY_SUFFIXES | TEMP_SUFFIXES:
        return True
    return path in {'Web/frontend/vite.config.js', 'Web/frontend/vite.config.d.ts'}


def source_files(root):
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        dirs[:] = [d for d in dirs if not excluded((base / d).relative_to(root))
                   and not (base / d).is_symlink()]
        for name in sorted(files):
            path = base / name
            if not excluded(path.relative_to(root)):
                yield path


def local_secrets(root):
    """Use local env values as fingerprints without printing or persisting them."""
    values = set()
    envs = [root / 'Web/backend/.env', root / 'Web/frontend/.env',
            root / 'Web/model_service/.env', root / 'Web/scripts/mock_jetson/.env',
            root / 'TLD_project/runtime/device.env']
    envs.extend((root / 'Web/local/device_credentials').glob('*.env'))
    key_pattern = re.compile(r'(?:PASSWORD|SECRET|API_KEY|ACCESS_KEY|SECURITY_CODE|TOKEN)', re.I)
    for path in envs:
        if not path.is_file():
            continue
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.partition('=')
            value = value.strip().strip('"\'')
            if sep and key_pattern.search(key) and len(value) >= 8:
                values.add(value)
    return values


def audit(root, fingerprints=()):
    findings, count, size = [], 0, 0
    for path in source_files(root):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            findings.append({'path': relative, 'rule': 'symlink'})
            continue
        count += 1
        size += path.stat().st_size
        if path.stat().st_size >= 100 * 1024 * 1024:
            findings.append({'path': relative, 'rule': 'github-file-size'})
        data = path.read_bytes()
        if b'\x00' in data[:8192]:
            continue
        try:
            content = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            continue
        # Test-only identities and passwords are fixtures, not real accounts.
        for number, line in enumerate(content.splitlines(), 1):
            for rule, pattern in PRIVATE_PATTERNS:
                if rule == 'personal-phone' and ('tests/' in relative or '/test/' in relative):
                    continue  # Synthetic, format-valid identities for unit tests.
                if pattern.search(line):
                    findings.append({'path': relative, 'line': number, 'rule': rule})
            if any(secret in line for secret in fingerprints):
                findings.append({'path': relative, 'line': number, 'rule': 'local-secret-fingerprint'})
    return {'files': count, 'bytes': size, 'findings': findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--fingerprint-root', type=Path, help='Local env directory; values never displayed')
    parser.add_argument('--git-index', action='store_true', help='Also reject forbidden tracked paths and scan staged content')
    args = parser.parse_args()
    root = args.root.resolve()
    fingerprints = local_secrets((args.fingerprint_root or root).resolve())
    report = audit(root, fingerprints)
    if args.git_index:
        result = subprocess.run(['git', 'ls-files', '-z'], cwd=root, capture_output=True)
        if result.returncode:
            report['findings'].append({'path': '.git', 'rule': 'index-unavailable'})
        else:
            for raw in result.stdout.split(b'\0'):
                if not raw:
                    continue
                relative = Path(raw.decode('utf-8'))
                if excluded(relative):
                    report['findings'].append({'path': relative.as_posix(), 'rule': 'forbidden-tracked-path'})
                    continue
                staged = subprocess.run(['git', 'show', ':' + relative.as_posix()], cwd=root, capture_output=True)
                try:
                    content = staged.stdout.decode('utf-8-sig')
                except UnicodeDecodeError:
                    continue
                for number, line in enumerate(content.splitlines(), 1):
                    for rule, pattern in PRIVATE_PATTERNS:
                        if rule == 'personal-phone' and ('tests/' in relative.as_posix() or '/test/' in relative.as_posix()):
                            continue
                        if pattern.search(line):
                            report['findings'].append({'path': relative.as_posix(), 'line': number, 'rule': 'staged-' + rule})
                    if any(secret in line for secret in fingerprints):
                        report['findings'].append({'path': relative.as_posix(), 'line': number, 'rule': 'staged-secret-fingerprint'})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['findings'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
