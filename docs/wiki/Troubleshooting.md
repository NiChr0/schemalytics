# Troubleshooting

## Quick Diagnostic Checklist

Run these before investigating further:

```bash
# 1. Ollama running?
curl http://localhost:11434/api/tags

# 2. Required models available?
ollama list | grep -E "gemma3|schemalytics"

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
Error: model 'gemma3:4b' not found
```

**Fix:**
```bash
ollama pull gemma3:4b
# Also pull the fine-tuned models if missing (used by Agents 3, 4a, 4b):
ollama pull nichr0/schemalytics-classification-agent
ollama pull nichr0/schemalytics-silver-agent
ollama pull nichr0/schemalytics-gold-agent
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

**Fix:** At the Summary Gate, type a correction:
```
"orders is a fact table, not a dimension"
"treat orders, order_items, and transactions as fact tables"
```

---

## LLM / Planning Issues

### Agent 4 takes a very long time (tens of minutes)

**Symptom:** Agent 4a or 4b stalls for 10+ minutes, possibly repeating.

**Cause:** The combined `prompt_tokens + max_tokens` exceeded Ollama's `num_ctx=12288`. Ollama silently truncates the JSON response, `instructor` retries 3×, and each retry takes several minutes.

**What to look for:**
```
[Agent 4a] tables=70  dims=12  facts=8  max_tokens=3256
```
If `max_tokens` is high (3000+) and you have many tables, the prompt may be too large.

**Fixes:**
- This is usually self-correcting — the dynamic `max_tokens` sizing accounts for schema size. If it happens consistently, open a GitHub issue.
- Use a model with a larger context window via Anthropic: `SCHEMALYTICS_LLM_PROVIDER=anthropic`

---

### `instructor` validation errors / instructor retries

**Symptom:** You see repeated "Retrying..." messages and Agent calls take very long.

**Cause:** The LLM is not producing valid JSON that matches the expected Pydantic model. `instructor` retries up to 3 times.

**Fixes:**
- Usually resolves after 1-2 retries
- If persistent, switch providers: `SCHEMALYTICS_LLM_PROVIDER=anthropic`
- Try a different Ollama model: `ollama pull qwen2.5-coder:7b`

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

**Fix:** At the Summary Gate or in the refinement loop, identify fact tables explicitly:
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

**Fix:** Run `dbt deps` in the generated project — `packages.yml` already declares the dependency:

```bash
cd your_dbt_project
dbt deps
dbt run
```

---

### Measures look wrong (non-numeric columns included)

**Symptom:** Generated fact models include columns like `status_code` or `type_flag` as measures.

**Cause:** The LLM occasionally picks non-numeric columns. The sanitizer (`_col_is_measure`) filters these out using type + name heuristics, but edge cases exist.

**Fix:** Use the refinement loop:
```
"remove status_code from fct_orders measures — it's not a metric"
"the only real measures on fct_orders are freight and discount"
```

---

### Gold model references a column that doesn't exist

**Symptom:** `dbt run` fails because a Gold model references a column not in the Silver fact.

**Cause:** Gold LLM output referenced a computed value (e.g. `qty * price`) instead of a declared derived measure alias.

**What the sanitizer does:** Expressions in Gold `column` fields are rejected automatically. Gold can only reference bare column names and named derived measures declared in Silver.

**Fix:** Use the refinement loop to add the derived measure explicitly:
```
"add line_total = quantity * unit_price as a derived measure on fct_order_details"
```

---

## Performance Issues

### Slow LLM response

Large schemas (50+ tables) can make Agent 3 and Agent 4 slow.

**Options:**
1. Use `schemalytics extract` first to inspect the schema, then target specific schemas
2. Use Anthropic (much faster than local Ollama for large schemas): `SCHEMALYTICS_LLM_PROVIDER=anthropic`
3. Run Ollama with GPU acceleration (check `ollama ps` for GPU usage)

---

## Getting Help

If none of the above resolves your issue:

1. Run `schemalytics extract -c <conn> -o schema.json` and inspect the output
2. Check the Ollama logs: `journalctl -u ollama` (Linux) or Console.app (macOS)
3. Open an issue at https://github.com/NiChr0/schemalytics/issues with:
   - Schemalytics version (`pip show schemalytics`)
   - Ollama version and model (`ollama --version`, `ollama list`)
   - Number of tables in your database
   - The `[Agent 4a] tables=N dims=N facts=N max_tokens=N` log line if Agent 4 is slow
   - Error message and stack trace
