#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests
import yaml
from dateutil import parser as date_parser

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.yaml"
SITE_DATA = ROOT / "site" / "data"
SITE_DATA.mkdir(parents=True, exist_ok=True)

USER_AGENT = "RSS-News-Aggregator/1.0 (+https://github.com/)"

def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = date_parser.parse(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def interval_seconds(value: str | None, default: str = "30m") -> int:
    value = (value or default).strip().lower()
    m = re.fullmatch(r"(\d+)\s*([mhd])", value)
    if not m:
        raise ValueError(f"Invalid interval: {value}")
    n = int(m.group(1))
    unit = {"m": 60, "h": 3600, "d": 86400}[m.group(2)]
    return n * unit

def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

def clean_html(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def article_id(source: str, entry: Any) -> str:
    guid = entry.get("id") or entry.get("guid") or entry.get("link") or entry.get("title")
    raw = f"{source}\n{guid}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

def should_refresh(state: dict[str, Any], feed: dict[str, Any], default_interval: str) -> bool:
    last = parse_dt(state.get("last_attempt"))
    if not last:
        return True
    interval = interval_seconds(feed.get("refresh"), default_interval)
    return (now_utc() - last).total_seconds() >= interval

def fetch_feed(feed: dict[str, Any], state: dict[str, Any], default_interval: str) -> dict[str, Any]:
    name = feed["name"]
    url = feed["url"]
    old = state.get(url, {})
    result = {
        "name": name,
        "url": url,
        "category": feed.get("category", "uncategorized"),
        "enabled": bool(feed.get("enabled", True)),
        "skipped": False,
        "success": False,
        "status": None,
        "error": None,
        "articles": [],
        "fetched_at": iso(now_utc()),
    }

    if not feed.get("enabled", True):
        result["skipped"] = True
        result["reason"] = "disabled"
        return result

    if not should_refresh(old, feed, default_interval):
        result["skipped"] = True
        result["reason"] = "not_due"
        result["last_success"] = old.get("last_success")
        return result

    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"}
    if old.get("etag"):
        headers["If-None-Match"] = old["etag"]
    if old.get("last_modified"):
        headers["If-Modified-Since"] = old["last_modified"]

    new_state = dict(old)
    new_state["last_attempt"] = iso(now_utc())

    last_exc = None
    response = None
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=25)
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            break
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(2 ** attempt)

    if response is None:
        result["error"] = str(last_exc or "request failed")
        state[url] = new_state
        return result

    result["status"] = response.status_code

    if response.status_code == 304:
        new_state["last_success"] = old.get("last_success")
        new_state["etag"] = old.get("etag")
        new_state["last_modified"] = old.get("last_modified")
        state[url] = new_state
        result["success"] = True
        result["not_modified"] = True
        result["last_success"] = new_state.get("last_success")
        return result

    try:
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise ValueError(f"feed parse error: {getattr(parsed, 'bozo_exception', 'unknown')}")
    except Exception as exc:
        result["error"] = str(exc)
        state[url] = new_state
        return result

    feed_title = parsed.feed.get("title") or name
    articles = []

    for entry in parsed.entries:
        published = (
            parse_dt(entry.get("published"))
            or parse_dt(entry.get("updated"))
            or parse_dt(entry.get("created"))
        )
        link = entry.get("link") or ""
        title = clean_html(entry.get("title") or "(untitled)")
        summary = clean_html(entry.get("summary") or entry.get("description") or "")
        if not link or not title:
            continue

        articles.append({
            "id": article_id(name, entry),
            "source": name,
            "source_title": feed_title,
            "category": feed.get("category", "uncategorized"),
            "title": title,
            "summary": summary[:2000],
            "url": link,
            "published": iso(published) if published else None,
        })

    new_state["etag"] = response.headers.get("ETag")
    new_state["last_modified"] = response.headers.get("Last-Modified")
    new_state["last_success"] = iso(now_utc())
    new_state["last_status"] = response.status_code
    new_state["last_error"] = None
    state[url] = new_state

    result["success"] = True
    result["articles"] = articles
    result["last_success"] = new_state["last_success"]
    return result

def main() -> int:
    cfg = load_yaml(CONFIG)
    default_interval = cfg.get("schedule", {}).get("interval", "30m")
    storage = cfg.get("storage", {})
    retention_days = int(storage.get("retention_days", 30))
    max_articles = int(storage.get("max_articles", 5000))
    state_path = ROOT / storage.get("state_file", "site/data/feed_state.json")
    state_path.parent.mkdir(parents=True, exist_ok=True)

    state = load_json(state_path, {})
    existing = load_json(SITE_DATA / "news.json", [])
    existing = existing if isinstance(existing, list) else []

    feeds = [f for f in cfg.get("feeds", []) if isinstance(f, dict)]
    results = []

    with ThreadPoolExecutor(max_workers=min(12, max(1, len(feeds)))) as executor:
        futures = [
            executor.submit(fetch_feed, f, state, default_interval)
            for f in feeds
        ]
        for future in as_completed(futures):
            results.append(future.result())

    new_articles = []
    for result in results:
        new_articles.extend(result.get("articles", []))

    by_id = {a["id"]: a for a in existing if isinstance(a, dict) and a.get("id")}
    for article in new_articles:
        by_id[article["id"]] = article

    cutoff = now_utc() - timedelta(days=retention_days)
    articles = []
    for article in by_id.values():
        dt = parse_dt(article.get("published"))
        if dt and dt < cutoff:
            continue
        articles.append(article)

    articles.sort(
        key=lambda x: parse_dt(x.get("published")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    articles = articles[:max_articles]

    sources = []
    for f in feeds:
        st = state.get(f.get("url"), {})
        sources.append({
            "name": f.get("name"),
            "url": f.get("url"),
            "category": f.get("category", "uncategorized"),
            "enabled": bool(f.get("enabled", True)),
            "refresh": f.get("refresh") or default_interval,
            "last_attempt": st.get("last_attempt"),
            "last_success": st.get("last_success"),
            "last_status": st.get("last_status"),
            "last_error": st.get("last_error"),
        })

    successes = sum(1 for r in results if r["success"])
    failures = sum(1 for r in results if not r["success"] and not r["skipped"])
    skipped = sum(1 for r in results if r["skipped"])

    update = {
        "updated": iso(now_utc()),
        "feeds": len(feeds),
        "success": successes,
        "failed": failures,
        "skipped": skipped,
        "articles": len(articles),
        "retention_days": retention_days,
    }

    save_json(SITE_DATA / "news.json", articles)
    save_json(SITE_DATA / "sources.json", sources)
    save_json(SITE_DATA / "update.json", update)
    save_json(state_path, state)

    # config.yaml is the single source of truth for public site metadata.
    site_cfg = cfg.get("site", {})
    save_json(ROOT / "site" / "config-public.json", {
        "site": {
            "title": site_cfg.get("title", ""),
            "description": site_cfg.get("description", ""),
        }
    })

    print(json.dumps(update, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
