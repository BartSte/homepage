import os
import time
from datetime import datetime
from pathlib import Path

import psutil
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from homepage import github, parser

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
