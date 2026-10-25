"""Verify, evaluate, regenerate all requests, and package submission in one command."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def finalize(destination):
    commands = [('tests','code/evaluation/checks.py'),
                ('sample evaluation','code/evaluation/main.py','--run-samples'),
                ('all requests','code/main.py'),
                ('failure analysis','code/evaluation/failure_audit.py'),
                ('measured reports','code/evaluation/report.py'),
                ('submission package','code/package_submission.py','--destination',str(destination))]
    log = ROOT/'work/finalize.log'
    log.parent.mkdir(exist_ok=True)
    with log.open('w',encoding='utf-8') as stream:
        for label,*arguments in commands:
            print(f'Running {label}...',flush=True)
            result = subprocess.run([sys.executable,'-X','utf8',*arguments],cwd=ROOT,
                                    stdout=stream,stderr=subprocess.STDOUT,timeout=1200)
            stream.flush()
            if result.returncode:
                raise RuntimeError(f'{label} failed; see {log}')
    print(f'All checks passed. Submission files: {destination.resolve()}',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,default=ROOT.parent/'outputs')
    finalize(parser.parse_args().destination)
