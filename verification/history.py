"""Persist verification runs and scheduled rechecks."""
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .sources import POLICY, PROFILE, RETAINED, SEARCH, SYNC, utc

DEFAULT_DB = Path(__file__).resolve().parents[1] / "work" / "ghost-v2.sqlite3"
CHECKS = (PROFILE, SEARCH, RETAINED, SYNC)
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
GUIDANCE = {
    "sync": "Ask the sync owner to block recreation for this account.",
    "profile": "Ask the account owner to investigate and remove the residual profile through the existing workflow.",
    "search": "Ask the search owner to remove the residual document after the sync guard is confirmed.",
    "retention": "Escalate the missing audit record to its owner using the retention recovery process.",
}


def outcome(checks):
    missing = {c.id for c in CHECKS} - {c.id for c in checks}
    inconclusive = sorted(missing | {c.id for c in checks if c.state == "unknown"})
    findings = [c.id for c in checks if c.state not in {"unknown", c.expected}]
    if findings:
        return "INCOMPLETE", findings, inconclusive
    if inconclusive:
        return "NEEDS_REVIEW", findings, inconclusive
    return "VERIFIED_IN_SCOPE", findings, inconclusive


class History:
    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY, subject TEXT NOT NULL, aliases TEXT NOT NULL,
                    interval_sec INTEGER NOT NULL, next_due TEXT
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
                    run_key TEXT NOT NULL UNIQUE, collected_at TEXT NOT NULL,
                    result TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS runs_by_case ON runs(case_id,id DESC);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def add_case(self, case_id, subject, aliases, interval):
        if not CASE_ID.fullmatch(case_id) or not CASE_ID.fullmatch(subject):
            raise ValueError("Case and subject references must contain only letters, digits, underscores or dashes.")
        if not 0 <= interval <= 86400 or 0 < interval < 5:
            raise ValueError("Use an interval from 5 to 86400 seconds, or 0 to disable rechecks.")
        normalized = sorted({a.strip().casefold() for a in aliases if a.strip()})
        if len(normalized) > 20 or any(len(a) > 254 for a in normalized):
            raise ValueError("At most 20 aliases of up to 254 characters are supported.")
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO cases VALUES(?,?,?,?,NULL)",
                       (case_id, subject, json.dumps(normalized), interval))

    def cases(self):
        with closing(self.connect()) as db:
            rows = db.execute("""
                SELECT c.id,c.next_due,c.interval_sec,r.result FROM cases c
                LEFT JOIN runs r ON r.id=(SELECT max(id) FROM runs WHERE case_id=c.id)
                ORDER BY c.id
            """)
            return [{"id": row["id"], "next_due": row["next_due"], "interval_sec": row["interval_sec"],
                     "latest": json.loads(row["result"]) if row["result"] else None} for row in rows]

    def detail(self, case_id, run_id=None):
        with closing(self.connect()) as db:
            case = db.execute("SELECT id,next_due,interval_sec FROM cases WHERE id=?", (case_id,)).fetchone()
            if not case:
                raise KeyError(case_id)
            rows = db.execute("SELECT id,result FROM runs WHERE case_id=? ORDER BY id DESC LIMIT 50",
                              (case_id,)).fetchall()
            if run_id and not any(str(r["id"]) == run_id for r in rows):
                selected = db.execute("SELECT id,result FROM runs WHERE case_id=? AND id=?",
                                      (case_id, run_id)).fetchone()
                if not selected:
                    raise KeyError(run_id)
                rows.append(selected)
            return {**dict(case), "runs": [{"id": row["id"], **json.loads(row["result"])} for row in rows]}

    def run(self, case_id, sources, due_at=None):
        # Serialize audits in this single-worker demo. WAL lets the dashboard read while a check runs.
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            case = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if not case:
                raise KeyError(case_id)
            if due_at and (case["next_due"] != due_at or due_at > utc()):
                return None
            run_key = f"{case_id}:{due_at}" if due_at else str(uuid4())
            checks = sources.inspect(case["subject"], json.loads(case["aliases"]))
            status, findings, review = outcome(checks)
            last = db.execute("SELECT id,result FROM runs WHERE case_id=? ORDER BY id DESC LIMIT 1",
                              (case_id,)).fetchone()
            open_states = {c.id for c in checks if c.state in {"present", "unknown"}}
            reappearances = ([dict(event, present_run=event.get("present_run", last["id"]))
                              for event in json.loads(last["result"])["reappearances"]
                              if event["check"] in open_states] if last else [])
            previous = db.execute("SELECT id,result FROM runs WHERE case_id=? ORDER BY id DESC",
                                  (case_id,))
            pending = {c.id: c for c in checks if c.id in {"profile", "search"} and c.state == "present"
                       and not any(e["check"] == c.id for e in reappearances)}
            for row in previous:
                if not pending:
                    break
                for check in json.loads(row["result"])["checks"]:
                    if check["id"] not in pending or check["state"] == "unknown":
                        continue
                    current = pending.pop(check["id"])
                    if check["state"] == "absent":
                        reappearances.append({"check": current.id, "previous_run": row["id"],
                                              "absent_at": check["observed_at"], "present_at": current.observed_at})
            collected = utc()
            delay = case["interval_sec"]
            next_due = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(
                timespec="milliseconds") if delay else None
            result = {"policy": POLICY, "status": status, "collected_at": collected,
                      "trigger": "Scheduled" if due_at else "Manual",
                      "checks": [asdict(c) for c in checks], "findings": findings, "review": review,
                      "reappearances": reappearances,
                      "guidance": [GUIDANCE[c] for c in GUIDANCE if c in findings]}
            cursor = db.execute("INSERT INTO runs(case_id,run_key,collected_at,result) VALUES(?,?,?,?)",
                                (case_id, run_key, collected, json.dumps(result)))
            for event in reappearances:
                event.setdefault("present_run", cursor.lastrowid)
            if reappearances:
                db.execute("UPDATE runs SET result=? WHERE id=?", (json.dumps(result), cursor.lastrowid))
            db.execute("UPDATE cases SET next_due=? WHERE id=?", (next_due, case_id))
            return {"id": cursor.lastrowid, **result}

    def run_due(self, sources):
        now = utc()
        with closing(self.connect()) as db:
            cases = db.execute("SELECT id,next_due FROM cases WHERE next_due<=? ORDER BY next_due", (now,)).fetchall()
        return [run for row in cases if (run := self.run(row["id"], sources, row["next_due"]))]


def report(case, run):
    lines = ["Ghost Protocol verification report", f"Case: {case['id']}", f"Policy: {run['policy']}",
             f"Verdict: {run['status']}", f"Collected: {run['collected_at']}",
             "Coverage: the configured demo tables, search index, and sync guard.", "Checks:"]
    for item in run["checks"]:
        lines.append(f"- Run {run['id']} / {item['id']}: {item['system']} · {item['scope']} | "
                     f"expected {item['expected']}, observed {item['state']} at {item['observed_at']} "
                     f"| {item['reason']}")
    for event in run["reappearances"]:
        lines.append(f"- Returned {event['check']}: absent in run {event['previous_run']} at "
                     f"{event['absent_at']}, present in run {event.get('present_run', run['id'])} at {event['present_at']}.")
    lines += ["Proposed follow-up:"] + (run["guidance"] or ["Review any unknown check and rerun when coverage improves."])
    return "\n".join(lines) + "\n"
