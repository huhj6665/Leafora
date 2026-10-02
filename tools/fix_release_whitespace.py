"""Normalize trailing whitespace only in publishable UTF-8 text files."""
import argparse
from pathlib import Path
import re

from release_audit import source_files


def normalize(data):
    if b'\x00' in data:
        return data
    try:
        data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return data
    if not data:
        return data
    ending = b'\r\n' if b'\r\n' in data else b'\n'
    cleaned = re.sub(rb'[ \t]+(?=\r?$)', b'', data, flags=re.MULTILINE)
    return cleaned.rstrip(b'\r\n') + ending


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    changed = 0
    for path in source_files(root):
        if path.is_symlink():
            raise ValueError('Refusing symbolic links')
        data = path.read_bytes()
        cleaned = normalize(data)
        if cleaned != data:
            path.write_bytes(cleaned)
            print(path.relative_to(root).as_posix())
            changed += 1
    print('Whitespace-only normalization: {} files'.format(changed))


if __name__ == '__main__':
    main()
