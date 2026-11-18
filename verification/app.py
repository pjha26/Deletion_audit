"""Local verification desk and command-line entry point."""
import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from urllib.parse import parse_qs, urlsplit

from .history import CASE_ID, DEFAULT_DB, History, report
from .sources import Sources

ASSETS = Path(__file__).with_name("ui")


def handler(history, sources):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, content, mime="application/json", attachment=None):
            data = content if isinstance(content, bytes) else json.dumps(content).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.end_headers()
            self.wfile.write(data)

        def valid_host(self):
            return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}",
                                                f"localhost:{self.server.server_port}"}

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {"error": "Open the desk through its loopback address."})
            request = urlsplit(self.path)
            route = request.path
            assets = {"/": ("index.html", "text/html"), "/desk.css": ("desk.css", "text/css"),
                      "/desk.js": ("desk.js", "text/javascript")}
            if route in assets:
                filename, mime = assets[route]
                return self.send(200, (ASSETS / filename).read_bytes(), f"{mime}; charset=utf-8")
            if route == "/api/cases":
                return self.send(200, history.cases())
            parts = route.strip("/").split("/")
            if parts[:2] == ["api", "cases"] and len(parts) in {3, 5} and CASE_ID.fullmatch(parts[2]):
                run_id = (parse_qs(request.query).get("run", [None])[0] if len(parts) == 3 else parts[4])
                if run_id is not None and (len(run_id) > 19 or not run_id.isascii() or not run_id.isdigit()):
                    return self.send(400, {"error": "Invalid run reference."})
                try:
                    case = history.detail(parts[2], run_id)
                except KeyError:
                    return self.send(404, {"error": "Case or verification run not found."})
                if len(parts) == 3:
                    return self.send(200, case)
                if parts[3] == "reports" and parts[4].isascii() and parts[4].isdigit():
                    for run in case["runs"]:
                        if str(run["id"]) == parts[4]:
                            return self.send(200, report(case, run).encode(), "text/plain; charset=utf-8",
                                             f"{case['id']}-run-{run['id']}.txt")
            self.send(404, {"error": "No such route."})

        def do_POST(self):
            if not self.valid_host() or self.headers.get("Origin") != f"http://{self.headers.get('Host')}" or (
                    self.headers.get("X-Ghost-Local") != "1" or self.headers.get("Content-Length", "0") != "0"
                    or self.headers.get("Transfer-Encoding")):
                return self.send(403, {"error": "Use the local desk to start a check."})
            parts = urlsplit(self.path).path.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "cases"] or parts[3] != "run" or not CASE_ID.fullmatch(parts[2]):
                return self.send(404, {"error": "No such route."})
            try:
                self.send(200, history.run(parts[2], sources))
            except KeyError:
                self.send(404, {"error": "Case not found."})
            except sqlite3.OperationalError:
                self.send(503, {"error": "The audit history is busy. Try again shortly."})

    return Handler


def serve(history, sources, port):
    stop = Event()

    def worker():
        while not stop.is_set():
            try:
                history.run_due(sources)
            except sqlite3.OperationalError:
                print("Audit history is temporarily busy.", flush=True)
            stop.wait(1)

    with ThreadingHTTPServer(("127.0.0.1", port), handler(history, sources)) as server:
        thread = Thread(target=worker, daemon=True)
        thread.start()
        print(f"Local: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            thread.join(timeout=25)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    commands = parser.add_subparsers(dest="command", required=True)
    web = commands.add_parser("serve")
    web.add_argument("--port", type=int, default=8772)
    case = commands.add_parser("add-case")
    case.add_argument("case")
    case.add_argument("subject")
    case.add_argument("--alias", action="append", default=[])
    case.add_argument("--every", type=int, default=0, help="Seconds between recurring checks")
    commands.add_parser("run").add_argument("case")
    options = parser.parse_args()
    history = History(options.db)
    if options.command == "add-case":
        history.add_case(options.case, options.subject, options.alias, options.every)
    elif options.command == "run":
        print(json.dumps(history.run(options.case, Sources.from_env()), indent=2))
    else:
        serve(history, Sources.from_env(), options.port)


if __name__ == "__main__":
    main()
