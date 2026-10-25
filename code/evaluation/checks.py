"""Run the authored tests and persist measured results for the Markdown report."""
import json
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


if __name__ == '__main__':
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.discover(str(ROOT/'code/tests'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    measurement = {'run_at':datetime.now(timezone.utc).isoformat(), 'tests':result.testsRun,
                   'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
                   'passed':result.wasSuccessful(),'seconds':round(time.perf_counter()-started,3)}
    path = ROOT/'work/test_results.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(measurement,indent=2),encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
