# Troubleshooting

## Quick Diagnostic Checklist

Run these before investigating further:

```bash
# 1. Ollama running?
curl http://localhost:11434/api/tags

# 2. Required model available?
ollama list | grep -E "qwen-data|qwen2.5-coder"

# 3. Can connect to PostgreSQL?
psql <your-connection-string> -c "\dt" | head -5

# 4. Schemalytics installed?
pip show schemalytics | grep Version
```

---

## Connection Issues

### `Connection refused` on Ollama

**Symptom:**
```
httpx.ConnectError: [Errno 61] Connection refused
```

**Cause:** Ollama is not running.

**Fix:**
```bash
ollama serve
# or on macOS, start Ollama from the menu bar app
```

---

### `model not found` error

**Symptom:**
```
Error: model 'qwen-data:latest' not found
```

**Fix:**
```bash
ollama pull qwen2.5-coder:7b
# or
ollama pull qwen-data:latest
```

---

### `could not connect to server` (PostgreSQL)

**Symptom:**
```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Causes and fixes:**

| Cause | Fix |
|-------|-----|
| Wrong host or port | Check connection string: `postgresql://user:pass@HOST:PORT/db` |
| Database not running | Start PostgreSQL |
| Wrong credentials | Verify username and password |
| Firewall blocking port | Check network access to port 5432 |
| SSL required | Add `?sslmode=require` to connection string |

---

## Schema Extraction Issues

### No tables found

**Symptom:** Schema extracts 0 tables.

**Causes:**
- Connected to wrong database or schema
- User lacks `SELECT` privilege on `information_schema`

**Fix:**
```bash
# Verify you can see tables manually
psql <connection-string> -c "\dt public.*"

# Grant schema access if needed (as superuser)
GRANT USAGE ON SCHEMA public TO your_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO your_user;
```

---

### Foreign keys missing from classification

**Symptom:** All tables classified as `dimension`, no facts detected.

**Cause:** Foreign keys are enforced at the application level (not in the database), so SQLAlchemy can't detect them.

**Fix:** During the refinement loop, give feedback to reclassify:
```
"orders is a fact table, not a dimension"
"treat orders, order_items, and transactions as fact tables"
```

---

## LLM / Planning Issues

### LLM returns empty plan

**Symptom:** Generation stalls or returns `{}`.

**Causes:**
- Schema is very large (many tables/columns) and the prompt exceeds model context
- Model timeout on slow hardware

**Fixes:**
- Use `schemalytics extract` first to review the schema, then target specific schemas
- Increase the httpx timeout in `schemalytics/llm.py` (default: 120s)
- Use a model with larger context: `ollama pull qwen2.5-coder:14b`

---

### JSON parse error from LLM

**Symptom:**
```
json.JSONDecodeError: Expecting value
```

**Cause:** The LLM returned prose or markdown instead of valid JSON.

**What Schemalytics does:** A regex fallback tries to extract the first valid JSON object from the response.

**If fallback also fails:**
- Retry — LLM outputs are non-deterministic, a second attempt usually works
- Try a different model: `ollama pull mistral:7b`

---

### Plan not changing after feedback

**Symptom:**
```
⚠️  Warning: No changes detected in plan after feedback
```

**Causes:**
- Feedback was too vague
- The LLM interpreted the feedback as a no-op

**Fix:** Be more specific:
```
# Vague
"make it better"

# Specific
"change agg_daily_revenue to weekly grain and rename it agg_weekly_revenue"
```

---

## Generation Issues

### Empty `gold/` folder

**Symptom:** dbt project generated but `models/gold/` is empty.

**Cause:** No fact tables were classified, so no gold aggregates could be created.

**Fix:** In the refinement loop, explicitly identify fact tables:
```
"orders is a fact table"
"treat order_items as a fact with measures quantity and unit_price"
```

---

### SQL syntax errors in generated models

**Symptom:** `dbt run` fails with SQL syntax errors.

**Cause:** Template rendering issue, usually from special characters in column names.

**Fix:** Check column names in the source table for special characters or reserved words. If found, raise an issue on GitHub with the column names.

---

### `dbt_utils not installed` error

**Symptom:**
```
Compilation error: No macro named 'surrogate_key' in package 'dbt_utils'
```

**Fix:** Add dbt-utils to `packages.yml` in the generated project:

```yaml
# packages.yml
packages:
  - package: dbt-labs/dbt_utils
    version: [">=1.0.0", "<2.0.0"]
```

Then run:
```bash
dbt deps
```

---

## Performance Issues

### Slow LLM response

Large schemas (50+ tables) with many columns can make prompts slow.

**Options:**
1. Filter to specific schemas: use `extract` first, inspect, then generate
2. Use a faster/smaller model: `ollama pull qwen2.5:3b`
3. Run Ollama with GPU acceleration (check `ollama ps` for GPU usage)

---

## Getting Help

If none of the above resolves your issue:

1. Run `schemalytics extract -c <conn> -o schema.json` and inspect the output
2. Check the Ollama logs: `journalctl -u ollama` (Linux) or Console.app (macOS)
3. Open an issue at https://github.com/NiChr0/schemalytics/issues with:
   - Schemalytics version (`pip show schemalytics`)
   - Ollama version (`ollama --version`)
   - Number of tables in your database
   - Error message and stack trace
