# homepage

A personal homepage built with [FastAPI](https://fastapi.tiangolo.com/), [Jinja2](https://jinja.palletsprojects.com/) templates, and [htmx](https://htmx.org/).

## Stack

- **FastAPI** — Python web framework
- **Jinja2** — server-side HTML templating
- **htmx** — dynamic frontend without writing JavaScript
- **Uvicorn** — ASGI server
- **uv** — dependency management

## Getting started

```bash
uv sync
uv run uvicorn homepage.main:app --reload
```

Then open [http://localhost:8000](http://localhost:8000).

## Project structure

```
src/homepage/
├── main.py          # FastAPI app and routes
└── templates/       # Jinja2 HTML templates
    └── index.html
tests/               # Test suite (pytest)
docs/                # Documentation
```

## Running tests

```bash
uv run pytest
```
