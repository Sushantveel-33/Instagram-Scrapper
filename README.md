# Location-based Users Scraper Documentation

## 1. Overview

The **Location-based Users Scraper** is an automated Instagram data collection tool built using Python and Selenium. The scraper discovers Instagram usernames related to a specific **city** and **content niche** (e.g., Food, Fitness, Travel, Fashion).

The system generates niche-specific hashtags and keyword searches, visits Instagram pages, extracts usernames from posts, identifies tagged users, discovers new hashtags from captions, and stores unique usernames in a CSV file.

---

# 2. Objectives

The scraper aims to:

* Find Instagram creators from a specific city and niche.
* Generate dynamic search queries automatically.
* Extract post owner usernames.
* Extract tagged usernames from posts.
* Discover additional hashtags from posts.
* Continuously expand search coverage.
* Avoid duplicate usernames.
* Save collected usernames for later validation and processing.

---

# 3. Features

### Dynamic Query Generation

Creates hashtags and keyword searches using:

* CITY
* NICHE

Example:

CITY = San Francisco

NICHE = Food

Generated hashtags:

* #sffood
* #sffoodie
* #sanfranciscofood
* #fooddblogger

Generated keywords:

* "san francisco food blogger"
* "best food in san francisco"
* "food influencer san francisco"

---

### Randomized Search Order

Queries are shuffled before execution to:

* Reduce repetitive scraping patterns.
* Improve discovery of unique users.
* Minimize Instagram detection risks.

---

### Username Extraction

The scraper collects usernames from:

1. Search page source.
2. Post owner accounts.
3. Tagged users in captions.

---

### Hashtag Discovery

The scraper scans captions for hashtags:

Example:

Caption:

#foodie #restaurant #brunch

Discovered hashtags are queued for future searches.

---

### Deduplication

Duplicate usernames are prevented using:

* Existing CSV records.
* Runtime memory tracking.
* Caption extraction filtering.

---

### Session-Based Authentication

Uses Instagram session cookies stored in:

```env
SESSION_IDS=
```

This allows scraping while logged into Instagram.

---

# 4. Project Workflow

## Project Structure

```
project/
├── scraper.py          # Main scraper (this file)
├── .env                # Configuration (not committed to git)
├── requirements.txt    # dependencies
└── raw_usernames.csv   # Output — created/appended on each run
```
---

## Requirements

- Python 3.8+
- Google Chrome (stable)
- `chromedriver` matching your Chrome version, available on `PATH`
- A valid Instagram session cookie (`sessionid`)

---

## Run Scraper

```bash
python scraper.py 
```

Starts scraping and appends new usernames.

---

## Step 1: Load Configuration

The scraper loads environment variables from:

```.env
CITY=New York
NICHE=food
TARGET=200
MAX_SCROLL_ROUNDS=6
SCROLL_PAUSE=1.5
POST_CLICK_LIMIT=25
PAGE_TIMEOUT=30
HEADLESS=true
SESSION_COOLDOWN=10
SESSION_MAX_FAILS=3
MAX_HASHTAG_QUEUE=40
SESSION_IDS=your_session_id_here
EXTRA_HASHTAGS=
EXTRA_KEYWORDS=

---

## Step 2: Generate Search Queries

Function:

```python
build_search_queries()

```

Creates:

* Hashtag searches
* Keyword searches

based on city and niche combinations.

---

## Step 3: Open Instagram Page

Selenium launches Chrome and navigates to:

```text
https://www.instagram.com/
```

Session cookies are injected to authenticate the user.

---

## Step 4: Search Hashtags/Keywords

The scraper visits generated URLs such as:

```text
https://www.instagram.com/explore/tags/sffood/
```

or

```text
https://www.instagram.com/explore/search/?q=san francisco food blogger
```

---

## Step 5: Scroll and Collect Posts

Function:

```python
_scroll_and_collect()
```

Performs:

* Page scrolling
* Post discovery
* Username extraction

---

## Step 6: Open Posts

Function:

```python
_click_post_and_extract()
```

Actions:

* Click post
* Extract owner username
* Extract tagged users
* Extract hashtags

---

## Step 7: Expand Search Coverage

New hashtags discovered from captions are added to:

```python
hashtag_queue
```

and processed later.

---

## Step 8: Save Results

Usernames are stored in:

```text
raw_usernames.csv
```

Format:

| username  | url                     | source      |
| --------- | ----------------------- | ----------- |
| foodie123 | instagram.com/foodie123 | #sffood     |
| chef_john | instagram.com/chef_john | caption tag |

---


## Niche Keywords Reference

The following niches have built-in synonym expansion. Any other value falls back to generic creator terms (`blogger`, `creator`, `influencer`, etc.).

| Niche           | Example Synonyms                                      |
|-----------------|-------------------------------------------------------|
| `food`          | foodie, chef, instafood, dining, restaurant, brunch   |
| `fitness`       | gym, workout, gains, crossfit, yoga, athlete          |
| `fashion`       | ootd, streetwear, lookbook, fashionista, couture      |
| `travel`        | wanderlust, nomad, backpacker, roadtrip, adventure    |
| `beauty`        | makeup, skincare, mua, haircare, glow, nails          |
| `lifestyle`     | vlog, blogger, selfcare, mindfulness, wellness        |
| `technology`    | coding, developer, startup, ai, machinelearning       |
| `gaming`        | gamer, esports, twitch, fps, pcgaming                 |
| `music`         | musician, dj, producer, hiphop, songwriter            |
| `art`           | artist, illustration, digitalart, sketch, gallery     |
| `health`        | nutrition, meditation, holistic, mentalhealth         |
| `sports`        | athlete, soccer, marathon, running, champion          |
| `dance`         | choreography, ballet, contemporary, performance       |
| `education`     | teacher, tutorial, edtech, academic, university       |
| `business`      | entrepreneur, ceo, branding, hustle, networking       |
| `finance`       | investing, crypto, trading, fintech, bitcoin          |
| `comedy`        | meme, viral, comedian, parody, satire                 |
| `family`        | parenting, motherhood, fatherhood, toddler            |
| `pets`          | dogsofinstagram, catsofinstagram, rescue, wildlife    |
| `entertainment` | movie, streaming, popculture, celebrity, netflix      |


## Key Functions & Classes

### `build_search_queries(city, niche) → List[dict]`
Generates all hashtag and keyword queries from `CITY` and `NICHE`. Produces variations using city abbreviations, compound forms, niche synonyms, and user-supplied extras. Returns a shuffled list of query dicts, each containing `type`, `label`, `value`, and `url`.

### `hashtag_to_query(tag) → dict`
Converts a raw hashtag string (e.g. `"nycfood"`) into a standard query dict pointing to the Instagram explore/tags URL.

### `SessionManager`
Manages a pool of Instagram session cookies. Rotates sessions round-robin, enforces cooldown gaps between reuses, and pauses sessions that hit rate limits or repeated failures.

| Method          | Description                                                    |
|-----------------|----------------------------------------------------------------|
| `get_sid()`     | Returns the next available session ID, respecting cooldowns    |
| `ok(sid)`       | Reports a successful use; decrements the failure counter       |
| `fail(sid, ...)`| Increments failures; pauses the session if threshold is reached|

### `_create_driver() → WebDriver`
Initialises a Chrome WebDriver with hardened options (no sandbox, headless mode if configured, spoofed user-agent).

### `_inject_session(driver, sid)`
Navigates to Instagram and injects the `sessionid` cookie so the browser is authenticated.

### `_scroll_and_collect(driver, query, ...) → Generator`
Core scraping loop for a single query. Loads the page, scans the source for usernames, clicks posts up to `POST_CLICK_LIMIT`, scrolls up to `MAX_SCROLL_ROUNDS` times, and yields `(username, source_label)` tuples.

### `_click_post_and_extract(driver, post_el, ...) → (username, caption_users)`
Clicks a post element, waits for it to load, then extracts the post owner's username via DOM inspection and JSON regex fallbacks. Also parses the caption for `@mentions` and `#hashtags`.

### `_extract_caption_data(page) → (tagged_users, found_hashtags)`
Parses raw page HTML to extract `@mentioned` usernames and `#hashtags` from post caption text using regex.

### `_source_usernames(page) → Set[str]`
Scans raw page HTML for `"username": "..."` JSON patterns and returns a set of valid, non-system usernames.

### `_write_raw(username, label)`
Thread-safe append of a single row to `raw_usernames.csv`. Writes the CSV header automatically if the file is new.

### `run_scraper()`
Main entry point for the `scrape` and `reset` commands. Orchestrates session setup, Phase 1 query iteration, and Phase 2 caption-hashtag follow-up.

### `show_queries()`
Dry-run command that prints all generated hashtag and keyword queries plus the niche synonym list — no browser opened.

---

# Conclusion

The Instagram City + Niche Hashtag Scraper is a creator discovery system that uses Instagram hashtags, keyword searches, caption analysis, and hashtag expansion techniques to collect niche-specific Instagram usernames from targeted geographic regions. It provides a scalable foundation for influencer discovery, lead generation, and social media research workflows.
