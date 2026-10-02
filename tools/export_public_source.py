"""Export current publishable files only; never copy old Git history or secrets."""
import argparse
from pathlib import Path
import shutil

from release_audit import audit, local_secrets, source_files


def export(root, output):
    root, output = root.resolve(), output.resolve()
    if output == root or root in output.parents or output in root.parents:
        raise ValueError('Output must be separate from the source tree.')
    if output.exists():
        raise ValueError('Output already exists; refusing to overwrite any files.')
    report = audit(root, local_secrets(root))
    if report['findings']:
        raise ValueError('Source audit failed; run release_audit.py for redacted locations.')
    selected = list(source_files(root))
    if any(p.is_symlink() for p in selected):
        raise ValueError('Refusing symbolic links.')
    output.mkdir(parents=True)
    for source in selected:
        destination = output / source.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    if (output / '.git').exists() or audit(output)['findings']:
        raise ValueError('Export verification failed; do not publish this output.')
    print('Exported {} files without Git history: {}'.format(len(selected), output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.root, args.output)


if __name__ == '__main__':
    main()
