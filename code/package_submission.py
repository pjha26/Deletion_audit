"""Package only runnable source/docs and copy the three submission files."""
import argparse
import csv
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from audit import validate
from main import input_fingerprint, engine_fingerprint, validate_requests

ROOT = Path(__file__).resolve().parents[1]


def package(destination):
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    required = ['code/main.py', 'code/README.md', 'code/evaluation/evaluation_report.md', 'code/evaluation/usage_report.md', 'output.csv', 'log.txt']
    for name in required:
        if not (ROOT/name).is_file():
            raise ValueError(f'Missing required submission artifact: {name}')
    with (ROOT/'output.csv').open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ['case_id','deletion_status','steps_json']:
            raise ValueError('Output CSV schema mismatch')
        output = list(reader)
    with (ROOT/'dataset/deletion_requests.csv').open(encoding='utf-8', newline='') as f:
        requests = list(csv.DictReader(f))
    validate_requests(requests)
    if len(requests) != 518:
        raise ValueError('Official submission requires exactly 518 requests')
    traces = json.loads((ROOT/'work/audit_traces.json').read_text(encoding='utf-8'))
    evidence_ids = set()
    for file,key in [('evidence_files.csv','file_id'),('system_activity.csv','activity_id'),('user_audit_log.csv','audit_id')]:
        with (ROOT/'dataset'/file).open(encoding='utf-8-sig',newline='') as stream:
            evidence_ids.update(row[key] for row in csv.DictReader(stream))
    validate(output,requests,evidence_ids,traces)
    usage = json.loads((ROOT/'work/cache/last_usage.json').read_text(encoding='utf-8'))
    expected = {'input_sha256':input_fingerprint(ROOT/'dataset',ROOT/'dataset/deletion_requests.csv'),
                'engine_sha256':engine_fingerprint(),
                'output_sha256':hashlib.sha256((ROOT/'output.csv').read_bytes()).hexdigest(),
                'trace_sha256':hashlib.sha256((ROOT/'work/audit_traces.json').read_bytes()).hexdigest()}
    if any(usage.get(key) != value for key,value in expected.items()):
        raise ValueError('Submission does not match verified run. Run code/finalize.py again.')
    coverage = json.loads((ROOT/'work/cache/coverage.json').read_text(encoding='utf-8'))
    if not coverage or any(not item.get('read') for item in coverage):
        raise ValueError('Not all evidence files were read')
    archive = destination/'code.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT/'code/README.md', 'README.md')
        for path in sorted((ROOT/'code').rglob('*')):
            if path.is_file() and path.suffix in {'.py', '.md', '.txt', '.html', '.css', '.js', '.svg'} and '__pycache__' not in path.parts:
                z.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if z.testzip() is not None or any(name.startswith(('dataset/', 'work/', '.venv/')) for name in names):
            raise ValueError('Invalid archive contents')
    for name in ['output.csv', 'log.txt']:
        shutil.copyfile(ROOT/name, destination/name)
    shutil.copyfile(ROOT/'code/IMPLEMENTATION_PLAN.md', destination/'implementation_plan.md')
    shutil.copyfile(ROOT/'code/evaluation/evaluation_report.md', destination/'evaluation_report.md')
    clarification = ROOT/'code/evaluation/clarification_needed.md'
    if clarification.exists():
        shutil.copyfile(clarification,destination/'clarification_needed.md')
    manifest = '# Submission integrity\n\n518 sorted prediction rows; exact schema and source citations validated.\n\n'
    manifest += '| File | SHA-256 |\n|---|---|\n'
    for name in ('code.zip','output.csv','log.txt'):
        manifest += f'| {name} | {hashlib.sha256((destination/name).read_bytes()).hexdigest()} |\n'
    manifest += '\nInput fingerprint: '+expected['input_sha256']+'\n\nEngine fingerprint: '+expected['engine_sha256']+'\n'
    (destination/'submission_manifest.md').write_text(manifest,encoding='utf-8')
    print(f'Packaged {len(names)} source/docs files and {len(output)} prediction rows to {destination}')
    print('code.zip SHA-256', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=ROOT.parent/'outputs')
    package(parser.parse_args().destination)
