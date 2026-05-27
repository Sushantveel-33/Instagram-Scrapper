"""
script.py — Instagram Username Generator + Validator

Usage:
    python script.py generate     → generate usernames → usernames.csv
    python script.py validate     → validate each URL  → validated.csv
    python script.py all          → generate then validate

"""

from __future__ import annotations

import csv
import os
import random
import re
import sys
import time
import threading
from pathlib import Path
from typing import Generator, List, Optional, Tuple
from dotenv import load_dotenv, dotenv_values

_BASE_DIR = Path(__file__).resolve().parent

TARGET        = 500
GENERATED_CSV = _BASE_DIR / "usernames.csv"
VALIDATED_CSV = _BASE_DIR / "validated.csv"

NAME_FILES = [
    str(_BASE_DIR / "unique_names_ssa.txt")          
]

MAX_WORKERS       = 1
HEADLESS          = True
PAGE_TIMEOUT      = 15
SESSION_COOLDOWN  = 10
SESSION_MAX_FAILS = 10

load_dotenv()

#SESSIONS = os.getenv("Session_ids").split(",")
SESSIONS = [
    s.strip()
    for s in os.getenv("Session_ids", "").split(",")
    if s.strip()
]

FIRST_NAMES: List[str] = [
    "james", "john", "robert", "michael", "william", "david", "emma", "olivia",
    "sophia", "isabella", "mia", "charlotte", "amelia", "harper", "luna", "chloe",
    "aria", "layla", "riley", "zoey", "nora", "lily", "ellie", "ryan", "sarah",
    "emily", "alex", "sam", "jordan", "taylor", "morgan", "casey", "jamie",
]

LAST_NAMES: List[str] = [
    "smith", "johnson", "williams", "brown", "jones", "garcia", "miller", "davis",
    "wilson", "taylor", "anderson", "thomas", "jackson", "white", "harris", "martin",
    "thompson", "young", "allen", "king", "wright", "scott", "green", "baker",
    "adams", "nelson", "carter", "mitchell", "perez", "roberts", "turner", "phillips",
    "campbell", "parker", "evans", "edwards", "collins", "stewart", "morris", "rogers",
]

NICHES: List[str] = [
    "fitness", "food", "fashion", "beauty", "travel", "lifestyle", "wellness",
    "skincare", "makeup", "yoga", "cooking", "vegan", "photography", "art",
    "tech", "gaming", "music", "dance", "books", "coffee", "diy", "craft",
    "parenting", "finance", "health", "style", "design", "creative", "media",
]

BRAND_NAMES: List[str] = []

SEPARATORS: List[str] = ["", "_", "."]


# ── Utility: ensure output directory is writable before touching any file ──────
def _ensure_writable_dir(path: Path) -> None:
    """
    Create parent directory if missing and verify the process can write there.
    Exits early with a clear message instead of a cryptic PermissionError later.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"[error] No permission to create directory: {path.parent}")
        print("        Run as a user that owns this directory, or change the output path.")
        sys.exit(1)
    if path.exists() and not os.access(path, os.W_OK):
        print(f"[error] File exists but is not writable: {path}")
        print("        Check file ownership and permissions (ls -la).")
        sys.exit(1)


# ── Name loading ───────────────────────────────────────────────────────────────
def _load_names_from_file(filepath: str) -> List[str]:
    names: List[str] = []
    # Normalise to lowercase path to avoid case-sensitivity surprises on Linux
    path = Path(filepath)
    if not path.exists():
        
        lower_path = path.parent / path.name.lower()
        if lower_path.exists():
            print(f"  [warning] Used lowercase filename: {lower_path}")
            path = lower_path
        else:
            print(f"  [warning] File not found: {filepath} — skipping")
            return []
    
    with path.open("r", encoding="utf-8") as f:
        for line in f:
           
            line = line.rstrip("\r\n").strip()
            if not line:
                continue
            name = line.split(",")[0].strip().lower()
            if name and name.isalpha() and 2 <= len(name) <= 20:
                names.append(name)
    print(f"  Loaded {len(names):,} names from {path.name}")
    return names


def load_file_names(filepaths: List[str]) -> List[str]:
    seen: set = set()
    combined: List[str] = []
    for fp in filepaths:
        for name in _load_names_from_file(fp):
            if name not in seen:
                seen.add(name)
                combined.append(name)
    return combined



def _make_username(seen: set, fn: str, kn: str, ln: str,
                   nic: str, bn: str, sep: str, n: str) -> Optional[str]:
    pattern = random.choices(
        population=list(range(1, 33)),
        weights=[
            6, 6, 5, 5,
            4, 4, 4, 4,
            3, 3, 3, 3,
            2, 2, 2,
            3, 3, 3, 3,
            2, 2, 2, 2, 2,
            5, 5, 4, 4,
            3, 3, 3, 3,
        ],
        k=1
    )[0]

    if   pattern == 1:  u = fn + sep + ln
    elif pattern == 2:  u = fn + sep + ln + sep + n
    elif pattern == 3:  u = fn + n
    elif pattern == 4:  u = fn + sep + ln[0] + n
    elif pattern == 5:  u = fn + sep + nic
    elif pattern == 6:  u = fn + sep + nic + sep + n
    elif pattern == 7:  u = fn + ln[0] + sep + nic
    elif pattern == 8:  u = fn + sep + ln + sep + nic
    elif pattern == 9:  u = "its"  + sep + fn
    elif pattern == 10: u = "im"   + sep + fn
    elif pattern == 11: u = "real" + sep + fn
    elif pattern == 12: u = "by"   + sep + fn
    elif pattern == 13: u = fn + sep + "creates"
    elif pattern == 14: u = fn + sep + "ugc"
    elif pattern == 15: u = fn + sep + "content"
    elif pattern == 16: u = bn
    elif pattern == 17: u = bn + sep + "official"
    elif pattern == 18: u = bn + sep + "hq"
    elif pattern == 19: u = bn + sep + "co"
    elif pattern == 20: u = "shop" + sep + bn
    elif pattern == 21: u = "the"  + sep + bn
    elif pattern == 22: u = bn + sep + "studio"
    elif pattern == 23: u = bn + sep + "world"
    elif pattern == 24: u = bn + sep + nic
    elif pattern == 25: u = kn + sep + ln
    elif pattern == 26: u = kn + sep + ln + sep + n
    elif pattern == 27: u = kn + n
    elif pattern == 28: u = kn + sep + ln[0] + n
    elif pattern == 29: u = kn + sep + nic
    elif pattern == 30: u = "its" + sep + kn
    elif pattern == 31: u = kn + sep + "creates"
    else:               u = kn + sep + nic + sep + n

    u = u.strip().lower()
    if u and u not in seen and 3 <= len(u) <= 30:
        return u
    return None


def generate_usernames(target: int, file_names: List[str]) -> Generator[str, None, None]:
    seen: set = set()
    count = attempts = 0
    while count < target and attempts < target * 10:
        attempts += 1
        fn  = random.choice(FIRST_NAMES)
        kn  = random.choice(
            file_names)  if file_names  else fn
        ln  = random.choice(LAST_NAMES)  if LAST_NAMES  else fn
        nic = random.choice(NICHES)      if NICHES      else fn
        bn  = random.choice(BRAND_NAMES) if BRAND_NAMES else fn
        sep = random.choice(SEPARATORS)
        n   = str(random.randint(1, 999))
        u   = _make_username(seen, fn, kn, ln, nic, bn, sep, n)
        if u:
            seen.add(u)
            count += 1
            yield u


def run_generator():
    print("=" * 50)
    print("Generator")
    print("=" * 50)

    # Verify write access before doing any work
    _ensure_writable_dir(GENERATED_CSV)

    print("Loading name files...")
    file_names = load_file_names(NAME_FILES)
    print(f"  Built-in first names : {len(FIRST_NAMES):,}")
    print(f"  Names from txt files : {len(file_names):,}")

    existing: set = set()
    if GENERATED_CSV.exists():
        
        with GENERATED_CSV.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("username"):
                    existing.add(row["username"])
        print(f"  Skipping {len(existing):,} already generated — appending new ones")

    mode         = "a" if existing else "w"
    write_header = not existing
    count        = 0

    with GENERATED_CSV.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["username", "url"])
        if write_header:
            writer.writeheader()
        for username in generate_usernames(TARGET, file_names):
            if username in existing:
                continue
            writer.writerow({"username": username,
                              "url": f"https://instagram.com/{username}/"})
            existing.add(username)
            count += 1

    print(f"\n  Done. {count:,} usernames written to {GENERATED_CSV.name}")



class SessionManager:
    def __init__(self, session_ids: List[str]):
        self._lock     = threading.Lock()
        self._sessions = [
            {"id": s, "last_used": 0.0, "failures": 0, "paused_until": 0.0}
            for s in session_ids
        ]
        self._index = 0

    def get_cookie(self) -> dict:
        if not self._sessions:
            return {}
        now = time.time()
        with self._lock:
            for _ in range(len(self._sessions) * 2):
                s = self._sessions[self._index]
                self._index = (self._index + 1) % len(self._sessions)
                if now < s["paused_until"]:
                    continue
                if now - s["last_used"] < SESSION_COOLDOWN:
                    continue
                s["last_used"] = now
                return {"sessionid": s["id"]}
            return {"sessionid": self._sessions[0]["id"]}

    def report_success(self, sid: str):
        with self._lock:
            for s in self._sessions:
                if s["id"] == sid:
                    s["failures"] = max(0, s["failures"] - 1)
                    break

    def report_failure(self, sid: str, rate_limited: bool = False):
        with self._lock:
            for s in self._sessions:
                if s["id"] == sid:
                    s["failures"] += 1
                    if rate_limited or s["failures"] >= SESSION_MAX_FAILS:
                        pause = 300 if rate_limited else 120
                        s["paused_until"] = time.time() + pause
                        print(f"  [session] paused {pause}s — "
                              f"{'rate-limit' if rate_limited else 'too many failures'}")
                    break



try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False

_NOT_FOUND_SIGNALS = [
    "page not found", "this page isn't available",
    "sorry, this page isn't available", "content isn't available",
    "the link you followed may be broken", "page may have been removed",
    "go back to instagram", "error_page", "profilepagenotfound",
]

_PROFILE_SIGNALS = [
    '"profile_pic_url"', '"followers_count"', '"follower_count"',
    '"biography"', '"edge_followed_by"', '"edge_owner_to_timeline_media"',
]


_file_lock = threading.Lock()


def _create_driver():
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")              
    opts.add_argument("--disable-dev-shm-usage")   
    opts.add_argument("--disable-setuid-sandbox")  
    opts.add_argument("--remote-debugging-port=0") 
    opts.add_argument("--window-size=1920,1080")
 
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(PAGE_TIMEOUT)
    return driver


def _extract_username(url: str) -> str:
    url = url.strip()
    if url.startswith("@"):
        return url[1:]
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", url)
    if m:
        return m.group(1)
    if " " not in url and "." not in url:
        return url
    return ""


def _check_profile(driver, url: str, session_mgr: Optional[SessionManager]) -> str:
    username = _extract_username(url)
    if not username:
        return "NotFound"

    sid = None
    if session_mgr:
        cookie = session_mgr.get_cookie()
        if cookie:
            sid = cookie["sessionid"]
            try:
                driver.get("https://www.instagram.com/")
                driver.add_cookie({"name": "sessionid", "value": sid,
                                   "domain": ".instagram.com"})
            except Exception:
                pass

    try:
        driver.get(f"https://www.instagram.com/{username}/")
        time.sleep(3)
        title = driver.title.lower()
        page  = driver.page_source.lower()

        for sig in _NOT_FOUND_SIGNALS:
            if sig in title or sig in page:
                if sid and session_mgr:
                    session_mgr.report_failure(sid)
                return "NotFound"

        if "please wait a few minutes" in page:
            if sid and session_mgr:
                session_mgr.report_failure(sid, rate_limited=True)
            return "NotFound"

        if "log in" in page and '"profile_pic_url"' not in page:
            return "NotFound"

        for sig in _PROFILE_SIGNALS + [f"instagram.com/{username.lower()}"]:
            if sig in page:
                if sid and session_mgr:
                    session_mgr.report_success(sid)
                return "Found"

        return "NotFound"

    except Exception:
        if sid and session_mgr:
            session_mgr.report_failure(sid)
        return "NotFound"


def _write_result(row: list):
   
    with _file_lock:
        write_header = not VALIDATED_CSV.exists()
        with VALIDATED_CSV.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["username", "url", "status"])
            writer.writerow(row)


def _worker(rows: List[Tuple[str, str]], session_mgr: Optional[SessionManager]):
    driver = _create_driver()
    try:
        for username, url in rows:
            status = _check_profile(driver, url, session_mgr)
            _write_result([username, url, status])
            print(f"  {username} -> {status}")
    finally:
        driver.quit()


def run_validator():
    print("=" * 50)
    print("Validator")
    print("=" * 50)

    if not SELENIUM_OK:
        print("[error] Selenium not installed.")
        print("        pip install selenium")
        print("        You also need Google Chrome + matching chromedriver on PATH.")
        print("        On Ubuntu/Debian servers: apt install chromium-browser chromium-chromedriver")
        return

    if not GENERATED_CSV.exists():
        print(f"[error] {GENERATED_CSV.name} not found. Run generator first.")
        return

    _ensure_writable_dir(VALIDATED_CSV)

    all_rows: List[Tuple[str, str]] = []
    with GENERATED_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            all_rows.append((row["username"], row["url"]))

    done: set = set()
    if VALIDATED_CSV.exists():
        with VALIDATED_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done.add(row.get("url", ""))
        print(f"  Skipping {len(done):,} already validated. "
              f"Remaining: {len(all_rows) - len(done):,}")

    rows = [(u, url) for u, url in all_rows if url not in done]
    if not rows:
        print("  Nothing to validate.")
        return

    session_mgr: Optional[SessionManager] = None
    if SESSIONS:
        session_mgr = SessionManager(SESSIONS)
        print(f"  Sessions loaded: {len(SESSIONS)} account(s)")
    else:
        print("  No sessions — running without login")

    chunks: List[list] = [[] for _ in range(MAX_WORKERS)]
    for i, row in enumerate(rows):
        chunks[i % MAX_WORKERS].append(row)

    print(f"  Validating {len(rows):,} URLs with {MAX_WORKERS} worker(s)...")
    print("  Stop anytime with Ctrl+C — progress is saved automatically.\n")

    threads = [
        threading.Thread(target=_worker, args=(chunks[i], session_mgr), daemon=True)
        for i in range(MAX_WORKERS)
    ]
    try:
        for t in threads: t.start()
        for t in threads: t.join()
    except KeyboardInterrupt:
        print(f"\n  Stopped. Results saved to {VALIDATED_CSV.name}")
        return

    print(f"\n  Done. Results saved to {VALIDATED_CSV.name}")


if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "help"
    if cmd == "generate":
        run_generator()
    elif cmd == "validate":
        run_validator()
    elif cmd == "all":
        run_generator()
        print()
        run_validator()
    else:
        print(__doc__)
