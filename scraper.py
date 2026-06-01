
"""
scraper.py  —  Stage 1: Instagram City + Niche Hashtag Scraper
═══════════════════════════════════════════════════════════════
• Builds dynamic, niche-compatible hashtags + keyword queries from CITY + NICHE
• Shuffles query order randomly on every run
• Opens each page, scrolls, CLICKS every post → gets real post-owner username
• Also extracts @tagged usernames and #hashtags from post captions:
    - @tagged users are added directly to raw_usernames.csv
    - #hashtags from posts are queued as new search targets
• TARGET is always the number of NEW users to add on this run, not the total
  file size — safe to raise and re-run at any time
• Deduplicates across all sources before writing

Usage:
    python scraper.py scrape   →  scrape → append to raw_usernames.csv
    python scraper.py reset    →  delete raw_usernames.csv then scrape fresh
    python scraper.py show     →  print generated queries (dry-run, no browser)

"""

from __future__ import annotations

import csv
import os
import re
import sys
import time
import random
import threading
from collections import deque
from pathlib import Path
from typing import Deque, Generator, List, Optional, Set, Tuple
from urllib.parse import quote

try:
    from dotenv import load_dotenv
except ImportError:
    print("\033[91m✗  python-dotenv not installed.\033[0m  pip install python-dotenv")
    sys.exit(1)

_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(_BASE_DIR / ".env")

CITY              = os.getenv("CITY")
NICHE             = os.getenv("NICHE")
TARGET            = int(os.getenv("TARGET"))   
MAX_SCROLL_ROUNDS = int(os.getenv("MAX_SCROLL_ROUNDS"))
SCROLL_PAUSE      = float(os.getenv("SCROLL_PAUSE"))
POST_CLICK_LIMIT  = int(os.getenv("POST_CLICK_LIMIT"))
PAGE_TIMEOUT      = int(os.getenv("PAGE_TIMEOUT"))
HEADLESS          = os.getenv("HEADLESS").lower() != "false"
SESSION_COOLDOWN  = int(os.getenv("SESSION_COOLDOWN"))
SESSION_MAX_FAILS = int(os.getenv("SESSION_MAX_FAILS"))
MAX_HASHTAG_QUEUE = int(os.getenv("MAX_HASHTAG_QUEUE"))
SESSIONS: List[str] = [s.strip() for s in os.getenv("SESSION_IDS","").split(",") if s.strip()]

RAW_CSV = _BASE_DIR / "raw_usernames.csv"

class C:
    RESET="\033[0m"; BOLD="\033[1m"; GREEN="\033[92m"
    YELLOW="\033[93m"; RED="\033[91m"; CYAN="\033[96m"; DIM="\033[2m"
    MAGENTA="\033[95m"

def ok(m):    print(f"  {C.GREEN}✔{C.RESET}  {m}")
def info(m):  print(f"  {C.CYAN}•{C.RESET}  {m}")
def warn(m):  print(f"  {C.YELLOW}⚠{C.RESET}  {m}")
def err(m):   print(f"  {C.RED}✗{C.RESET}  {m}")
def dim(m):   print(f"  {C.DIM}{m}{C.RESET}")
def found(m): print(f"  {C.MAGENTA}↳{C.RESET}  {m}")

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException,
        StaleElementReferenceException, ElementClickInterceptedException,
    )
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False


_RE_USERNAME  = re.compile(r'"username"\s*:\s*"([A-Za-z0-9_.]{2,30})"')
_RE_CAPTION   = re.compile(r'"text"\s*:\s*"([^"]{1,2200})"')         
_RE_AT_TAG    = re.compile(r'@([A-Za-z0-9_.]{2,30})')                  
_RE_HASH_TAG  = re.compile(r'#([A-Za-z0-9][A-Za-z0-9_]{1,29})')     

_SKIP_NAMES = frozenset({
    "instagram","explore","accounts","p","reel","reels","stories",
    "direct","tv","web","legal","about","help","privacy","safety",
    "press","api","blog","jobs","shop","music","audio",
})

_file_lock = threading.Lock()


_NICHE_EXTRAS: dict = {
    "food":        ["eats","foodie","foodies","cuisine","chef","recipe","kitchen",
                    "dining","restaurant","brunch","lunch","dinner","delicious",
                    "yummy","tasty","food","homecooking","instafood"],

    "fitness":     ["gym","workout","fit","gains","training","health","cardio",
                    "weightlifting","crossfit","yoga","pilates","athlete","strong"],

    "fashion":     ["style","ootd","outfit","streetwear","trend","lookbook",
                    "fashionista","modeling","wardrobe","apparel","couture"],

    "travel":      ["wanderlust","adventure","explore","trip","vacation","tourism",
                    "backpacker","nomad","traveler","roadtrip","getaway","journey"],

    "beauty":      ["makeup","skincare","glam","cosmetics","beautytips","mua",
                    "haircare","nails","glow","skincareroutine","beautyinfluencer"],

    "lifestyle":   ["life","daily","routine","vlog","blogger","living","vibes",
                    "motivation","inspiration","selfcare","mindfulness","wellness"],

    "technology":  ["tech","coding","developer","startup","gadget","innovation",
                    "software","app","programming","ai","machinelearning","geek"],

    "gaming":      ["gamer","esports","twitch","streaming","playstation","xbox",
                    "nintendo","videogames","fps","rpg","console","pcgaming"],

    "music":       ["musician","singer","dj","producer","concert","hiphop","rap",
                    "rnb","pop","indie","band","vocalist","songwriter","beats"],

    "art":         ["artist","painting","drawing","illustration","digitalart",
                    "design","creative","artwork","sketch","gallery","artsy"],

    "health":      ["wellness","nutrition","diet","healthy","organic","mindful",
                    "meditation","holistic","mentalhealth","selfcare","cleaneating"],

    "sports":      ["athlete","basketball","football","soccer","tennis","baseball",
                    "swimming","cycling","marathon","running","champion","team"],

    "dance":       ["dancer","choreography","ballet","hiphop","contemporary",
                    "studio","moves","routine","performance","dancing"],

    "education":   ["learning","teacher","student","tutorial","study","knowledge",
                    "academic","university","course","edtech","teaching"],

    "business":    ["entrepreneur","startup","ceo","founder","marketing","branding",
                    "growth","success","leadership","hustle","networking"],

    "finance":     ["investing","stocks","crypto","wealth","trading","money",
                    "personalfinance","budgeting","investor","fintech","bitcoin"],

    "comedy":      ["funny","humor","meme","viral","joke","skit","comedian",
                    "laugh","hilarious","parody","satire","witty"],

    "family":      ["mom","dad","parenting","kids","baby","toddler","family",
                    "motherhood","fatherhood","parentlife","homeschool"],

    "pets":        ["dog","cat","puppy","kitten","pets","petsofinstagram",
                    "dogsofinstagram","catsofinstagram","animal","wildlife","rescue"],
                    
    "entertainment":["movie","film","tv","series","streaming","actor","actress",
                     "celebrity","review","binge","popculture","netflix"],
}

def _niche_extras(niche: str) -> List[str]:
    n = niche.lower().strip()
    if n in _NICHE_EXTRAS:
        return _NICHE_EXTRAS[n]

    for key, vals in _NICHE_EXTRAS.items():
        if key in n or n in key:
            return vals

    return ["blogger","creator","influencer","content","lifestyle","daily","vlog"]


def build_search_queries(city: str, niche: str) -> List[dict]:
    
    c      = city.lower().strip()
    n      = niche.lower().strip()
    words  = c.split()
    abbr   = "".join(w[0] for w in words)[:4]    
    c_ns   = c.replace(" ", "")                    
    n_ns   = n.replace(" ", "")                   
    two    = "".join(words[:2]) if len(words) >= 2 else c_ns 

    niche_syns = _niche_extras(n)                 


    base_tags = list(filter(None, [
        # abbr + niche
        f"{abbr}{n_ns}",
        f"{abbr}{n_ns}ie",
        f"{abbr}{n_ns}ies",
        f"{abbr}{n_ns}gram",
        f"{abbr}blogger",
        f"{c_ns}{n_ns}",
        f"{c_ns}blogger",
        f"{c_ns}reels",
        f"{two}{n_ns}" if two != c_ns else "",
        f"{two}eats"   if two != c_ns else "",
        f"{n_ns}in{c_ns}",
        f"{n_ns}in{abbr}",
        f"{n_ns}blogger",
        f"{n_ns}creator",
        f"{n_ns}influencer",
        f"{n_ns}ie",
        f"{n_ns}ies",
        f"{n_ns}photography",
        f"{n_ns}gram",
        f"{n_ns}lover",
        f"{n_ns}review",
    ]))

    syn_tags = []
    for syn in niche_syns[:12]:                    
        syn_clean = syn.lower().replace(" ", "")
        syn_tags.extend([
            f"{abbr}{syn_clean}",                
            f"{c_ns}{syn_clean}",                
        ])

    all_tag_values = list(dict.fromkeys(base_tags + syn_tags))


    for x in os.getenv("EXTRA_HASHTAGS", "").split(","):
        v = x.strip().lstrip("#")
        if v:
            all_tag_values.append(v)


    keyword_values = list(dict.fromkeys([
        f"{c} {n} blogger",
        f"{c} {n} creator",
        f"{c} {n} influencer",
        f"{abbr} {n} blogger",
        f"{abbr} {n} influencer",
        f"{c} {n} instagram",
        f"best {n} in {c}",
        f"{n} blogger {c}",

        *[f"{c} {syn} blogger" for syn in niche_syns[:3]],
        *[f"{abbr} {syn}" for syn in niche_syns[:3]],
    ]))

    for x in os.getenv("EXTRA_KEYWORDS", "").split(","):
        v = x.strip()
        if v:
            keyword_values.append(v)


    queries: List[dict] = []
    for tag in all_tag_values:
        tag = tag.strip().lstrip("#")
        if len(tag) < 2:
            continue
        queries.append({
            "type":  "hashtag",
            "label": f"#{tag}",
            "value": tag,
            "url":   f"https://www.instagram.com/explore/tags/{quote(tag)}/",
        })
    for kw in keyword_values:
        if not kw:
            continue
        queries.append({
            "type":  "keyword",
            "label": f'"{kw}"',
            "value": kw,
            "url":   f"https://www.instagram.com/explore/search/?q={quote(kw)}",
        })

    random.shuffle(queries)
    return queries


def hashtag_to_query(tag: str) -> dict:
    tag = tag.strip().lstrip("#").lower()
    return {
        "type":  "hashtag",
        "label": f"#{tag}",
        "value": tag,
        "url":   f"https://www.instagram.com/explore/tags/{quote(tag)}/",
    }


class SessionManager:
    def __init__(self, session_ids: List[str]):
        self._sessions = [
            {"id": sid, "failures": 0, "last_used": 0.0, "paused_until": 0.0}
            for sid in session_ids
        ]
        self._index = 0
        self._lock  = threading.Lock()

    def get_sid(self) -> Optional[str]:
        if not self._sessions:
            return None
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
                return s["id"]
            return min(self._sessions, key=lambda s: s["paused_until"])["id"]

    def ok(self, sid: str):
        with self._lock:
            for s in self._sessions:
                if s["id"] == sid:
                    s["failures"] = max(0, s["failures"] - 1)
                    break

    def fail(self, sid: str, rate_limited: bool = False):
        with self._lock:
            for s in self._sessions:
                if s["id"] == sid:
                    s["failures"] += 1
                    if rate_limited or s["failures"] >= SESSION_MAX_FAILS:
                        pause = 300 if rate_limited else 120
                        s["paused_until"] = time.time() + pause
                        warn(f"Session paused {pause}s")
                    break

def _create_driver():
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    for arg in [
        "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-setuid-sandbox", "--remote-debugging-port=0",
        "--window-size=1920,1080",
    ]:
        opts.add_argument(arg)
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    d = webdriver.Chrome(options=opts)
    d.set_page_load_timeout(PAGE_TIMEOUT)
    return d


def _inject_session(driver, sid: str):
    try:
        if "instagram.com" not in driver.current_url:
            driver.get("https://www.instagram.com/")
            time.sleep(2)
        driver.add_cookie({
            "name": "sessionid", "value": sid,
            "domain": ".instagram.com", "path": "/",
        })
    except Exception as e:
        warn(f"Cookie inject failed: {e}")


def _source_usernames(page: str) -> Set[str]:
    return {
        u.lower() for u in _RE_USERNAME.findall(page)
        if 2 <= len(u) <= 30 and u.lower() not in _SKIP_NAMES
    }


def _extract_caption_data(page: str) -> Tuple[Set[str], Set[str]]:
    
    tagged_users:   Set[str] = set()
    found_hashtags: Set[str] = set()

    for caption_text in _RE_CAPTION.findall(page):
        # Unescape basic JSON sequences
        caption_text = caption_text.replace("\\n", " ").replace('\\"', '"')

        for mention in _RE_AT_TAG.findall(caption_text):
            u = mention.lower()
            if 2 <= len(u) <= 30 and u not in _SKIP_NAMES:
                tagged_users.add(u)

        for tag in _RE_HASH_TAG.findall(caption_text):
            t = tag.lower()
            if 2 <= len(t) <= 30:
                found_hashtags.add(t)

    return tagged_users, found_hashtags


def _click_post_and_extract(
    driver,
    post_el,
    hashtag_queue: Deque[str],
    queued_hashtags: Set[str],
) -> Optional[str]:
   
    username       = None
    original_url   = driver.current_url
    caption_users: List[str] = []

    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", post_el)
        time.sleep(0.3)
        try:
            post_el.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", post_el)

       
        try:
            WebDriverWait(driver, 5).until(
                lambda d: d.current_url != original_url
                          or d.find_elements(By.CSS_SELECTOR, "article")
            )
        except TimeoutException:
            pass
        time.sleep(random.uniform(0.8, 1.4))

        page = driver.page_source
        try:
            article = driver.find_element(By.CSS_SELECTOR, "article,[role='dialog']")
            for lnk in article.find_elements(By.CSS_SELECTOR, "a[href^='/']")[:6]:
                href = lnk.get_attribute("href") or ""
                m = re.search(
                    r"instagram\.com/([A-Za-z0-9_.]{2,30})/?(?:\?.*)?$", href
                )
                if m and m.group(1).lower() not in _SKIP_NAMES:
                    username = m.group(1).lower()
                    break
        except NoSuchElementException:
            pass

        if not username:
            m = re.search(
                r'"owner"\s*:\s*\{[^}]*"username"\s*:\s*"([A-Za-z0-9_.]{2,30})"',
                page,
            )
            if m and m.group(1).lower() not in _SKIP_NAMES:
                username = m.group(1).lower()

        if not username:
            cands = _source_usernames(page)
            if cands:
                username = next(iter(cands))

        tagged, post_hashtags = _extract_caption_data(page)

        caption_users.extend(
            u for u in tagged
            if u not in _SKIP_NAMES and u != username
        )

        for ht in post_hashtags:
            if ht not in queued_hashtags and len(queued_hashtags) < MAX_HASHTAG_QUEUE:
                queued_hashtags.add(ht)
                hashtag_queue.append(ht)

    except Exception:
        pass
    finally:
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys("\ue00c")
            time.sleep(0.4)
        except Exception:
            pass
        if driver.current_url != original_url:
            try:
                driver.back()
                time.sleep(1.2)
            except Exception:
                pass

    return username, caption_users


def _scroll_and_collect(
    driver,
    query: dict,
    all_seen: Set[str],      
    new_collected: Set[str], 
    hashtag_queue: Deque[str],
    queued_hashtags: Set[str],
) -> Generator[Tuple[str, str], None, None]:
    label = query["label"]

    try:
        driver.get(query["url"])
        time.sleep(random.uniform(2.5, 3.5))
    except Exception as e:
        warn(f"Load failed {label}: {e}")
        return

    page = driver.page_source
    if any(s in page.lower() for s in ["log in", "sign up", "create account"]):
        warn(f"Not logged in for {label}")
        return
    if "please wait a few minutes" in page.lower():
        warn(f"Rate-limited on {label}")
        return

    for u in _source_usernames(page):
        if u not in all_seen:
            all_seen.add(u)
            new_collected.add(u)
            yield u, label
            if len(new_collected) >= TARGET:
                return

    clicked: Set[str]   = set()
    new_this_query: int = 0

    for _round in range(MAX_SCROLL_ROUNDS):
        if new_this_query >= POST_CLICK_LIMIT:
            break

        new_posts = []
        for sel in ("article a[href*='/p/']", "a[href*='/p/']", "a[href*='/reel/']"):
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    for el in els:
                        try:
                            href = el.get_attribute("href") or ""
                            if href and href not in clicked:
                                clicked.add(href)
                                new_posts.append(el)
                        except StaleElementReferenceException:
                            continue
                    break
            except Exception:
                continue

        for post_el in new_posts:
            if new_this_query >= POST_CLICK_LIMIT or len(new_collected) >= TARGET:
                break

            owner, caption_users = _click_post_and_extract(
                driver, post_el, hashtag_queue, queued_hashtags
            )

            if owner and owner not in all_seen and owner not in _SKIP_NAMES:
                all_seen.add(owner)
                new_collected.add(owner)
                new_this_query += 1
                yield owner, label
                if len(new_collected) >= TARGET:
                    return

            for cu in caption_users:
                if cu not in all_seen and cu not in _SKIP_NAMES:
                    all_seen.add(cu)
                    new_collected.add(cu)
                    new_this_query += 1
                    found(f"@tagged in caption: {cu}  (from {label})")
                    yield cu, f"{label} [caption @tag]"
                    if len(new_collected) >= TARGET:
                        return

            time.sleep(random.uniform(0.5, 1.1))

        prev_h = driver.execute_script("return document.body.scrollHeight")
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 1400);")
            time.sleep(SCROLL_PAUSE)

        for u in _source_usernames(driver.page_source):
            if u not in all_seen:
                all_seen.add(u)
                new_collected.add(u)
                new_this_query += 1
                yield u, label
                if len(new_collected) >= TARGET:
                    return

        if driver.execute_script("return document.body.scrollHeight") == prev_h:
            break  # page didn't grow

    dim(f"    {label} → {new_this_query} new")


def _ensure_writable(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and not os.access(p, os.W_OK):
        err(f"Not writable: {p}")
        sys.exit(1)


def _load_existing(p: Path) -> Set[str]:
    if not p.exists():
        return set()
    with p.open("r", newline="", encoding="utf-8") as f:
        return {r["username"].strip() for r in csv.DictReader(f) if r.get("username")}


def _write_raw(username: str, label: str):
    with _file_lock:
        hdr = not RAW_CSV.exists()
        with RAW_CSV.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["username", "url", "source"])
            if hdr:
                w.writeheader()
            w.writerow({
                "username": username,
                "url":      f"https://www.instagram.com/{username}/",
                "source":   label,
            })



def run_scraper():
    print(f"\n{C.BOLD}{C.CYAN}  ── Stage 1: City + Niche Hashtag Scraper ──{C.RESET}\n")

    if not SELENIUM_OK:
        err("Selenium not installed.  pip install selenium")
        dim("Also need Chrome + chromedriver on PATH.")
        return
    if not SESSIONS:
        err("No SESSION_IDS in .env")
        dim("Instagram hashtag pages require a logged-in session.")
        return

    _ensure_writable(RAW_CSV)
    all_seen:      Set[str] = _load_existing(RAW_CSV)
    new_collected: Set[str] = set()

    if all_seen:
        info(f"Already in CSV  →  {len(all_seen):,} usernames  (will not be re-added)")
    info(f"Target (NEW)    →  {TARGET:,} new usernames to add this run")
    queries = build_search_queries(CITY, NICHE)

    hashtag_queue:   Deque[str] = deque()
    queued_hashtags: Set[str]   = set()

    info(f"City          →  {CITY}")
    info(f"Niche         →  {NICHE}")
    info(f"Queries       →  {len(queries)}  "
         f"({sum(1 for q in queries if q['type']=='hashtag')} hashtags + "
         f"{sum(1 for q in queries if q['type']=='keyword')} keywords)  [shuffled]")
    info(f"Scroll rounds →  {MAX_SCROLL_ROUNDS} / page  |  Post clicks: {POST_CLICK_LIMIT} / query")
    info(f"Hashtag queue →  up to {MAX_HASHTAG_QUEUE} tags discovered from post captions")
    info(f"Sessions      →  {len(SESSIONS)}")
    print()

    driver = _create_driver()
    try:
        _inject_session(driver, SESSIONS[0])
        time.sleep(1)

        def _run_query(q: dict):
            if len(new_collected) >= TARGET:
                return 0
            remaining = TARGET - len(new_collected)
            info(f"Searching  {q['label']}  "
                 f"(need {remaining} more | added {len(new_collected):,} new so far)")
            count = 0
            for uname, src in _scroll_and_collect(
                driver, q, all_seen, new_collected, hashtag_queue, queued_hashtags
            ):
                _write_raw(uname, src)
                count += 1
            if count:
                ok(f"  {q['label']} → {count} new  (run total: {len(new_collected):,})")
            else:
                dim(f"  {q['label']} → 0 new")
            time.sleep(random.uniform(2.5, 6.0))
            return count
        for q in queries:
            if len(new_collected) >= TARGET:
                break
            _run_query(q)

        if len(new_collected) < TARGET and hashtag_queue:
            print()
            info(f"Phase 2 — following {len(hashtag_queue)} hashtags discovered from post captions")
            while hashtag_queue and len(new_collected) < TARGET:
                ht = hashtag_queue.popleft()
                q  = hashtag_to_query(ht)
                found(f"Caption hashtag  {q['label']}")
                _run_query(q)

    except KeyboardInterrupt:
        print(f"\n  Stopped — {len(new_collected):,} new usernames added to {RAW_CSV.name}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    print()
    total_in_csv = len(_load_existing(RAW_CSV))
    ok(f"This run added  →  {C.GREEN}{C.BOLD}{len(new_collected):,}{C.RESET} new usernames")
    ok(f"Total in CSV    →  {C.BOLD}{total_in_csv:,}{C.RESET} unique usernames  ({RAW_CSV.name})")
    if hashtag_queue:
        dim(f"  Unused caption hashtags still in queue: {len(hashtag_queue)}")
    print()


def show_queries():
    queries  = build_search_queries(CITY, NICHE)
    hashtags = [q for q in queries if q["type"] == "hashtag"]
    keywords = [q for q in queries if q["type"] == "keyword"]
    print(f"\n{C.BOLD}{C.CYAN}  Queries for CITY={CITY!r}  NICHE={NICHE!r}"
          f"  (shuffled — order changes each run){C.RESET}\n")
    print(f"  {C.BOLD}Hashtags ({len(hashtags)}):{C.RESET}")
    for q in hashtags:
        print(f"    {C.GREEN}{q['label']:<40}{C.RESET}  {q['url']}")
    print(f"\n  {C.BOLD}Keywords ({len(keywords)}):{C.RESET}")
    for q in keywords:
        print(f"    {C.CYAN}{q['label']:<55}{C.RESET}  {q['url']}")
    extras = _niche_extras(NICHE)
    print(f"\n  {C.BOLD}Niche-compatible extras for {NICHE!r}:{C.RESET}")
    print(f"    {', '.join(extras)}")
    print()


if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "help"
    if   cmd == "scrape":
        run_scraper()
    elif cmd == "reset":
        if RAW_CSV.exists():
            RAW_CSV.unlink()
            warn(f"Deleted {RAW_CSV.name}")
        run_scraper()
    elif cmd == "show":
        show_queries()
    else:
        print(__doc__)