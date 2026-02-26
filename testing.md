# Agent: Testing & Validation

> Load this file when the task involves running tests, validating output, or debugging a pipeline failure.
> Always read `AGENTS.md` first for full repo context.

---

## Prerequisites Check

Before running any tests, verify:

```bash
# 1. Ollama is running
curl http://localhost:11434/api/tags | python -m json.tool

# 2. Required model is available
ollama list | grep -E "qwen-data|qwen2.5-coder"

# 3. Northwind test DB is up
psql postgresql://postgres:postgres@localhost:5432/northwind -c "\dt" | head -5

# 4. Package installed in editable mode
pip show schemalytics | grep -E "Version|Location"
```

If Ollama model is missing: `ollama pull qwen2.5-coder:7b`
If Northwind DB is missing: `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres ghcr.io/nichr0/northwind-postgres:latest`

---

## Test Levels

### Level 1 — Unit (fast, no external deps)

```bash
pip install pytest pytest-cov
pytest tests/ -v --tb=short
```

Focus areas to cover:
- `classify_by_fk_graph()` — given a mock Schema, assert correct fact/dimension classification
- `models.py` — Pydantic validation edge cases (missing fields, wrong types)
- Template rendering in `generators/dbt.py` — assert SQL output matches expected structure

### Level 2 — Integration (requires Ollama)

Test each pipeline step in isolation:

```bash
# Schema extraction
python -c "
from schemalytics.extractors.postgres import extract_schema
schema = extract_schema('postgresql://postgres:postgres@localhost:5432/northwind')
print(f'Tables: {len(schema.tables)}')
assert len(schema.tables) > 0, 'No tables extracted'
print('✅ Schema extraction OK')
"

# FK graph classification
python -c "
from schemalytics.extractors.postgres import extract_schema
from schemalytics.planner import classify_by_fk_graph
schema = extract_schema('postgresql://postgres:postgres@localhost:5432/northwind')
classifications = classify_by_fk_graph(schema)
print({c.table_name: c.role for c in classifications})
print('✅ FK classification OK')
"
```

### Level 3 — End-to-End (full pipeline)

```bash
# Clean output dir
rm -rf /tmp/e2e_test

# Run full pipeline (non-interactive via context file)
cat > /tmp/context.yaml << EOF
business_type: ecommerce
industry: Retail & E-commerce
entities: [customers, orders, products]
goals: [revenue tracking, order analysis]
temporal: historical_tracking
grain: transaction_level
EOF

schemalytics generate \
  -c postgresql://postgres:postgres@localhost:5432/northwind \
  -o /tmp/e2e_test \
  -n northwind_test \
  -x /tmp/context.yaml
```

---

## Output Validation

After generation, validate the output structure:

```bash
# Check all required files exist
python -c "
from pathlib import Path
base = Path('/tmp/e2e_test')
required = [
    'dbt_project.yml',
    'models/bronze',
    'models/silver/dimensions',
    'models/silver/facts',
    'models/gold',
    'semantic_layer.yml',
    'README.md',
]
for r in required:
    p = base / r
    assert p.exists(), f'MISSING: {r}'
    print(f'✅ {r}')
"

# Check SQL files are non-empty and contain expected patterns
python -c "
from pathlib import Path
sql_files = list(Path('/tmp/e2e_test/models').rglob('*.sql'))
print(f'Total SQL files: {len(sql_files)}')
for f in sql_files:
    content = f.read_text()
    assert 'select' in content.lower(), f'No SELECT in {f.name}'
    assert '{{' in content, f'No Jinja2 in {f.name}'
print('✅ All SQL files valid')
"
```

---

## Debugging Common Failures

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Connection refused` on Ollama | Ollama not running | `ollama serve` |
| `model not found` | Model not pulled | `ollama pull qwen2.5-coder:7b` |
| LLM returns empty plan | Prompt too long or model timeout | Reduce schema size or increase `timeout` in httpx call |
| JSON parse error from LLM | Model returned markdown/prose | Check `parse_llm_json()` regex fallback |
| Missing FK edges in classification | SQLAlchemy didn't pick up FKs | Check if FKs are defined at DB level vs app level only |
| Empty `gold/` folder | No fact tables classified | Review FK graph output; manually reclassify if needed |

---

## Regression Checklist

Run this before any PR or release:

- [ ] `ruff check schemalytics/` — zero errors
- [ ] Level 1 unit tests pass
- [ ] Level 3 e2e against Northwind produces valid output
- [ ] `dbt parse` succeeds in the generated project (optional but ideal)
- [ ] `semantic_layer.yml` is valid YAML and non-empty