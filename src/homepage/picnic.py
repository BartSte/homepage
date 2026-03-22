"""Picnic grocery routes — status, recipes CRUD, meals, staples."""
from __future__ import annotations

import html as _html
import json
import sqlite3
import subprocess
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

router = APIRouter()

_DB = Path.home() / ".openclaw/picnic/staples.db"
_VENV = Path.home() / ".openclaw/picnic/.venv/bin/python"
_TOOLS = Path.home() / ".openclaw/picnic/picnic_tools.py"


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _run_tool(*args: str, timeout: int = 10) -> dict:
    r = subprocess.run([str(_VENV), str(_TOOLS), *args],
                       capture_output=True, text=True, timeout=timeout)
    return json.loads(r.stdout)


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _e(s) -> str:
    """HTML-escape a value."""
    return _html.escape(str(s or ""))


def _recipe_view_card(r: dict) -> str:
    ings = r.get("ingredients", [])
    known = sum(1 for i in ings if i.get("preferred_product_id"))
    total = len(ings)
    pct = int(known / total * 100) if total else 0
    bar_color = "#10b981" if pct == 100 else "#f59e0b" if pct >= 50 else "#ef4444"

    def ing_chip(i: dict) -> str:
        cls = "ing-known" if i.get("preferred_product_id") else "ing-unknown"
        icon = "✓" if i.get("preferred_product_id") else "?"
        product = (f' <span class="ing-product">{_e(i["preferred_product_name"])}</span>'
                   if i.get("preferred_product_name") else "")
        return f'<li class="ing-item {cls}">{icon} {_e(i["ingredient_name"])}{product}</li>'

    chips = "".join(ing_chip(i) for i in ings)
    notes_html = f'<div class="recipe-notes">{_e(r.get("notes") or "")}</div>' if r.get("notes") else ""

    return f"""<div class="recipe-card" id="recipe-{r['id']}">
  <div class="recipe-head">
    <span class="recipe-name">{_e(r['name'])}</span>
    <div style="display:flex;align-items:center;gap:8px">
      <span class="recipe-servings">{_e(r['servings'])}p</span>
      <button class="btn-sm btn-edit"
        hx-get="/api/picnic/recipes/{r['id']}/edit"
        hx-target="#recipe-{r['id']}"
        hx-swap="outerHTML">✏ edit</button>
    </div>
  </div>
  {notes_html}
  <div class="recipe-progress">
    <div class="progress-bar"><div class="progress-fill" style="width:{pct}%;background:{bar_color}"></div></div>
    <span class="progress-label">{known}/{total} producten bekend</span>
  </div>
  <ul class="ing-list">{chips}</ul>
</div>"""


def _ingredient_edit_row(i: dict) -> str:
    pid = _e(i.get("preferred_product_id") or "")
    pname = _e(i.get("preferred_product_name") or "—")
    qty = _e(i.get("quantity") or "")
    unit = _e(i.get("unit") or "")
    qty_unit = f"{qty} {unit}".strip() if qty or unit else "—"
    return f"""<div class="ing-edit-row" id="ing-{i['id']}">
  <span class="ing-edit-name">{_e(i['ingredient_name'])}</span>
  <span class="ing-edit-qty">{qty_unit}</span>
  <span class="ing-edit-product" title="{pid}">{pname}</span>
  <button class="btn-sm btn-danger"
    hx-delete="/api/picnic/ingredients/{i['id']}"
    hx-target="#ing-{i['id']}"
    hx-swap="outerHTML"
    hx-confirm="Ingredient '{_e(i['ingredient_name'])}' verwijderen?">✕</button>
</div>"""


def _recipe_edit_card(r: dict) -> str:
    ings = r.get("ingredients", [])
    ing_rows = "".join(_ingredient_edit_row(i) for i in ings)
    return f"""<div class="recipe-card recipe-editing" id="recipe-{r['id']}">
  <form hx-post="/api/picnic/recipes/{r['id']}"
        hx-target="#recipe-{r['id']}"
        hx-swap="outerHTML">
    <div class="edit-row">
      <input class="edit-field edit-name" name="name"
             value="{_e(r['name'])}" placeholder="Recept naam" required>
      <input class="edit-field edit-cuisine" name="cuisine"
             value="{_e(r.get('cuisine') or '')}" placeholder="Keuken">
      <input class="edit-field edit-servings" name="servings" type="number"
             value="{_e(r['servings'])}" min="1" max="20">
    </div>
    <input class="edit-field edit-notes" name="notes"
           value="{_e(r.get('notes') or '')}" placeholder="Notities (ingredient samenvatting)">
    <div class="edit-actions">
      <button type="submit" class="btn-sm btn-save">💾 opslaan</button>
      <button type="button" class="btn-sm btn-cancel"
        hx-get="/api/picnic/recipes/{r['id']}/view"
        hx-target="#recipe-{r['id']}"
        hx-swap="outerHTML">annuleer</button>
      <button type="button" class="btn-sm btn-danger"
        hx-delete="/api/picnic/recipes/{r['id']}"
        hx-target="#recipe-{r['id']}"
        hx-swap="outerHTML"
        hx-confirm="Recept '{_e(r['name'])}' verwijderen?"
        style="margin-left:auto">🗑 verwijder</button>
    </div>
  </form>

  <div class="ing-edit-section">
    <div class="ing-edit-header">Ingrediënten</div>
    <div id="ing-list-{r['id']}">{ing_rows}</div>
    <form class="ing-add-form"
          hx-post="/api/picnic/recipes/{r['id']}/ingredients"
          hx-target="#ing-list-{r['id']}"
          hx-swap="beforeend"
          hx-on::after-request="this.reset()">
      <input class="edit-field" name="ingredient_name"
             placeholder="Naam" required style="flex:2;min-width:100px">
      <input class="edit-field" name="quantity" type="number"
             step="0.5" min="0" placeholder="qty" style="width:56px">
      <input class="edit-field" name="unit"
             placeholder="eenheid" style="flex:1;min-width:70px">
      <button type="submit" class="btn-sm btn-add">+ add</button>
    </form>
  </div>
</div>"""


def _new_recipe_form() -> str:
    return """<div class="recipe-card recipe-editing" id="recipe-new" style="margin-bottom:16px">
  <div class="recipe-head" style="margin-bottom:12px">
    <span class="recipe-name" style="color:var(--accent)">Nieuw recept</span>
  </div>
  <form hx-post="/api/picnic/recipes"
        hx-target="#recipe-new"
        hx-swap="outerHTML">
    <div class="edit-row">
      <input class="edit-field edit-name" name="name"
             placeholder="Recept naam" required autofocus>
      <input class="edit-field edit-cuisine" name="cuisine"
             placeholder="Keuken (bijv. Italiaans)">
      <input class="edit-field edit-servings" name="servings" type="number"
             value="4" min="1" max="20">
    </div>
    <input class="edit-field edit-notes" name="notes"
           placeholder="Notities">
    <div class="edit-actions">
      <button type="submit" class="btn-sm btn-save">+ aanmaken</button>
      <button type="button" class="btn-sm btn-cancel"
        hx-get="/api/picnic/recipes/new/cancel"
        hx-target="#recipe-new"
        hx-swap="outerHTML">annuleer</button>
    </div>
  </form>
</div>"""


# ── Static page ───────────────────────────────────────────────────────────────

@router.get("/picnic/status-fragment")
async def picnic_status():
    """htmx: order status panel."""
    try:
        data = _run_tool("get_status")
    except Exception as e:
        return HTMLResponse(f'<p style="color:var(--red);font-size:.85rem;">Error: {_e(e)}</p>')

    if not data.get("ok"):
        return HTMLResponse(f'<p style="color:var(--red);font-size:.85rem;">{_e(data.get("error","?"))}</p>')

    from datetime import date
    today = data.get("today", "")
    next_order = data.get("next_order_date")
    last_delivery = data.get("last_delivery_date", "—")
    due_count = len(data.get("staples_due", []))
    total_staples = data.get("total_staples", 0)
    feedback_count = data.get("unapplied_feedback", 0)

    if next_order:
        today_dt = date.fromisoformat(today)
        next_dt = date.fromisoformat(next_order)
        delta = (next_dt - today_dt).days
        if delta < 0:
            schedule_html = f'<span style="color:var(--red)">⚠ {abs(delta)} dagen te laat</span>'
        elif delta == 0:
            schedule_html = '<span style="color:var(--accent)">📦 bestelling vandaag</span>'
        else:
            schedule_html = f'<span style="color:var(--green)">✓ volgende bestelling over {delta} dagen ({next_order})</span>'
    else:
        schedule_html = '<span style="color:var(--muted)">nog niet gepland</span>'

    due_color = "var(--red)" if due_count > 0 else "var(--green)"

    return HTMLResponse(f"""
<div class="picnic-stat"><span class="picnic-label">schema</span><span class="picnic-val">{schedule_html}</span></div>
<div class="picnic-stat"><span class="picnic-label">laatste levering</span><span class="picnic-val">{_e(last_delivery or "—")}</span></div>
<div class="picnic-stat"><span class="picnic-label">staples te bestellen</span><span class="picnic-val" style="color:{due_color}">{due_count} / {total_staples}</span></div>
<div class="picnic-stat"><span class="picnic-label">onverwerkte feedback</span><span class="picnic-val">{feedback_count}</span></div>
""")


@router.get("/api/picnic/status")
async def picnic_status_api():
    return await picnic_status()


# ── Recipes — list ────────────────────────────────────────────────────────────

@router.get("/api/picnic/recipes")
async def picnic_recipes():
    """htmx: full recipe list, grouped by cuisine."""
    from collections import defaultdict

    conn = _db()
    recipes = conn.execute(
        "SELECT * FROM recipes WHERE active=1 ORDER BY cuisine, name"
    ).fetchall()

    if not recipes:
        conn.close()
        return HTMLResponse('<p style="color:var(--muted);font-size:.85rem;">Nog geen recepten.</p>')

    by_cuisine: dict[str, list] = defaultdict(list)
    for row in recipes:
        r = dict(row)
        ings = conn.execute(
            "SELECT * FROM recipe_ingredients WHERE recipe_id=? ORDER BY id", (r["id"],)
        ).fetchall()
        r["ingredients"] = [dict(i) for i in ings]
        by_cuisine[r.get("cuisine") or "Overig"].append(r)
    conn.close()

    html = ""
    for cuisine, rlist in sorted(by_cuisine.items()):
        html += f'<div class="cuisine-group"><h3 class="cuisine-title">{_e(cuisine)}</h3>'
        for r in rlist:
            html += _recipe_view_card(r)
        html += "</div>"
    return HTMLResponse(html)


# ── Recipes — view/edit single card ──────────────────────────────────────────

@router.get("/api/picnic/recipes/new/cancel")
async def picnic_recipe_new_cancel():
    """Cancel new recipe form — returns empty to remove the slot."""
    return HTMLResponse("")


@router.get("/api/picnic/recipes/new")
async def picnic_recipe_new():
    return HTMLResponse(_new_recipe_form())


@router.get("/api/picnic/recipes/{recipe_id}/view")
async def picnic_recipe_view(recipe_id: int):
    conn = _db()
    row = conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    if not row:
        conn.close()
        return HTMLResponse("")
    r = dict(row)
    r["ingredients"] = [dict(i) for i in conn.execute(
        "SELECT * FROM recipe_ingredients WHERE recipe_id=? ORDER BY id", (recipe_id,)
    ).fetchall()]
    conn.close()
    return HTMLResponse(_recipe_view_card(r))


@router.get("/api/picnic/recipes/{recipe_id}/edit")
async def picnic_recipe_edit_form(recipe_id: int):
    conn = _db()
    row = conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    if not row:
        conn.close()
        return HTMLResponse('<p style="color:var(--red)">Recept niet gevonden.</p>')
    r = dict(row)
    r["ingredients"] = [dict(i) for i in conn.execute(
        "SELECT * FROM recipe_ingredients WHERE recipe_id=? ORDER BY id", (recipe_id,)
    ).fetchall()]
    conn.close()
    return HTMLResponse(_recipe_edit_card(r))


# ── Recipes — create / update / delete ───────────────────────────────────────

@router.post("/api/picnic/recipes")
async def picnic_recipe_create(
    name: str = Form(...),
    cuisine: str = Form(""),
    servings: int = Form(4),
    notes: str = Form(""),
):
    conn = _db()
    cur = conn.execute(
        "INSERT INTO recipes (name, cuisine, servings, notes, active) VALUES (?,?,?,?,1)",
        (name.strip(), cuisine.strip() or None, servings, notes.strip() or None),
    )
    recipe_id = cur.lastrowid
    conn.commit()
    r = dict(conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone())
    r["ingredients"] = []
    conn.close()
    # Return in edit mode so user can immediately add ingredients
    resp = HTMLResponse(_recipe_edit_card(r))
    resp.headers["HX-Trigger"] = "recipesUpdated"
    return resp


@router.post("/api/picnic/recipes/{recipe_id}")
async def picnic_recipe_update(
    recipe_id: int,
    name: str = Form(...),
    cuisine: str = Form(""),
    servings: int = Form(4),
    notes: str = Form(""),
):
    conn = _db()
    conn.execute(
        "UPDATE recipes SET name=?, cuisine=?, servings=?, notes=? WHERE id=?",
        (name.strip(), cuisine.strip() or None, servings, notes.strip() or None, recipe_id),
    )
    conn.commit()
    r = dict(conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone())
    r["ingredients"] = [dict(i) for i in conn.execute(
        "SELECT * FROM recipe_ingredients WHERE recipe_id=? ORDER BY id", (recipe_id,)
    ).fetchall()]
    conn.close()
    return HTMLResponse(_recipe_view_card(r))


@router.delete("/api/picnic/recipes/{recipe_id}")
async def picnic_recipe_delete(recipe_id: int):
    conn = _db()
    conn.execute("UPDATE recipes SET active=0 WHERE id=?", (recipe_id,))
    conn.commit()
    conn.close()
    resp = HTMLResponse("")
    resp.headers["HX-Trigger"] = "recipesUpdated"
    return resp


# ── Ingredients ───────────────────────────────────────────────────────────────

@router.post("/api/picnic/recipes/{recipe_id}/ingredients")
async def picnic_ingredient_add(
    recipe_id: int,
    ingredient_name: str = Form(...),
    quantity: str = Form(""),
    unit: str = Form(""),
):
    conn = _db()
    qty = float(quantity) if quantity.strip() else None
    cur = conn.execute(
        "INSERT INTO recipe_ingredients (recipe_id, ingredient_name, quantity, unit) VALUES (?,?,?,?)",
        (recipe_id, ingredient_name.strip(), qty, unit.strip() or None),
    )
    ing_id = cur.lastrowid
    conn.commit()
    i = dict(conn.execute("SELECT * FROM recipe_ingredients WHERE id=?", (ing_id,)).fetchone())
    conn.close()
    return HTMLResponse(_ingredient_edit_row(i))


@router.delete("/api/picnic/ingredients/{ing_id}")
async def picnic_ingredient_delete(ing_id: int):
    conn = _db()
    conn.execute("DELETE FROM recipe_ingredients WHERE id=?", (ing_id,))
    conn.commit()
    conn.close()
    return HTMLResponse("")


# ── Meals history ─────────────────────────────────────────────────────────────

@router.get("/api/picnic/meals")
async def picnic_meals():
    from collections import defaultdict
    try:
        data = _run_tool("get_meal_history", "8")
    except Exception as e:
        return HTMLResponse(f'<p style="color:var(--red);font-size:.85rem;">Error: {_e(e)}</p>')

    meals = data.get("meals", [])
    if not meals:
        return HTMLResponse('<p style="color:var(--muted);font-size:.85rem;">Nog geen maaltijdgeschiedenis.</p>')

    by_date: dict = defaultdict(list)
    for m in meals:
        by_date[m["order_date"]].append(m)

    html_parts = []
    for d, items in sorted(by_date.items(), reverse=True):
        html_parts.append(f'<div class="meal-week"><span class="meal-date">{_e(d)}</span>')
        for m in items:
            cuisine = f' <span class="meal-cuisine">{_e(m["cuisine"])}</span>' if m.get("cuisine") else ""
            html_parts.append(f'<div class="meal-row">🍽 {_e(m["name"])}{cuisine}</div>')
        html_parts.append("</div>")
    return HTMLResponse("".join(html_parts))


# ── Staples ───────────────────────────────────────────────────────────────────

@router.get("/api/picnic/staples")
async def picnic_staples():
    try:
        data = _run_tool("staple_list")
    except Exception as e:
        return HTMLResponse(f'<p style="color:var(--red);font-size:.85rem;">Error: {_e(e)}</p>')

    staples = data.get("staples", [])
    if not staples:
        return HTMLResponse('<p style="color:var(--muted);font-size:.85rem;">Geen staples bijgehouden.</p>')

    rows = ""
    for s in staples:
        badge = ('<span class="badge badge-due">due</span>' if s.get("is_due")
                 else '<span class="badge badge-ok">ok</span>')
        rows += f"""<tr>
  <td>{_e(s['name'])}</td>
  <td>{badge}</td>
  <td style="font-family:var(--mono);font-size:.8rem;color:var(--muted)">{_e(s.get('last_ordered_date') or '—')}</td>
  <td style="font-family:var(--mono);font-size:.8rem;color:var(--muted)">{_e(s.get('next_due') or '—')}</td>
  <td style="font-family:var(--mono);font-size:.8rem;color:var(--muted)">{_e(s.get('reorder_interval_days', '?'))}d</td>
</tr>"""

    return HTMLResponse(f"""<table class="staples-table">
  <thead><tr>
    <th>item</th><th>status</th><th>laatste bestelling</th><th>volgende</th><th>interval</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>""")
