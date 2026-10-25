"""Package only runnable source/docs and copy the three submission files."""
import argparse
import csv
import hashlib
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def package(destination):
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    required = ['code/main.py', 'code/README.md', 'code/evaluation/evaluation_report.md', 'code/evaluation/usage_report.md', 'output.csv', 'log.txt']
    for name in required:
        if not (ROOT/name).is_file():
            raise ValueError(f'Missing required submission artifact: {name}')
    with (ROOT/'output.csv').open(encoding='utf-8', newline='') as f:
        output = list(csv.DictReader(f))
    with (ROOT/'dataset/deletion_requests.csv').open(encoding='utf-8', newline='') as f:
        requests = list(csv.DictReader(f))
    if [r['case_id'] for r in output] != sorted(r['case_id'] for r in requests):
        raise ValueError('Output coverage/order mismatch')
    archive = destination/'code.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT/'code/README.md', 'README.md')
        for path in sorted((ROOT/'code').rglob('*')):
            if path.is_file() and path.suffix in {'.py', '.md', '.txt'} and '__pycache__' not in path.parts:
                z.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if z.testzip() is not None or any(name.startswith(('dataset/', 'work/', '.venv/')) for name in names):
            raise ValueError('Invalid archive contents')
    for name in ['output.csv', 'log.txt']:
        shutil.copyfile(ROOT/name, destination/name)
    shutil.copyfile(ROOT/'code/IMPLEMENTATION_PLAN.md', destination/'implementation_plan.md')
    shutil.copyfile(ROOT/'code/evaluation/evaluation_report.md', destination/'evaluation_report.md')
    print(f'Packaged {len(names)} source/docs files and {len(output)} prediction rows to {destination}')
    print('code.zip SHA-256', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=ROOT.parent/'outputs')
    package(parser.parse_args().destination)
