"""Parse org-mode files for activities and personal records."""

import re
from pathlib import Path

ACTIVITIES_PATH = Path.home() / "dropbox/org/activities.org"
RECORDS_PATH = Path.home() / "dropbox/org/personal_records.org"

ACTIVITY_META = {
    "Road Biking": {"icon": "🚴", "color": "#3b82f6", "short": "ride"},
    "Indoor Cycling": {"icon": "🏠", "color": "#6366f1", "short": "indoor"},
    "Cycling": {"icon": "🚴", "color": "#3b82f6", "short": "ride"},
    "Running": {"icon": "🏃", "color": "#10b981", "short": "run"},
    "Other": {"icon": "💪", "color": "#8b5cf6", "short": "other"},
    "Strength Training": {"icon": "💪", "color": "#8b5cf6", "short": "gym"},
}


def activity_meta(type_str: str) -> dict:
    return ACTIVITY_META.get(type_str, {"icon": "⚡", "color": "#64748b", "short": "other"})


def _parse_org_table(lines: list[str]) -> list[dict]:
    """Parse an org-mode pipe table into a list of dicts."""
    rows = []
    headers = None
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            break
        # Skip separator rows like |---+---|
        inner = s.strip("|").replace("+", "").replace("-", "").replace(" ", "")
        if not inner:
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if headers is None:
            headers = cols
        else:
            rows.append(dict(zip(headers, cols)))
    return rows


def get_activities() -> dict:
    """Parse ~/dropbox/org/activities.org into structured data."""
    if not ACTIVITIES_PATH.exists():
        return {"year": None, "summary": [], "weeks": []}

    text = ACTIVITIES_PATH.read_text()
    lines = text.splitlines()

    result: dict = {"year": None, "summary": [], "weeks": []}

    title_m = re.search(r"TITLE: Garmin Activities (\d+)", text)
    if title_m:
        result["year"] = int(title_m.group(1))

    i = 0
    current_week: dict | None = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Summary table
        if stripped == "* Summary":
            i += 1
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            result["summary"] = _parse_org_table(table_lines)
            continue

        # Week heading: * Week 11 · March 2026
        wm = re.match(r"\* Week (\d+) · (.+)", stripped)
        if wm:
            if current_week:
                result["weeks"].append(current_week)
            current_week = {
                "number": int(wm.group(1)),
                "month": wm.group(2),
                "mod": 0,
                "vig": 0,
                "intensity": 0,
                "total_duration": "",
                "total_km": 0.0,
                "activities": [],
            }
            i += 1
            continue

        # Intensity line: /287 mod + 94 vig = 475 intensity min/
        if current_week and stripped.startswith("/") and "mod" in stripped:
            im = re.search(r"(\d+) mod \+ (\d+) vig = (\d+)", stripped)
            if im:
                current_week["mod"] = int(im.group(1))
                current_week["vig"] = int(im.group(2))
                current_week["intensity"] = int(im.group(3))
            i += 1
            continue

        # Activity table
        if current_week and stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            for row in _parse_org_table(table_lines):
                date_val = row.get("Date", "").strip()
                if date_val in ("Date", ""):
                    continue
                if date_val == "Total":
                    current_week["total_duration"] = row.get("Duration", "").strip()
                    try:
                        current_week["total_km"] = float(row.get("km", "0") or "0")
                    except ValueError:
                        pass
                else:
                    km_raw = row.get("km", "-").strip()
                    try:
                        km_val: float | None = float(km_raw)
                    except ValueError:
                        km_val = None
                    meta = activity_meta(row.get("Type", ""))
                    current_week["activities"].append({
                        "date": date_val,
                        "name": row.get("Activity", "").strip(),
                        "type": row.get("Type", "").strip(),
                        "duration": row.get("Duration", "").strip(),
                        "km": km_val,
                        "icon": meta["icon"],
                        "color": meta["color"],
                    })
            continue

        i += 1

    if current_week:
        result["weeks"].append(current_week)

    # Reverse so newest week is first
    result["weeks"] = list(reversed(result["weeks"]))
    return result


def get_personal_records() -> dict:
    """Parse ~/dropbox/org/personal_records.org into structured data."""
    if not RECORDS_PATH.exists():
        return {"cycling_prs": [], "running_prs": [], "segment_koms": []}

    text = RECORDS_PATH.read_text()
    lines = text.splitlines()

    result: dict = {"cycling_prs": [], "running_prs": [], "cycling_power_prs": [], "segment_koms": []}

    section: str | None = None
    subsection: str | None = None  # "time" or "power"
    current_dist: dict | None = None
    current_power: dict | None = None
    current_seg: dict | None = None
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped == "* Cycling PRs":
            section = "cycling"
            subsection = None
            i += 1
            continue
        elif stripped == "* Running PRs":
            section = "running"
            subsection = None
            i += 1
            continue
        elif stripped == "* Segment KOMs":
            if current_seg:
                result["segment_koms"].append(current_seg)
                current_seg = None
            section = "koms"
            subsection = None
            i += 1
            continue

        if section in ("cycling", "running"):
            # Level-2 heading — determine subsection
            if re.match(r"\*\* ", stripped):
                current_dist = None
                current_power = None
                if "Max average power" in stripped:
                    subsection = "power"
                else:
                    subsection = "time"
                i += 1
                continue

            if subsection == "power" and section == "cycling":
                pm = re.match(r"\*\*\* ([\d.]+ min)", stripped)
                if pm:
                    current_power = {"duration": pm.group(1), "entries": []}
                    result["cycling_power_prs"].append(current_power)
                    i += 1
                    continue
                if stripped.startswith("|") and current_power is not None:
                    table_lines = []
                    while i < len(lines) and lines[i].strip().startswith("|"):
                        table_lines.append(lines[i])
                        i += 1
                    current_power["entries"] = [
                        e for e in _parse_org_table(table_lines)
                        if e.get("Rank", "").strip() not in ("Rank", "")
                    ]
                    continue
            else:
                dm = re.match(r"\*\*\* ([\d.]+) km", stripped)
                if dm:
                    current_dist = {"distance": float(dm.group(1)), "entries": []}
                    target = result["cycling_prs"] if section == "cycling" else result["running_prs"]
                    target.append(current_dist)
                    i += 1
                    continue
                # Only attach tables when we're inside a km-distance block
                if stripped.startswith("|") and current_dist is not None:
                    table_lines = []
                    while i < len(lines) and lines[i].strip().startswith("|"):
                        table_lines.append(lines[i])
                        i += 1
                    current_dist["entries"] = [
                        e for e in _parse_org_table(table_lines)
                        if e.get("Rank", "").strip() not in ("Rank", "")
                    ]
                    continue

        elif section == "koms":
            sm = re.match(r"\*\* (SEG-.+)", stripped)
            if sm:
                if current_seg:
                    result["segment_koms"].append(current_seg)
                current_seg = {
                    "name": sm.group(1).strip(),
                    "display_name": sm.group(1).replace("SEG-", "").replace("-", " ").strip(),
                    "distance": None,
                    "ascent": None,
                    "descent": None,
                    "best_time": None,
                    "is_kom": False,
                    "matches": 0,
                    "leaderboard": [],
                }
                i += 1
                continue

            if current_seg:
                dm2 = re.match(r"- Distance: ([\d.]+) km", stripped)
                if dm2:
                    current_seg["distance"] = float(dm2.group(1))

                am = re.match(r"- Ascent: (\d+) m", stripped)
                if am:
                    current_seg["ascent"] = int(am.group(1))

                bm = re.match(r"- Best: ([\d:]+)(.*)", stripped)
                if bm:
                    current_seg["best_time"] = bm.group(1)
                    current_seg["is_kom"] = "(KOM)" in bm.group(2)

                mm = re.match(r"- Matches: (\d+)", stripped)
                if mm:
                    current_seg["matches"] = int(mm.group(1))

                if stripped.startswith("|"):
                    table_lines = []
                    while i < len(lines) and lines[i].strip().startswith("|"):
                        table_lines.append(lines[i])
                        i += 1
                    current_seg["leaderboard"] = [
                        e for e in _parse_org_table(table_lines)
                        if e.get("Rank", "").strip() not in ("Rank", "")
                    ]
                    continue

        i += 1

    if current_seg:
        result["segment_koms"].append(current_seg)

    return result
