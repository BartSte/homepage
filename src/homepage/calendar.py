"""Fetch and parse calendar events from khal CLI."""

import re
import subprocess
import time
from datetime import date, datetime, timedelta

_cache: dict = {}
CACHE_TTL = 120  # 2 minutes — calendar changes more often


def _cached(key: str, fetch_fn):
    now = time.time()
    if key in _cache and now - _cache[key]["ts"] < CACHE_TTL:
        return _cache[key]["data"]
    data = fetch_fn()
    _cache[key] = {"ts": now, "data": data}
    return data


CALENDAR_COLORS = {
    "outlook_work": {"dot": "#3b82f6", "bg": "rgba(59,130,246,0.12)", "label": "work"},
    "outlook_personal": {"dot": "#10b981", "bg": "rgba(16,185,129,0.12)", "label": "personal"},
}


def _cal_meta(cal: str) -> dict:
    return CALENDAR_COLORS.get(cal, {"dot": "#64748b", "bg": "rgba(100,116,139,0.1)", "label": cal})


def _khal_date(d: date) -> str:
    return d.strftime("%Y-%m-%d %a")


def get_events(days_ahead: int = 21) -> list[dict]:
    """Return a list of day dicts covering today + days_ahead."""

    def fetch():
        today = date.today()
        end = today + timedelta(days=days_ahead)
        try:
            result = subprocess.run(
                [
                    "khal", "list",
                    _khal_date(today),
                    _khal_date(end),
                    "--format",
                    "{start-date}|{start-time}|{end-time}|{calendar}|{title}|{all-day}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            raw = result.stdout
        except Exception:
            raw = ""

        # Parse into events keyed by date string
        events_by_date: dict[str, list] = {}
        for line in raw.splitlines():
            line = line.strip()
            # Skip day header lines
            if not "|" in line:
                continue
            parts = line.split("|")
            if len(parts) < 6:
                continue
            raw_date, start, end, cal, title, all_day = parts[:6]
            # Extract YYYY-MM-DD from "2026-03-18 Wed"
            date_m = re.match(r"(\d{4}-\d{2}-\d{2})", raw_date.strip())
            if not date_m:
                continue
            d = date_m.group(1)
            meta = _cal_meta(cal.strip())
            event = {
                "title": title.strip(),
                "start": start.strip(),
                "end": end.strip(),
                "cal": cal.strip(),
                "all_day": all_day.strip() == "True",
                "dot": meta["dot"],
                "bg": meta["bg"],
                "label": meta["label"],
            }
            events_by_date.setdefault(d, []).append(event)

        # Build day list
        days = []
        today_str = today.isoformat()
        for offset in range(days_ahead + 1):
            d = today + timedelta(days=offset)
            d_str = d.isoformat()
            dow = d.strftime("%A")
            dom = d.strftime("%-d")
            month = d.strftime("%B")
            day_events = events_by_date.get(d_str, [])
            # Deduplicate all-day events (khal repeats them for each day)
            seen_titles = set()
            deduped = []
            for e in day_events:
                key = (e["title"], e["all_day"])
                if e["all_day"] and key in seen_titles:
                    continue
                seen_titles.add(key)
                deduped.append(e)
            # Sort: all-day first, then by start time
            deduped.sort(key=lambda e: ("" if e["all_day"] else e["start"]))
            days.append({
                "date": d_str,
                "dow": dow,
                "dom": dom,
                "month": month,
                "is_today": d_str == today_str,
                "is_weekend": d.weekday() >= 5,
                "events": deduped,
                "event_count": len(deduped),
            })
        return days

    return _cached("events", fetch)


def get_today_events() -> list[dict]:
    days = get_events(0)
    return days[0]["events"] if days else []
