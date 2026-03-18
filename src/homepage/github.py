"""GitHub data fetcher with a simple TTL cache."""

import json
import subprocess
import time

_cache: dict = {}
CACHE_TTL = 300  # 5 minutes


def _cached(key: str, fetch_fn):
    now = time.time()
    if key in _cache and now - _cache[key]["ts"] < CACHE_TTL:
        return _cache[key]["data"]
    data = fetch_fn()
    _cache[key] = {"ts": now, "data": data}
    return data


def _gh(*args: str) -> list | dict:
    try:
        r = subprocess.run(
            ["gh", "api", *args],
            capture_output=True, text=True, timeout=12
        )
        if r.returncode != 0:
            return []
        return json.loads(r.stdout)
    except Exception:
        return []


def _gh_graphql(query: str) -> dict:
    try:
        r = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={query}"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode != 0:
            return {}
        return json.loads(r.stdout)
    except Exception:
        return {}


def _time_ago(iso: str) -> str:
    """Convert ISO timestamp to 'X ago' string."""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = int((now - dt).total_seconds())
        if diff < 60:
            return "just now"
        elif diff < 3600:
            return f"{diff // 60}m ago"
        elif diff < 86400:
            return f"{diff // 3600}h ago"
        elif diff < 86400 * 7:
            return f"{diff // 86400}d ago"
        elif diff < 86400 * 30:
            return f"{diff // (86400 * 7)}w ago"
        elif diff < 86400 * 365:
            return f"{diff // (86400 * 30)}mo ago"
        else:
            return f"{diff // (86400 * 365)}y ago"
    except Exception:
        return iso[:10]


LANG_COLORS = {
    "Python": "#3572A5",
    "Lua": "#000080",
    "Shell": "#89e051",
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "Rust": "#dea584",
    "Go": "#00ADD8",
    "C": "#555555",
    "C++": "#f34b7d",
    "Vim Script": "#199f4b",
    "Nix": "#7e7eff",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
}


def get_repos() -> list[dict]:
    def fetch():
        data = _gh("users/BartSte/repos?sort=pushed&per_page=15&type=owner")
        if not isinstance(data, list):
            return []
        out = []
        for r in data:
            lang = r.get("language") or ""
            out.append({
                "name": r["name"],
                "url": r["html_url"],
                "description": r.get("description") or "",
                "language": lang,
                "lang_color": LANG_COLORS.get(lang, "#64748b"),
                "pushed": r.get("pushed_at", ""),
                "pushed_ago": _time_ago(r.get("pushed_at", "")),
                "stars": r.get("stargazers_count", 0),
                "fork": r.get("fork", False),
            })
        return out

    return _cached("repos", fetch)


def get_open_prs() -> list[dict]:
    def fetch():
        q = '{ search(query:"author:BartSte is:pr is:open", type:ISSUE, first:20) { nodes { ... on PullRequest { title url createdAt updatedAt isDraft repository { nameWithOwner } } } } }'
        data = _gh_graphql(q)
        nodes = data.get("data", {}).get("search", {}).get("nodes", [])
        return [
            {
                "title": n["title"],
                "url": n["url"],
                "repo": n["repository"]["nameWithOwner"],
                "repo_short": n["repository"]["nameWithOwner"].split("/")[-1],
                "created": n["createdAt"][:10],
                "updated_ago": _time_ago(n["updatedAt"]),
                "draft": n.get("isDraft", False),
            }
            for n in nodes
        ]

    return _cached("open_prs", fetch)


def get_recent_commits() -> list[dict]:
    """Pull recent commits from the top 5 most-active repos."""
    def fetch():
        repos = get_repos()[:6]
        all_commits = []
        for repo in repos:
            name = repo["name"]
            data = _gh(f"repos/BartSte/{name}/commits?per_page=3")
            if not isinstance(data, list):
                continue
            for c in data:
                msg = c.get("commit", {}).get("message", "").split("\n")[0]
                date = c.get("commit", {}).get("committer", {}).get("date", "")
                all_commits.append({
                    "repo": name,
                    "repo_url": f"https://github.com/BartSte/{name}",
                    "message": msg,
                    "date": date[:10],
                    "date_ago": _time_ago(date),
                    "sha": c.get("sha", "")[:7],
                    "url": c.get("html_url", ""),
                })
        all_commits.sort(key=lambda x: x["date"], reverse=True)
        return all_commits[:15]

    return _cached("commits", fetch)
