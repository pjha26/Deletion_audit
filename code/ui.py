"""Local audit dossier UI. Run: python code/ui.py --port 8765."""
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import subprocess
import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).parent/'ui'


def read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


class Store:
    def __init__(self, root=ROOT):
        self.root = root
        self.lock = threading.RLock()
        self.job = {'state': 'idle', 'action': None, 'message': ''}
        self.refresh()

    def refresh(self):
        with self.lock:
            data = self.root/'dataset'
            self.requests = {r['case_id']: r for r in read_csv(data/'deletion_requests.csv')}
            self.predictions = {r['case_id']: dict(r, steps=json.loads(r['steps_json'])) for r in read_csv(self.root/'output.csv')}
            self.traces = {r['case_id']: r for r in read_json(self.root/'work/audit_traces.json', [])}
            self.users = {r['user_id']: r for r in read_csv(data/'user_identities.csv')}
            self.history = read_csv(data/'user_audit_log.csv')
            self.files = {r['file_id']: r for r in read_csv(data/'evidence_files.csv')}
            self.activities = {r['activity_id']: r for r in read_csv(data/'system_activity.csv')}
            self.audits = {r['audit_id']: r for r in self.history}
            self.rules = read_csv(data/'deletion_rules.csv')
            self.coverage = {r['file_id']: r for r in read_json(self.root/'work/cache/coverage.json', [])}
            self.usage = read_json(self.root/'work/cache/last_usage.json', {})
            self.metrics = read_json(self.root/'work/evaluation_details.json', {})
            self.email_users = {r['email'].casefold(): uid for uid, r in self.users.items()}
            for row in self.history:
                if row['field_name'] == 'email':
                    self.email_users[row['old_value'].casefold()] = row['user_id']
                    self.email_users[row['new_value'].casefold()] = row['user_id']

    def case(self, case_id):
        if case_id not in self.requests:
            raise KeyError('Unknown case')
        request = self.requests[case_id]
        trace = self.traces.get(case_id, {})
        uid = trace.get('user_id') or self.email_users.get(request['email'].casefold())
        prediction = self.predictions.get(case_id)
        user = self.users.get(uid, {'name': request['email'].split('@')[0], 'email': request['email']})
        if prediction is None:
            review = {'required': True, 'reasons': ['No generated prediction. Run the local audit.']}
        else:
            review = trace.get('review', {'required': bool(trace.get('warnings')), 'reasons': trace.get('warnings', [])})
        return {'request': request, 'prediction': prediction, 'user': user, 'trace': trace, 'review': review,
                'identity_history': [r for r in self.history if r['user_id'] == uid and r['event_time'] <= request['audit_at']],
                'rules': self.rules}

    def summary(self):
        cases = []
        for case_id in self.requests:
            case = self.case(case_id)
            prediction = case['prediction'] or {}
            steps = prediction.get('steps', [])
            risks = sum(s['operation'] in {'REPORT_ACTIVE_DATA_FLOW', 'REPORT_RESTORE_RISK'} for s in steps)
            findings = sum(s['phase'] == 'FINDING' for s in steps)
            cases.append({'case_id': case_id, 'name': case['user']['name'], 'email': case['request']['email'],
                          'status': prediction.get('deletion_status', 'UNRUN'), 'review_required': case['review']['required'],
                          'findings': findings, 'risks': risks, 'resources': len(case['trace'].get('resources', [])),
                          'audit_at': case['request']['audit_at']})
        cases.sort(key=lambda c: (-c['risks'], -c['findings'], c['case_id']))
        output = self.root/'output.csv'
        return {'cases': cases, 'counts': dict(Counter(c['status'] for c in cases)),
                'review_required': sum(c['review_required'] for c in cases), 'evidence_files': len(self.files),
                'last_run': datetime.fromtimestamp(output.stat().st_mtime, timezone.utc).isoformat() if output.exists() else None,
                'usage': self.usage, 'metrics': {k: v for k, v in self.metrics.items() if k not in {'differences', 'unresolved'}},
                'job': self.job}

    def source(self, source_id):
        if source_id in self.files:
            entry = self.files[source_id]
            path = (self.root/'dataset'/entry['file_path']).resolve()
            if not path.is_relative_to((self.root/'dataset/evidence').resolve()):
                raise ValueError('Evidence path outside supplied evidence directory')
            kind = path.suffix.lstrip('.')
            result = dict(entry, kind=kind, coverage=self.coverage.get(source_id, {}))
            if kind not in {'pdf', 'png', 'jpg', 'jpeg'}:
                result['content'] = path.read_text(encoding='utf-8')[:1_000_000]
            return result, path
        item = self.activities.get(source_id) or self.audits.get(source_id)
        if item is None:
            raise KeyError('Unknown evidence ID')
        return {'file_id': source_id, 'kind': 'event', 'content': json.dumps(item, ensure_ascii=False, indent=2)}, None

    def start(self, action):
        with self.lock:
            if self.job['state'] == 'running':
                return False
            self.job = {'state': 'running', 'action': action, 'message': 'Reading local evidence and reconstructing the supplied requests.'}
        def worker():
            try:
                commands = []
                if action == 'run':
                    commands.append([sys.executable, str(self.root/'code/main.py')])
                commands += [[sys.executable, str(self.root/'code/evaluation/main.py'), '--run-samples'],
                             [sys.executable, str(self.root/'code/evaluation/failure_audit.py')],
                             [sys.executable, str(self.root/'code/evaluation/report.py')]]
                for command in commands:
                    result = subprocess.run(command, cwd=self.root, capture_output=True, text=True,
                                            encoding='utf-8', errors='replace', timeout=600)
                    if result.returncode:
                        raise RuntimeError((result.stderr or result.stdout)[-3000:])
                self.refresh()
                with self.lock:
                    self.job = {'state': 'done', 'action': action, 'message': 'Local run finished. Predictions and measured reports have been refreshed.'}
            except Exception as error:
                with self.lock:
                    self.job = {'state': 'error', 'action': action, 'message': str(error)}
        threading.Thread(target=worker, daemon=True).start()
        return True


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send(self, status, body, content_type='application/json; charset=utf-8', headers=None):
            if not isinstance(body, bytes):
                body = body.encode('utf-8') if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Local host required'})
            path = unquote(urlsplit(self.path).path)
            try:
                with store.lock:
                    if path == '/api/summary':
                        return self.send(200, store.summary())
                    if path == '/api/status':
                        return self.send(200, store.job)
                    if path.startswith('/api/case/'):
                        return self.send(200, store.case(path.removeprefix('/api/case/')))
                    if path == '/api/evidence':
                        return self.send(200, [dict(r, coverage=store.coverage.get(key, {})) for key, r in store.files.items()])
                    if path == '/api/evaluation':
                        report = store.root/'code/evaluation/failure_audit.md'
                        return self.send(200, {'metrics': store.metrics, 'failure_audit': report.read_text(encoding='utf-8') if report.exists() else ''})
                    if path.startswith('/api/source/'):
                        metadata, _ = store.source(path.removeprefix('/api/source/'))
                        return self.send(200, metadata)
                    if path.startswith('/api/evidence/'):
                        _, source = store.source(path.removeprefix('/api/evidence/'))
                        if source is None:
                            raise KeyError('Not a file')
                        return self.send(200, source.read_bytes(), mimetypes.guess_type(source.name)[0] or 'application/octet-stream')
                    if path == '/api/export':
                        output = store.root/'output.csv'
                        return self.send(200, output.read_bytes(), 'text/csv; charset=utf-8',
                                         {'Content-Disposition': 'attachment; filename="output.csv"'})
                names = {'/': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css', '/favicon.svg': 'favicon.svg'}
                if path not in names:
                    raise KeyError('Not found')
                asset = ASSETS/names[path]
                return self.send(200, asset.read_bytes(), mimetypes.guess_type(asset.name)[0] + '; charset=utf-8')
            except (KeyError, FileNotFoundError):
                self.send(404, {'error': 'Not found'})
            except ValueError as error:
                self.send(400, {'error': str(error)})

        def do_POST(self):
            origin = self.headers.get('Origin')
            allowed = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
            if not self.valid_host() or self.headers.get('X-Audit-Local') != '1' or (origin and origin not in allowed):
                return self.send(403, {'error': 'Same-origin local action required'})
            if self.headers.get('Content-Length', '0') not in {'0', '2'}:
                return self.send(400, {'error': 'No action parameters accepted'})
            if self.headers.get('Content-Length') == '2':
                if self.rfile.read(2) != b'{}':
                    return self.send(400, {'error': 'Invalid action body'})
            action = {'/api/run': 'run', '/api/evaluate': 'evaluate'}.get(urlsplit(self.path).path)
            if action is None:
                return self.send(404, {'error': 'Unknown action'})
            started = store.start(action)
            self.send(202 if started else 409, store.job)
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(Store()))
    print(f'Ghost Protocol local audit desk: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
