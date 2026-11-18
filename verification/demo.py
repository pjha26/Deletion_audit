"""Synthetic fixture operator. These write credentials are separate from the verifier."""
import argparse
import os
import time
from urllib.error import HTTPError, URLError

import psycopg
from psycopg import sql

from .history import History
from .sources import SearchClient, Sources

CASE = "GP-1042"
SUBJECT = "demo-account-1042"
ALIAS = "previous-account@fiction.test"
DOCUMENT = "/ghost-profiles/_doc/demo-1042?refresh=wait_for"


def admin_search():
    return SearchClient("https://127.0.0.1:49200", "admin",
                        os.environ["GHOST_SEARCH_ADMIN_PASSWORD"], allow_demo_cert=True)


def admin_db():
    return psycopg.connect(host="127.0.0.1", port=45432, dbname="ghost_demo", user="postgres",
                           password=os.environ["GHOST_PG_ADMIN_PASSWORD"], connect_timeout=3)


def wait_for_sources(search):
    for _ in range(60):
        try:
            with admin_db() as db:
                db.execute("SELECT 1")
            search.request("GET", "/")
            return
        except (URLError, OSError, psycopg.OperationalError):
            time.sleep(2)
    raise SystemExit("Demo sources did not become ready.")


def seed(history):
    search = admin_search()
    wait_for_sources(search)
    with admin_db() as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS ghost_demo")
        db.execute("CREATE TABLE IF NOT EXISTS ghost_demo.profiles (subject_ref text PRIMARY KEY)")
        db.execute("CREATE TABLE IF NOT EXISTS ghost_demo.retained_audit (subject_ref text PRIMARY KEY)")
        db.execute("CREATE TABLE IF NOT EXISTS ghost_demo.sync_guard (subject_ref text PRIMARY KEY, blocked boolean NOT NULL)")
        if not db.execute("SELECT 1 FROM pg_roles WHERE rolname='ghost_auditor'").fetchone():
            db.execute("CREATE ROLE ghost_auditor LOGIN")
        db.execute(sql.SQL("ALTER ROLE ghost_auditor PASSWORD {}").format(
            sql.Literal(os.environ["GHOST_PG_READ_PASSWORD"])))
        db.execute("GRANT USAGE ON SCHEMA ghost_demo TO ghost_auditor")
        db.execute("GRANT SELECT ON ALL TABLES IN SCHEMA ghost_demo TO ghost_auditor")
        db.execute("INSERT INTO ghost_demo.profiles VALUES (%s) ON CONFLICT DO NOTHING", (SUBJECT,))
        db.execute("INSERT INTO ghost_demo.retained_audit VALUES (%s) ON CONFLICT DO NOTHING", (SUBJECT,))
        db.execute("INSERT INTO ghost_demo.sync_guard VALUES (%s, false) ON CONFLICT (subject_ref) "
                   "DO UPDATE SET blocked=false", (SUBJECT,))
        db.execute("INSERT INTO ghost_demo.retained_audit VALUES ('demo-review-1057') ON CONFLICT DO NOTHING")
        db.execute("INSERT INTO ghost_demo.sync_guard VALUES ('demo-review-1057', true) ON CONFLICT DO NOTHING")
    search.request("PUT", "/_plugins/_security/api/internalusers/ghost_auditor",
                   {"password": os.environ["GHOST_SEARCH_PASSWORD"]})
    search.request("PUT", "/_plugins/_security/api/roles/ghost_audit_reader",
                   {"cluster_permissions": [], "index_permissions": [
                       {"index_patterns": ["ghost-profiles"],
                        "allowed_actions": ["search", "indices:admin/mappings/get"]}]})
    search.request("PUT", "/_plugins/_security/api/rolesmapping/ghost_audit_reader",
                   {"users": ["ghost_auditor"]})
    try:
        search.request("GET", "/ghost-profiles")
    except HTTPError as error:
        if error.code != 404:
            raise
        search.request("PUT", "/ghost-profiles", {"settings": {"number_of_replicas": 0},
                       "mappings": {"dynamic": "strict", "properties": {
                           "subject_ref": {"type": "keyword"}, "alias": {"type": "keyword"}}}})
    search.request("PUT", DOCUMENT, {"subject_ref": SUBJECT, "alias": ALIAS})
    registered = {case["id"] for case in history.cases()}
    if CASE not in registered:
        history.add_case(CASE, SUBJECT, [ALIAS], 15)
    if "GP-1057" not in registered:
        history.add_case("GP-1057", "demo-review-1057", [ALIAS], 0)


def fixture(action):
    if action == "delete-primary":
        with admin_db() as db:
            db.execute("DELETE FROM ghost_demo.profiles WHERE subject_ref=%s", (SUBJECT,))
    elif action == "clean-copy":
        with admin_db() as db:
            db.execute("UPDATE ghost_demo.sync_guard SET blocked=true WHERE subject_ref=%s", (SUBJECT,))
        try:
            admin_search().request("DELETE", DOCUMENT)
        except HTTPError as error:
            if error.code != 404:
                raise
    elif action == "replay-sync":
        with admin_db() as db:
            db.execute("UPDATE ghost_demo.sync_guard SET blocked=false WHERE subject_ref=%s", (SUBJECT,))
        admin_search().request("PUT", DOCUMENT, {"subject_ref": SUBJECT, "alias": ALIAS})


def verify_permissions():
    reader = Sources.from_env()
    with psycopg.connect(reader.dsn) as db:
        db.execute("SELECT 1 FROM ghost_demo.profiles LIMIT 1")
        try:
            db.execute("UPDATE ghost_demo.profiles SET subject_ref=subject_ref WHERE false")
        except psycopg.errors.InsufficientPrivilege:
            db.rollback()
        else:
            raise RuntimeError("The PostgreSQL reader has write privileges.")
    if reader.search_check(SUBJECT, [ALIAS]).state == "unknown":
        raise RuntimeError("The search role could not read its index.")
    try:
        reader.search.request("PUT", "/ghost-profiles/_doc/permission-probe", {"subject_ref": "permission-probe"})
    except HTTPError as error:
        if error.code != 403:
            raise
    else:
        admin_search().request("DELETE", "/ghost-profiles/_doc/permission-probe?refresh=wait_for")
        raise RuntimeError("The search reader has write privileges.")
    print("PostgreSQL and OpenSearch reader write probes were denied.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seed", "delete-primary", "clean-copy", "replay-sync", "permissions"])
    args = parser.parse_args()
    if args.action == "seed":
        seed(History())
    elif args.action == "permissions":
        verify_permissions()
    else:
        fixture(args.action)


if __name__ == "__main__":
    main()
