import itertools
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from .extract import extract, grounded
from .history import History, outcome, report
from .sources import PROFILE, RETAINED, SEARCH, SYNC, Sources, search_state


def evidence(states):
    return [check.observed(state, "Synthetic test observation.")
            for check, state in zip((PROFILE, SEARCH, RETAINED, SYNC), states, strict=True)]


class FakeSources:
    def __init__(self, states):
        self.states = states

    def inspect(self, subject, aliases):
        return evidence(self.states)


def search_response(sources=()):
    return {"_shards": {"total": 1, "successful": 1, "failed": 0}, "timed_out": False,
            "hits": {"total": {"relation": "eq", "value": len(sources)}, "hits": [
                {"_index": "ghost-profiles", "_source": source} for source in sources]}}


class VerdictTests(unittest.TestCase):
    def test_no_unsafe_verified_verdict_across_policy_and_coverage_matrix(self):
        expected = ("absent", "absent", "present", "blocked")
        accepted = 0
        for states in itertools.product(("absent", "present", "unknown"), ("absent", "present", "unknown"),
                                        ("present", "absent", "unknown"), ("blocked", "active", "unknown")):
            with self.subTest(states=states):
                verdict, violations, review = outcome(evidence(states))
                if states == expected:
                    self.assertEqual(verdict, "VERIFIED_IN_SCOPE")
                    accepted += 1
                else:
                    self.assertNotEqual(verdict, "VERIFIED_IN_SCOPE")
                    if any(state not in {"unknown", required} for state, required in zip(states, expected)):
                        self.assertEqual(verdict, "INCOMPLETE")
                        self.assertTrue(violations)
                    else:
                        self.assertEqual(verdict, "NEEDS_REVIEW")
                        self.assertTrue(review)
        self.assertEqual(accepted, 1)

    def test_omitting_a_required_target_requires_review(self):
        checks = evidence(("absent", "absent", "present", "blocked"))
        self.assertEqual(outcome(checks[:3]), ("NEEDS_REVIEW", [], ["sync"]))

    def test_alias_matched_to_other_subject_cannot_prove_an_owner_or_absence(self):
        data = search_response([{"subject_ref": "other-account"}])
        self.assertEqual(search_state(SEARCH, data, "account-1", ["alias"]).state, "unknown")

    def test_partial_and_timed_out_searches_cannot_prove_absence(self):
        for data in [dict(search_response(), timed_out=True),
                     dict(search_response(), _shards={"total": 2, "successful": 1, "failed": 1})]:
            self.assertEqual(search_state(SEARCH, data, "account-1", []).state, "unknown")
        data = search_response()
        data["hits"]["total"] = {"relation": "gte", "value": 0}
        self.assertEqual(search_state(SEARCH, data, "account-1", []).state, "unknown")

    def test_matching_nothing_on_nonsearchable_identity_fields_is_unknown(self):
        class WrongMapping:
            def request(self, method, path):
                return {"ghost-profiles": {"mappings": {"properties": {
                    "subject_ref": {"type": "text"}, "alias": {"type": "keyword"}}}}}

        check = Sources(None, WrongMapping()).search_check("account-1", [])
        self.assertEqual(check.state, "unknown")
        self.assertIn("mapping", check.reason)


class RecheckTests(unittest.TestCase):
    def test_restart_recheck_records_recurrence_and_repeated_due_key_is_ignored(self):
        work = Path(__file__).resolve().parents[1] / "work"
        work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as directory:
            path = Path(directory) / "audit.sqlite"
            history = History(path)
            history.add_case("TEST-1", "account-1", ["private@fiction.test"], 15)
            present = FakeSources(("absent", "present", "present", "active"))
            absent = FakeSources(("absent", "absent", "present", "blocked"))
            self.assertEqual(history.run("TEST-1", present)["status"], "INCOMPLETE")
            clean = history.run("TEST-1", absent)
            self.assertEqual(clean["status"], "VERIFIED_IN_SCOPE")
            due = "2000-01-01T00:00:00.000+00:00"
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.execute("UPDATE cases SET next_due=?", (due,))
            restarted = History(path)
            returned, = restarted.run_due(present)
            self.assertEqual(returned["reappearances"][0]["previous_run"], clean["id"])
            self.assertIsNone(restarted.run("TEST-1", present, due))
            self.assertEqual(len(restarted.detail("TEST-1")["runs"]), 3)
            later = restarted.run("TEST-1", present)
            self.assertEqual(later["reappearances"][0]["present_run"], returned["id"])
            self.assertEqual(restarted.run("TEST-1", absent)["reappearances"], [])
            self.assertNotIn("private@fiction.test", report({"id": "TEST-1"}, returned))
            self.assertNotIn("account-1", report({"id": "TEST-1"}, returned))


class ExtractionTests(unittest.TestCase):
    def test_candidates_need_an_exact_line_and_correct_subject(self):
        document = "The search copy for acct-ab is still visible."
        base = {"event": "search_copy_present", "subject": "acct-a", "line": 1, "quote": document}
        self.assertEqual(grounded(document, "acct-a", {"facts": [base]}), [])
        exact = dict(base, subject="acct-ab")
        changed = dict(exact, quote=document + " Extra.")
        self.assertEqual(grounded(document, "acct-ab", {"facts": [exact, changed, exact]}), [exact])

    def test_local_model_failure_explicitly_routes_to_review(self):
        with patch("verification.extract.model_facts", side_effect=TimeoutError):
            result = extract("manual note for acct-1", "acct-1", "http://127.0.0.1:18087")
        self.assertTrue(result["review_required"])
        self.assertIn("failed", result["note"])


if __name__ == "__main__":
    unittest.main()
