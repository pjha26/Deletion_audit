"""Fixed-purpose read-only connectors for the supported demo schema."""
import base64
import json
import os
import ssl
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

import psycopg


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class Check:
    id: str
    system: str
    scope: str
    expected: str
    state: str = "unknown"
    reason: str = ""
    observed_at: str = ""
    matches: int | None = None

    def observed(self, state, reason, matches=None):
        return replace(self, state=state, reason=reason, observed_at=utc(), matches=matches)


PROFILE = Check("profile", "PostgreSQL", "ghost_demo.profiles", "absent")
RETAINED = Check("retention", "PostgreSQL", "ghost_demo.retained_audit", "present")
SYNC = Check("sync", "PostgreSQL", "ghost_demo.sync_guard", "blocked")
SEARCH = Check("search", "OpenSearch", "ghost-profiles", "absent")
POLICY = "demo-policy-v1"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class SearchClient:
    def __init__(self, base, user, password, allow_demo_cert=False):
        url = urlsplit(base)
        if (url.scheme != "https" or not url.hostname or url.username or url.path not in {"", "/"}
                or url.query or url.fragment):
            raise ValueError("Search must use an HTTPS origin")
        if allow_demo_cert and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Demo certificate bypass requires loopback")
        self.base = base.rstrip("/")
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        context = ssl._create_unverified_context() if allow_demo_cert else ssl.create_default_context()
        self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))

    def request(self, method, path, body=None):
        headers = {"Authorization": self.auth, "Content-Type": "application/json"}
        data = json.dumps(body).encode() if body is not None else None
        request = Request(self.base + path, data, headers, method=method)
        with self.opener.open(request, timeout=4) as response:
            return json.loads(response.read(1_000_000))


def search_state(check, response, subject, aliases):
    """Absence requires a complete exact-match query against the fixed index."""
    shards = response["_shards"]
    if response["timed_out"] is not False or response.get("terminated_early") or (
            shards["failed"] != 0 or shards["total"] <= 0 or shards["successful"] != shards["total"]):
        return check.observed("unknown", "The search did not finish across every shard.")
    hits = response["hits"]
    total = hits["total"]["value"]
    if hits["total"]["relation"] != "eq" or type(total) is not int or total != len(hits["hits"]):
        return check.observed("unknown", "The search returned an incomplete result set.")
    matched = sum(hit["_index"] == "ghost-profiles" and hit["_source"].get("subject_ref") == subject
                  for hit in hits["hits"])
    if matched:
        detail = "The index contains a document linked to the verified account."
        if matched != total:
            detail += " Other exact candidates have conflicting ownership."
        return check.observed("present", detail, matched)
    if total:
        return check.observed("unknown", "An exact alias matched a record without verified ownership.")
    return check.observed("absent", f"No document matched the stable reference or {len(aliases)} known aliases.", 0)


class Sources:
    def __init__(self, dsn, search):
        self.dsn = dsn
        self.search = search

    @classmethod
    def from_env(cls):
        return cls(os.environ.get("GHOST_PG_DSN"), SearchClient(
            os.environ.get("GHOST_SEARCH_URL", "https://127.0.0.1:49200"),
            os.environ.get("GHOST_SEARCH_USER", "ghost_auditor"),
            os.environ.get("GHOST_SEARCH_PASSWORD", ""),
            os.environ.get("GHOST_DEMO_CERT") == "1"))

    def postgres_check(self, check, subject):
        if not self.dsn:
            return check.observed("unknown", "PostgreSQL read credentials are missing.")
        statements = {
            "profile": "SELECT EXISTS (SELECT 1 FROM ghost_demo.profiles WHERE subject_ref = %s)",
            "retention": "SELECT EXISTS (SELECT 1 FROM ghost_demo.retained_audit WHERE subject_ref = %s)",
            "sync": "SELECT blocked FROM ghost_demo.sync_guard WHERE subject_ref = %s",
        }
        try:
            with psycopg.connect(self.dsn, connect_timeout=4,
                                 options="-c statement_timeout=3500 -c default_transaction_read_only=on") as conn:
                row = conn.execute(statements[check.id], (subject,)).fetchone()
        except psycopg.errors.InsufficientPrivilege:
            return check.observed("unknown", "The read-only role cannot access this target.")
        except psycopg.Error:
            return check.observed("unknown", "The database check could not finish.")
        if check.id == "sync":
            if not row or type(row[0]) is not bool:
                return check.observed("unknown", "A per-account sync guard could not be confirmed.")
            if row[0]:
                return check.observed("blocked", "The configured sync job is blocked for this account.")
            return check.observed("active", "The configured sync job can recreate this account's search copy.")
        return check.observed("present" if row[0] else "absent",
                              "A record matched the stable reference." if row[0] else
                              "No record matched the stable reference.", int(row[0]))

    def search_check(self, subject, aliases):
        must_match = [{"term": {"subject_ref": subject}}]
        if aliases:
            must_match.append({"terms": {"alias": list(aliases)}})
        query = {"query": {"bool": {"should": must_match, "minimum_should_match": 1}},
                 "_source": ["subject_ref"], "size": 50, "track_total_hits": True}
        try:
            mapping = self.search.request("GET", "/ghost-profiles/_mapping")["ghost-profiles"]["mappings"]
            properties = mapping["properties"]
            if mapping.get("_source", {}).get("enabled") is False or any(
                properties[field]["type"] != "keyword" or properties[field].get("index") is False
                for field in ("subject_ref", "alias")
            ):
                return SEARCH.observed("unknown", "Index identifier fields do not match the supported mapping.")
            data = self.search.request("POST", "/ghost-profiles/_search?allow_partial_search_results=false", query)
            return search_state(SEARCH, data, subject, aliases)
        except HTTPError as error:
            reason = ("Search permissions did not allow the check." if error.code in {401, 403}
                      else "The required search index could not be checked.")
        except (URLError, OSError, ValueError, KeyError, TypeError, AttributeError):
            reason = "Search was unavailable or returned invalid evidence."
        return SEARCH.observed("unknown", reason)

    def inspect(self, subject, aliases):
        return [self.postgres_check(PROFILE, subject), self.search_check(subject, aliases),
                self.postgres_check(RETAINED, subject), self.postgres_check(SYNC, subject)]
