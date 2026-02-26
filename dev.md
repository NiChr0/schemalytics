# Agent: Feature Development

> Load this file when the task involves adding a feature, fixing a bug, or refactoring code.
> Always read `AGENTS.md` first for full repo context.

---

## Ground Rules

- Never add cloud LLM API calls. All LLM calls go through Ollama on localhost.
- Never add dbt execution logic. Schemalytics generates files only.
- SQL generation must use Jinja2 templates in `generators/dbt.py`, not raw LLM output.
- All new data structures must be Pydantic v2 models in `models.py`.
- Match existing code style: type hints everywhere, docstrings on public functions.

---

## Workflow

### 1. Understand the change

Before writing any code:
- Identify which module owns the change (`cli.py`, `planner.py`, `extractors/`, `generators/`)
- Check `models.py` — does a new Pydantic model need to be added or modified?
- If the change affects the CLI, update `cli.py` click commands accordingly

### 2. Implement

**Adding a new pipeline step:**
1. Define input/output Pydantic models in `models.py`
2. Implement logic in the appropriate module (`planner.py` for LLM/classification logic, `generators/dbt.py` for file output)
3. Wire into `cli.py` in the correct pipeline order
4. If adding a Jinja2 template, add it near the top of `generators/dbt.py` as a string constant or in a `templates/` module if it grows large

**Adding a new CLI command:**
1. Add `@click.command()` function in `cli.py`
2. Register it with `cli.add_command()`
3. Update `CLAUDE.md` CLI Commands table

**Modifying LLM prompts:**
- Prompts live in `planner.py` as inline strings
- Always include JSON output format instructions in the prompt
- Always add a fallback if the LLM returns malformed JSON (catch `json.JSONDecodeError`)

### 3. Validate before finishing

Run these checks in order:

```bash
# Lint
ruff check schemalytics/

# Type check (if mypy is available)
mypy schemalytics/ --ignore-missing-imports

# Functional smoke test
schemalytics generate \
  -c postgresql://postgres:postgres@localhost:5432/northwind \
  -o /tmp/test_output \
  --name smoke_test
```

Verify the output directory contains:
- `dbt_project.yml`
- `models/bronze/`, `models/silver/dimensions/`, `models/silver/facts/`, `models/gold/`
- `semantic_layer.yml`
- `README.md`

### 4. Update docs

- If the change affects CLI flags: update `CLAUDE.md` and `README.md`
- If the change affects the pipeline flow: update the architecture diagram in `CLAUDE.md`
- If a new Pydantic model was added: add a short description comment to the class

---

## Common Patterns

**Making an Ollama LLM call:**
```python
import httpx, json

def call_ollama(prompt: str, model: str = "qwen-data:latest") -> str:
    response = httpx.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()["response"]
```

**Safe JSON parsing from LLM output:**
```python
import re, json

def parse_llm_json(raw: str) -> dict:
    # Strip markdown code fences if present
    clean = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        # Extract first JSON object found
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise
```

**Adding a Jinja2 SQL template:**
```python
from jinja2 import Template

BRONZE_TEMPLATE = """
-- Bronze: {{ table_name }}
{{ config(materialized='view') }}

select * from {{ source('raw', '{{ table_name }}') }}
"""

sql = Template(BRONZE_TEMPLATE).render(table_name="orders")
```