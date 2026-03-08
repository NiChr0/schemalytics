# Contributing

## Development Setup

```bash
git clone https://github.com/NiChr0/schemalytics.git
cd schemalytics
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**Prerequisites:**
- Ollama running with `gemma3-data` pulled
- Docker (for the Northwind test database)

```bash
# Pull the required Ollama model
ollama pull gemma3-data

# Start the test database
docker run -d \
  -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  ghcr.io/nichr0/northwind-postgres:latest
```

---

## Code Style

Schemalytics uses `ruff` for linting. Run before every commit:

```bash
ruff check schemalytics/
ruff check schemalytics/ --fix   # auto-fix most issues
```

Zero errors required before any PR or release.

---

## Key Design Rules

Read these before writing any code:

1. **Jinja2 for SQL, not LLM output.** All SQL generation goes through the Jinja2 templates in `templates.py`. The LLM never writes raw SQL.

2. **No dbt execution.** Schemalytics generates dbt project files only. Users run `dbt run` themselves. Do not add `dbt` as a runtime dependency or execute it.

3. **`instructor` for all LLM output.** Every agent call returns a validated Pydantic model via `llm.query_structured()`. No `json.loads()` anywhere in the pipeline.

4. **Pydantic v2 for all data structures.** Any new data model must be a `pydantic.BaseModel` subclass in `models.py`.

5. **Pipeline contract.** Silver is sanitized before Gold sees it (`_sanitize_plan()` runs between Agent 4a and 4b). Never pass raw LLM output downstream without validation.

6. **Token budgets matter.** Ollama uses `num_ctx=12288`. Always size `max_tokens` per agent call to fit within the window. Use dynamic budgets (see existing agents) rather than hardcoded large values.

---

## Project Structure

```
schemalytics/
├── cli.py                  # Click CLI — add new commands here
├── models.py               # Pydantic models — all data structures here
├── llm.py                  # LLM provider abstraction (Ollama / Anthropic)
├── planner.py              # 5-agent pipeline, sanitization, refinement loop
├── templates.py            # Jinja2 SQL templates
├── extractors/
│   └── postgres.py         # Schema extraction
└── generators/
    └── dbt.py              # dbt file generation
```

---

## How to Add a Feature

### New pipeline step

1. Define input/output Pydantic models in `models.py`
2. Implement logic in the appropriate module:
   - LLM / classification logic → `planner.py`
   - File output → `generators/dbt.py`
3. Wire into `run_pipeline()` in `planner.py` in the correct pipeline order
4. Update `AGENTS.md` if the architecture or CLI changes

### New CLI command

1. Add a `@click.command()` function in `cli.py`
2. Register it with `cli.add_command()`
3. Update `AGENTS.md` CLI Commands table and this wiki

### New Jinja2 SQL template

Add as a string constant in `templates.py`, near the top with the other templates:

```python
MY_NEW_TEMPLATE = """
-- {{ model_name }}
{{ config(materialized='table') }}

select ...
from {{ ref('source_model') }}
"""
```

Then render in `generators/dbt.py`:

```python
from schemalytics.templates import MY_NEW_TEMPLATE
from jinja2 import Template

sql = Template(MY_NEW_TEMPLATE).render(model_name="my_model")
```

---

## Testing

See [testing.md](../../testing.md) for the full test workflow. In summary:

```bash
# Level 1 — unit tests (no external deps)
pytest tests/test_agents.py -v

# Level 2 — integration (requires Ollama + Northwind)
SCHEMALYTICS_INTEGRATION=1 pytest tests/test_integration.py -v

# Level 3 — end-to-end
schemalytics generate \
  -c postgresql://postgres:mypassword@localhost:5432/northwind \
  -o /tmp/e2e_test
```

---

## Making an LLM Call

All agent calls use `llm.query_structured()`:

```python
from schemalytics import llm
from schemalytics.models import MyOutputModel

result = llm.query_structured(
    system="You are a data engineer...",
    user=f"Schema:\n{schema_summary}",
    response_model=MyOutputModel,
    max_tokens=1024,   # size appropriately for expected output
)
# result is a validated MyOutputModel — no JSON parsing needed
```

**Returning a list** — `instructor` cannot return `list[T]` directly; wrap in a container:

```python
from pydantic import BaseModel

class _ResultList(BaseModel):
    items: list[MyItemModel]

result = llm.query_structured(system=..., user=..., response_model=_ResultList)
return result.items
```

---

## Release Process

See [release.md](../../release.md) for the full release workflow. In summary:

1. Run `ruff check schemalytics/` — zero errors
2. Run end-to-end test against Northwind
3. Bump `version` in `pyproject.toml` and `schemalytics/__init__.py`
4. `python -m build`
5. `twine check dist/* && twine upload dist/*`
6. `git tag vX.Y.Z && git push origin vX.Y.Z`

Versioning: `MAJOR.MINOR.PATCH`
- PATCH — bug fixes
- MINOR — new features, backward compatible
- MAJOR — breaking CLI or output structure changes
