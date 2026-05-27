

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

# ── Required third-party imports with clear install hints ──────────────────────
try:
    import psycopg2
    import psycopg2.errors
except ImportError:
    print("\033[91m✗  psycopg2 not installed.\033[0m")
    print("   pip install psycopg2-binary")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("\033[91m✗  python-dotenv not installed.\033[0m")
    print("   pip install python-dotenv")
    sys.exit(1)


# ── Colors ─────────────────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    DIM    = "\033[2m"

def ok(msg):   print(f"  {C.GREEN}✔{C.RESET}  {msg}")
def info(msg): print(f"  {C.CYAN}•{C.RESET}  {msg}")
def warn(msg): print(f"  {C.YELLOW}⚠{C.RESET}  {msg}")
def err(msg):  print(f"  {C.RED}✗{C.RESET}  {msg}")
def dim(msg):  print(f"  {C.DIM}{msg}{C.RESET}")



_BASE_DIR = Path(__file__).resolve().parent

VALIDATED_CSV = _BASE_DIR / "validated.csv"
CHECKED_CSV   = _BASE_DIR / "checked.csv"
CHUNK_SIZE    = 1000



def _find_and_load_env() -> Path:
    candidates = [
        _BASE_DIR / ".env",
        Path.cwd() / ".env",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(dotenv_path=p)
            return p

    # Neither location has a .env — give a clear, actionable error
    err(".env file not found.")
    dim(f"Looked in: {candidates[0]}")
    dim(f"       and: {candidates[1]}")
    dim("Create a .env file with: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD")
    sys.exit(1)


_env_path = _find_and_load_env()

DB_HOST      = os.getenv("DB_HOST")
DB_PORT      = int(os.getenv("DB_PORT", "5432"))
DB_NAME      = os.getenv("DB_NAME")
DB_USER      = os.getenv("DB_USER")
DB_PASSWORD  = os.getenv("DB_PASSWORD")
DB_SCHEMA    = os.getenv("DB_SCHEMA")
DB_TABLE     = os.getenv("DB_TABLE")
DB_NEW_TABLE = os.getenv("DB_NEW_TABLE")

_required = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
_missing  = [k for k in _required if not os.getenv(k)]
if _missing:
    err(f"Missing required variables in .env: {', '.join(_missing)}")
    dim(f".env loaded from: {_env_path}")
    sys.exit(1)


# ── Helpers ────────────────────────────────────────────────────────────────────
def _ref_table()  -> str: return f"{DB_SCHEMA}.{DB_TABLE}"
def _new_table()  -> str: return f"{DB_SCHEMA}.{DB_NEW_TABLE}"
def _index_name() -> str: return f"idx_{DB_NAME}_{DB_SCHEMA}_{DB_NEW_TABLE}_username"


def _ensure_writable(path: Path) -> None:
    """
    Create parent dirs and confirm write access before touching the DB.
    A PermissionError here (common on servers with restricted service users)
    gives a clear message rather than a confusing mid-run traceback.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        err(f"Cannot create directory: {path.parent}")
        dim("The process user lacks write permission here.")
        dim("Fix: chown/chmod the directory, or change the output path.")
        sys.exit(1)
    if path.exists() and not os.access(path, os.W_OK):
        err(f"File exists but is not writable: {path}")
        dim("Fix: chmod 664 <file>  or  chown <user> <file>")
        sys.exit(1)


def _connect() -> "psycopg2.extensions.connection":
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=DB_PASSWORD,
            # connect_timeout prevents the script from hanging silently when
            # the server's firewall drops packets (common on cloud VMs)
            connect_timeout=10,
        )
        with conn.cursor() as cur:
            cur.execute(f"SET search_path TO {DB_SCHEMA}, public")
        conn.commit()
        return conn
    except psycopg2.OperationalError as e:
        err(f"Cannot connect to PostgreSQL: {e}")
        dim(f"Host={DB_HOST}  Port={DB_PORT}  DB={DB_NAME}  User={DB_USER}")
        dim("Common server-side causes:")
        dim("  • Firewall blocks port 5432 — check security group / ufw rules")
        dim("  • pg_hba.conf does not allow this host/user combination")
        dim("  • DB_HOST is 'localhost' but Postgres listens on a socket only")
        dim("    → try DB_HOST=127.0.0.1 instead")
        sys.exit(1)


# ── Setup ──────────────────────────────────────────────────────────────────────
def create_tables():
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA}")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {_new_table()} (
                    id          SERIAL    PRIMARY KEY,
                    username    TEXT      NOT NULL UNIQUE,
                    url         TEXT      NOT NULL,
                    inserted_at TIMESTAMP NOT NULL
                )
            """)
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {_index_name()}
                ON {_new_table()}(username)
            """)
            cur.execute(f"SELECT COUNT(*) FROM {_ref_table()}")
            ref_count = cur.fetchone()[0]
        conn.commit()
        ok(f"Connected  →  {C.BOLD}{DB_NAME}{C.RESET}  ({DB_HOST}:{DB_PORT})")
        info(f"Reference  →  {_ref_table()}  ({ref_count:,} rows)")
        info(f"Output     →  {_new_table()}")
    except psycopg2.errors.UndefinedTable:
        err(f"Reference table '{_ref_table()}' not found.")
        dim("Check DB_SCHEMA and DB_TABLE in your .env file.")
        sys.exit(1)
    finally:
        conn.close()


# ── Checked-file helpers ───────────────────────────────────────────────────────
def _load_checked() -> set:
    path = CHECKED_CSV
    if not path.exists():
        return set()
    # newline="" + utf-8: explicit on every open to survive locale differences
    with path.open("r", newline="", encoding="utf-8") as f:
        checked = {row["username"].strip()
                   for row in csv.DictReader(f) if row.get("username")}
    info(f"Check      →  {len(checked):,} usernames already checked")
    return checked


def _append_to_checked(rows: List[dict]):
    if not rows:
        return
    _ensure_writable(CHECKED_CSV)
    write_header = not CHECKED_CSV.exists()
    with CHECKED_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["username", "checked_at"])
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({"username": row["username"],
                              "checked_at": datetime.now().isoformat()})
    ok(f"Check updated  →  {len(rows):,} usernames saved to {CHECKED_CSV.name}")


# ── CSV loading ────────────────────────────────────────────────────────────────
def _load_validated_csv() -> List[dict]:
    if not VALIDATED_CSV.exists():
        err(f"{VALIDATED_CSV.name} not found.")
        dim(f"Expected location: {VALIDATED_CSV}")
        dim("Run: python script.py validate")
        return []

    checked      = _load_checked()
    rows         = []
    skipped_check = 0

    with VALIDATED_CSV.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status", "").strip().lower() != "found":
                continue
            username = row["username"].strip()
            if username in checked:
                skipped_check += 1
                continue
            rows.append({"username": username, "url": row["url"].strip()})

    if skipped_check:
        warn(f"Skipped    →  {skipped_check:,} already checked")
    info(f"New rows   →  {len(rows):,} profiles to process")
    return rows


# ── Insert ─────────────────────────────────────────────────────────────────────
def _insert_chunk(cur, chunk: List[dict]) -> int:
    values = [(row["username"], row["url"], datetime.now()) for row in chunk]
    args   = ",".join(cur.mogrify("(%s,%s,%s)", v).decode() for v in values)
    cur.execute(f"""
        INSERT INTO {_new_table()} (username, url, inserted_at)
        SELECT v.username, v.url, v.inserted_at
        FROM (VALUES {args}) AS v(username, url, inserted_at)
        WHERE NOT EXISTS (
            SELECT 1 FROM {_ref_table()} r WHERE r.username = v.username
        )
        ON CONFLICT (username) DO NOTHING
    """)
    return cur.rowcount


def save_new_profiles(rows: List[dict]) -> Tuple[int, int]:
    if not rows:
        return 0, 0

    inserted = 0
    conn     = _connect()
    try:
        with conn.cursor() as cur:
            for i in range(0, len(rows), CHUNK_SIZE):
                chunk    = rows[i: i + CHUNK_SIZE]
                inserted += _insert_chunk(cur, chunk)
                done     = min(i + CHUNK_SIZE, len(rows))
                pct      = int(done / len(rows) * 100)
                bar      = ("█" * (pct // 5)).ljust(20)
                print(f"  {C.CYAN}{bar}{C.RESET}  {pct:>3}%  ({done:,}/{len(rows):,})",
                      end="\r", flush=True)

        conn.commit()
        _append_to_checked(rows)
        print(" " * 60, end="\r")  # clear progress line
    except Exception as e:
        conn.rollback()
        print()
        err(f"Insert failed: {e}")
        warn("Transaction rolled back — no partial data written.")
        warn("Check file not updated — rows will be retried on next run.")
        return 0, 0
    finally:
        conn.close()

    return inserted, len(rows) - inserted


def _counts() -> Tuple[int, int]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {_ref_table()}")
            ref = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM {_new_table()}")
            new = cur.fetchone()[0]
        return ref, new
    finally:
        conn.close()


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{C.BOLD}{C.CYAN}  ── Save to PostgreSQL ──{C.RESET}\n")

    create_tables()
    print()

    rows = _load_validated_csv()
    if not rows:
        warn("Nothing new to process — all rows already checked.")
        sys.exit(0)

    print(f"\n  {C.CYAN}Inserting {len(rows):,} profiles...{C.RESET}\n")
    inserted, skipped = save_new_profiles(rows)

    ref_count, new_count = _counts()

    print(f"\n  {'─' * 36}")
    ok(f"Inserted   →  {C.GREEN}{C.BOLD}{inserted:,}{C.RESET}  new profiles")
    if skipped:
        warn(f"Skipped    →  {skipped:,}  already in reference table")
    else:
        ok("Skipped    →  0")
    print(f"  {'─' * 36}")
    dim(f"  {str(_ref_table()):<35} {ref_count:,} rows")
    dim(f"  {str(_new_table()):<35} {new_count:,} rows")
    print()
