import os
import time
from datetime import datetime
from pathlib import Path

import psutil
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

START_TIME = time.time()


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/stats")
async def stats():
    # CPU temperature
    try:
        temp_raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
        temp_c = int(temp_raw) / 1000.0
    except Exception:
        temp_c = None

    # CPU usage
    cpu = psutil.cpu_percent(interval=0.1)

    # Memory
    mem = psutil.virtual_memory()
    mem_used_mb = mem.used / 1024 / 1024
    mem_total_mb = mem.total / 1024 / 1024
    mem_pct = mem.percent

    # Uptime
    uptime_seconds = int(time.time() - psutil.boot_time())
    days, rem = divmod(uptime_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days > 0:
        uptime_str = f"{days}d {hours}h {minutes}m"
    else:
        uptime_str = f"{hours}h {minutes}m"

    # Load average
    load = os.getloadavg()
    load_str = f"{load[0]:.2f} {load[1]:.2f} {load[2]:.2f}"

    # Current time Amsterdam
    now = datetime.now()
    time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%A, %d %B %Y")

    temp_str = f"{temp_c:.1f}°C" if temp_c is not None else "N/A"

    # Build HTML fragment for htmx
    temp_color = "#10b981"
    if temp_c and temp_c > 70:
        temp_color = "#ef4444"
    elif temp_c and temp_c > 55:
        temp_color = "#f59e0b"

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
  <span class="stat-value">{mem_pct:.0f}% <small>({mem_used_mb:.0f}/{mem_total_mb:.0f} MB)</small></span>
</div>
<div class="stat-item">
  <span class="stat-label">📊 load avg</span>
  <span class="stat-value">{load_str}</span>
</div>
"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)
