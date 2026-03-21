import os
import time
from datetime import datetime
from pathlib import Path

import psutil
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from homepage import calendar, github, parser

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

START_TIME = time.time()


# ── Landing page ───────────────────────────────────────────────────────────────

@app.get("/")
async def index(request: Request):
    # Quick stats for the landing page
    activities = parser.get_activities()
    latest_week = activities["weeks"][0] if activities["weeks"] else None
    return templates.TemplateResponse("index.html", {
        "request": request,
        "active": "home",
        "latest_week": latest_week,
    })


# ── Activities ─────────────────────────────────────────────────────────────────

@app.get("/activities")
async def activities_page(request: Request):
    data = parser.get_activities()
    # Compute YTD totals
    total_km = sum(w["total_km"] for w in data["weeks"])
    total_intensity = sum(w["intensity"] for w in data["weeks"])
    # Parse HH:MM:SS durations and sum seconds
    total_seconds = 0
    for w in data["weeks"]:
        d = w.get("total_duration", "")
        parts = d.split(":")
        try:
            if len(parts) == 3:
                total_seconds += int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                total_seconds += int(parts[0]) * 3600 + int(parts[1]) * 60
        except Exception:
            pass
    total_hours = total_seconds // 3600
    total_minutes = (total_seconds % 3600) // 60

    max_intensity = max((w["intensity"] for w in data["weeks"]), default=1)

    return templates.TemplateResponse("activities.html", {
        "request": request,
        "active": "activities",
        "data": data,
        "total_km": f"{total_km:.0f}",
        "total_time": f"{total_hours}h {total_minutes}m",
        "total_intensity": f"{total_intensity}",
        "max_intensity": max_intensity,
    })


# ── KOMs & PRs ────────────────────────────────────────────────────────────────

@app.get("/koms")
async def koms_page(request: Request):
    records = parser.get_personal_records()
    kom_count = sum(1 for s in records["segment_koms"] if s["is_kom"])
    return templates.TemplateResponse("koms.html", {
        "request": request,
        "active": "koms",
        "records": records,
        "kom_count": kom_count,
    })


# ── Calendar ──────────────────────────────────────────────────────────────────

@app.get("/calendar")
async def calendar_page(request: Request):
    days = calendar.get_events(days_ahead=21)
    today_events = days[0]["events"] if days else []
    # Group into weeks for display
    weeks: list[list] = []
    current_week: list = []
    for day in days:
        current_week.append(day)
        if day["dow"] == "Sunday" or day == days[-1]:
            weeks.append(current_week)
            current_week = []
    if current_week:
        weeks.append(current_week)
    return templates.TemplateResponse("calendar.html", {
        "request": request,
        "active": "calendar",
        "days": days,
        "weeks": weeks,
        "today_events": today_events,
    })


@app.get("/api/calendar/day/{date_str}")
async def calendar_day(date_str: str):
    """htmx fragment: full event list for a specific date."""
    from homepage.calendar import get_events
    from datetime import date
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        return HTMLResponse('<p style="color:var(--red)">Invalid date</p>')

    days = get_events(days_ahead=21)
    day = next((d for d in days if d["date"] == date_str), None)
    if not day:
        return HTMLResponse('<p style="color:var(--muted);font-size:.85rem;">No data for this date.</p>')

    dow = target.strftime("%A")
    dom = target.strftime("%-d")
    month = target.strftime("%B %Y")

    if not day["events"]:
        body = '<p style="color:var(--muted);font-size:.85rem;padding:4px 0;">Nothing scheduled — enjoy the free day 🎉</p>'
    else:
        rows = []
        for e in day["events"]:
            if e["all_day"]:
                time_str = "all day"
            else:
                time_str = f"{e['start']}–{e['end']}"
            rows.append(f'''<div class="detail-event">
  <span class="detail-dot" style="background:{e['dot']};"></span>
  <span class="detail-time">{time_str}</span>
  <span class="detail-title">{e['title']}</span>
  <span class="detail-cal" style="color:{e['dot']};background:{e['bg']};">{e['label']}</span>
</div>''')
        body = "\n".join(rows)

    html = f'''<div class="detail-header">
  <span class="detail-dow">{dow}</span>
  <span class="detail-date">{dom} {month}</span>
  <button class="detail-close" onclick="document.getElementById('day-detail').innerHTML=''">✕</button>
</div>
{body}'''
    return HTMLResponse(html)


@app.get("/api/calendar-today")
async def calendar_today():
    """htmx fragment: today's events."""
    from homepage.calendar import get_today_events
    calendar._cache.clear()  # force refresh
    events = get_today_events()
    if not events:
        return HTMLResponse('<p style="color:var(--muted);font-size:.85rem;padding:4px 0;">Nothing scheduled today 🎉</p>')
    parts = []
    for e in events:
        if e["all_day"]:
            time_str = "all day"
        else:
            time_str = f"{e['start']}–{e['end']}"
        parts.append(f'''<div class="today-event">
  <span class="today-dot" style="background:{e['dot']};"></span>
  <span class="today-time">{time_str}</span>
  <span class="today-title">{e['title']}</span>
</div>''')
    return HTMLResponse("\n".join(parts))


# ── GitHub ────────────────────────────────────────────────────────────────────

@app.get("/github")
async def github_page(request: Request):
    repos = github.get_repos()
    open_prs = github.get_open_prs()
    commits = github.get_recent_commits()
    return templates.TemplateResponse("github.html", {
        "request": request,
        "active": "github",
        "repos": repos,
        "open_prs": open_prs,
        "commits": commits,
    })


# ── Picnic ────────────────────────────────────────────────────────────────────

@app.get("/picnic")
async def picnic_page(request: Request):
    import sqlite3
    from pathlib import Path
    try:
        conn = sqlite3.connect(Path.home() / ".openclaw/picnic/staples.db")
        recipes_count = conn.execute("SELECT COUNT(*) FROM recipes WHERE active=1").fetchone()[0]
        conn.close()
    except Exception:
        recipes_count = 0
    return templates.TemplateResponse("picnic.html", {
        "request": request,
        "active": "picnic",
        "recipes_count": recipes_count,
    })


@app.get("/api/picnic/status")
async def picnic_status():
    """htmx fragment: Picnic order status and cart summary."""
    import json
    import subprocess
    from pathlib import Path

    venv_python = Path.home() / ".openclaw/picnic/.venv/bin/python"
    tools_py = Path.home() / ".openclaw/picnic/picnic_tools.py"

    try:
        result = subprocess.run(
            [str(venv_python), str(tools_py), "get_status"],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)
    except Exception as e:
        return HTMLResponse(f'<p style="color:var(--red);font-size:.85rem;">Error: {e}</p>')

    if not data.get("ok"):
        return HTMLResponse(f'<p style="color:var(--red);font-size:.85rem;">{data.get("error","Unknown error")}</p>')

    today = data.get("today", "")
    next_order = data.get("next_order_date")
    last_delivery = data.get("last_delivery_date", "—")
    due_count = len(data.get("staples_due", []))
    total_staples = data.get("total_staples", 0)
    feedback_count = data.get("unapplied_feedback", 0)

    if next_order:
        from datetime import date
        today_dt = date.fromisoformat(today)
        next_dt = date.fromisoformat(next_order)
        delta = (next_dt - today_dt).days
        if delta < 0:
            schedule_html = f'<span style="color:var(--red)">⚠ overdue by {abs(delta)} days</span>'
        elif delta == 0:
            schedule_html = '<span style="color:var(--accent)">📦 order due today</span>'
        else:
            schedule_html = f'<span style="color:var(--green)">✓ next order in {delta} days ({next_order})</span>'
    else:
        schedule_html = '<span style="color:var(--muted)">not scheduled yet</span>'

    due_color = "var(--red)" if due_count > 0 else "var(--green)"

    html = f"""
<div class="picnic-stat"><span class="picnic-label">schedule</span><span class="picnic-val">{schedule_html}</span></div>
<div class="picnic-stat"><span class="picnic-label">last delivery</span><span class="picnic-val">{last_delivery or "—"}</span></div>
<div class="picnic-stat"><span class="picnic-label">staples due</span><span class="picnic-val" style="color:{due_color}">{due_count} / {total_staples}</span></div>
<div class="picnic-stat"><span class="picnic-label">pending feedback</span><span class="picnic-val">{feedback_count}</span></div>
"""
    return HTMLResponse(html)


@app.get("/api/picnic/recipes")
async def picnic_recipes():
    """htmx fragment: full recipe list with ingredients."""
    import json
    import sqlite3
    from pathlib import Path

    db_path = Path.home() / ".openclaw/picnic/staples.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    recipes = conn.execute("SELECT * FROM recipes WHERE active=1 ORDER BY cuisine, name").fetchall()

    if not recipes:
        conn.close()
        return HTMLResponse('<p style="color:var(--muted);font-size:.85rem;">No recipes yet.</p>')

    # Group by cuisine
    from collections import defaultdict
    by_cuisine = defaultdict(list)
    for r in recipes:
        r = dict(r)
        ings = conn.execute(
            "SELECT * FROM recipe_ingredients WHERE recipe_id=? ORDER BY id", (r["id"],)
        ).fetchall()
        r["ingredients"] = [dict(i) for i in ings]
        by_cuisine[r["cuisine"] or "Overig"].append(r)
    conn.close()

    html = ""
    for cuisine, rlist in sorted(by_cuisine.items()):
        html += f'<div class="cuisine-group"><h3 class="cuisine-title">{cuisine}</h3>'
        for r in rlist:
            known = sum(1 for i in r["ingredients"] if i.get("preferred_product_id"))
            total = len(r["ingredients"])
            pct = int(known / total * 100) if total else 0
            bar_color = "#10b981" if pct == 100 else "#f59e0b" if pct >= 50 else "#ef4444"
            def _ing_html(i):
                known = bool(i.get("preferred_product_id"))
                cls = "ing-known" if known else "ing-unknown"
                icon = "✓" if known else "?"
                product = f' <span class="ing-product">{i["preferred_product_name"]}</span>' if i.get("preferred_product_name") else ""
                return f'<li class="ing-item {cls}">{icon} {i["ingredient_name"]}{product}</li>'
            ing_list = "".join(_ing_html(i) for i in r["ingredients"])
            html += f"""<div class="recipe-card">
  <div class="recipe-head">
    <span class="recipe-name">{r["name"]}</span>
    <span class="recipe-servings">{r["servings"]}p</span>
  </div>
  <div class="recipe-notes">{r["notes"] or ""}</div>
  <div class="recipe-progress">
    <div class="progress-bar">
      <div class="progress-fill" style="width:{pct}%;background:{bar_color}"></div>
    </div>
    <span class="progress-label">{known}/{total} producten bekend</span>
  </div>
  <ul class="ing-list">{ing_list}</ul>
</div>"""
        html += '</div>'

    return HTMLResponse(html)


@app.get("/api/picnic/meals")
async def picnic_meals():
    """htmx fragment: recent meals ordered."""
    import json
    import subprocess
    from pathlib import Path

    venv_python = Path.home() / ".openclaw/picnic/.venv/bin/python"
    tools_py = Path.home() / ".openclaw/picnic/picnic_tools.py"

    try:
        result = subprocess.run(
            [str(venv_python), str(tools_py), "get_meal_history", "8"],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)
    except Exception as e:
        return HTMLResponse(f'<p style="color:var(--red);font-size:.85rem;">Error: {e}</p>')

    meals = data.get("meals", [])
    if not meals:
        return HTMLResponse('<p style="color:var(--muted);font-size:.85rem;">No meal history yet.</p>')

    # Group by order_date
    from collections import defaultdict
    by_date = defaultdict(list)
    for m in meals:
        by_date[m["order_date"]].append(m)

    html = ""
    for date, items in sorted(by_date.items(), reverse=True):
        html += f'<div class="meal-week"><span class="meal-date">{date}</span>'
        for m in items:
            cuisine = f' <span class="meal-cuisine">{m["cuisine"]}</span>' if m.get("cuisine") else ""
            html += f'<div class="meal-row">🍽 {m["name"]}{cuisine}</div>'
        html += '</div>'

    return HTMLResponse(html)


@app.get("/api/picnic/staples")
async def picnic_staples():
    """htmx fragment: staples table."""
    import json
    import subprocess
    from pathlib import Path

    venv_python = Path.home() / ".openclaw/picnic/.venv/bin/python"
    tools_py = Path.home() / ".openclaw/picnic/picnic_tools.py"

    try:
        result = subprocess.run(
            [str(venv_python), str(tools_py), "staple_list"],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)
    except Exception as e:
        return HTMLResponse(f'<p style="color:var(--red);font-size:.85rem;">Error: {e}</p>')

    staples = data.get("staples", [])
    if not staples:
        return HTMLResponse('<p style="color:var(--muted);font-size:.85rem;">No staples tracked yet.</p>')

    rows = ""
    for s in staples:
        due = s.get("is_due", False)
        badge = '<span class="badge badge-due">due</span>' if due else '<span class="badge badge-ok">ok</span>'
        last = s.get("last_ordered_date") or "—"
        next_due = s.get("next_due") or "—"
        interval = s.get("reorder_interval_days", "?")
        rows += f"""<tr>
  <td>{s['name']}</td>
  <td>{badge}</td>
  <td style="font-family:var(--mono);font-size:.8rem;color:var(--muted)">{last}</td>
  <td style="font-family:var(--mono);font-size:.8rem;color:var(--muted)">{next_due}</td>
  <td style="font-family:var(--mono);font-size:.8rem;color:var(--muted)">{interval}d</td>
</tr>"""

    return HTMLResponse(f"""<table class="staples-table">
  <thead><tr>
    <th>item</th><th>status</th><th>last ordered</th><th>next due</th><th>interval</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>""")


# ── Live system stats (htmx) ──────────────────────────────────────────────────

@app.get("/api/stats")
async def stats():
    try:
        temp_raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
        temp_c = int(temp_raw) / 1000.0
    except Exception:
        temp_c = None

    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    mem_used_mb = mem.used / 1024 / 1024
    mem_total_mb = mem.total / 1024 / 1024

    uptime_seconds = int(time.time() - psutil.boot_time())
    days, rem = divmod(uptime_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    uptime_str = f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m"

    load = os.getloadavg()
    load_str = f"{load[0]:.2f} {load[1]:.2f} {load[2]:.2f}"

    now = datetime.now()
    time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%A, %d %B %Y")

    temp_color = "#10b981"
    if temp_c and temp_c > 70:
        temp_color = "#ef4444"
    elif temp_c and temp_c > 55:
        temp_color = "#f59e0b"

    temp_str = f"{temp_c:.1f}°C" if temp_c is not None else "N/A"

    html = f"""
<div class="stat-item">
  <span class="stat-label">🕐 time</span>
  <span class="stat-value">{time_str}</span>
</div>
<div class="stat-item">
  <span class="stat-label">📅 date</span>
  <span class="stat-value">{date_str}</span>
</div>
<div class="stat-item">
  <span class="stat-label">⏱ uptime</span>
  <span class="stat-value">{uptime_str}</span>
</div>
<div class="stat-item">
  <span class="stat-label">🌡 temp</span>
  <span class="stat-value" style="color:{temp_color}">{temp_str}</span>
</div>
<div class="stat-item">
  <span class="stat-label">⚡ cpu</span>
  <span class="stat-value">{cpu:.1f}%</span>
</div>
<div class="stat-item">
  <span class="stat-label">🧠 memory</span>
  <span class="stat-value">{mem.percent:.0f}% <small>({mem_used_mb:.0f}/{mem_total_mb:.0f} MB)</small></span>
</div>
<div class="stat-item">
  <span class="stat-label">📊 load avg</span>
  <span class="stat-value">{load_str}</span>
</div>
"""
    return HTMLResponse(content=html)
