# Contributing

## Development Setup

```bash
git clone https://github.com/NiChr0/schemalytics.git
cd schemalytics
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**Prerequisites:**
- Ollama running with `qwen2.5-coder:7b` pulled
- Docker (for the Northwind test database)

```bash
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

1. **No cloud LLM calls.** All LLM calls go through Ollama on `localhost:11434`. Never add OpenAI, Anthropic, or any cloud API as a dependency.

2. **No dbt execution.** Schemalytics generates dbt project files only. Users run `dbt run` themselves. Do not add `dbt` as a runtime dependency or execute it.

3. **Jinja2 for SQL, not LLM output.** All SQL generation goes through the Jinja2 templates in `templates.py`. The LLM never writes raw SQL.

4. **Pydantic v2 for all data structures.** Any new data model must be a `pydantic.BaseModel` subclass in `models.py`.

5. **Type hints everywhere, docstrings on public functions.**

---

## Project Structure

```
schemalytics/
├── cli.py                  # Click CLI — add new commands here
├── models.py               # Pydantic models — all data structures here
├── llm.py                  # Ollama HTTP client
├── planner.py              # LLM planning and refinement loop
├── templates.py            # Jinja2 SQL templates
├── industry_taxonomy.py    # Industry presets
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
3. Wire into `cli.py` in the correct pipeline order
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

### New industry preset

Add to `industry_taxonomy.py`:

```python
"My Industry": {
    "sub_type_name": {
        "entities": ["entity1", "entity2"],
        "goals": ["goal 1", "goal 2"],
        "metrics": ["metric1", "metric2"],
    }
}
```

---

## Testing

See [testing.md](../../testing.md) for the full test workflow. In summary:

```bash
# Level 1 — unit tests (no external deps)
pytest tests/ -v

# Level 2 — integration (requires Ollama)
python -c "
from schemalytics.extractors.postgres import extract_schema
schema = extract_schema('postgresql://postgres:postgres@localhost:5432/northwind')
print(f'Tables: {len(schema.tables)}')
"

# Level 3 — end-to-end
schemalytics generate \
  -c postgresql://postgres:postgres@localhost:5432/northwind \
  -o /tmp/e2e_test \
  -x /tmp/context.yaml
```

---

## Making an LLM Call

Use the `llm` module:

```python
from schemalytics import llm

# Plain text response
response = llm.query("What is 2+2?")

# JSON response (auto-parses)
data = llm.query_json("Return a JSON object with key 'result' and value 42")
```

For inline LLM calls (e.g., in a new planner function):

```python
import httpx, json, re

def call_ollama(prompt: str, model: str = "qwen-data:latest") -> str:
    response = httpx.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()["response"]

def parse_llm_json(raw: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise
```

---

## Release Process

See [release.md](../../release.md) for the full release workflow. In summary:

1. Run `ruff check schemalytics/` — zero errors
2. Run end-to-end test against Northwind
3. Bump `version` in `pyproject.toml`
4. `python -m build`
5. `twine check dist/* && twine upload dist/*`
6. `git tag vX.Y.Z && git push origin vX.Y.Z`

Versioning: `MAJOR.MINOR.PATCH`
- PATCH — bug fixes
- MINOR — new features, backward compatible
- MAJOR — breaking CLI or output structure changes
