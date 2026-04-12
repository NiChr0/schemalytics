# Configuration

Schemalytics is configured entirely through environment variables. There is no config file — the pipeline is interactive by design.

---

## LLM Provider

```bash
# Ollama (default) — runs locally, no API key needed
SCHEMALYTICS_LLM_PROVIDER=ollama

# Anthropic Claude — requires an API key
SCHEMALYTICS_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

| Provider | Model | Notes |
|----------|-------|-------|
| `ollama` | `gemma3:4b` (default) | Local, private, free. Requires Ollama running at `localhost:11434`. |
| `anthropic` | `claude-sonnet-4-20250514` | Cloud API. Faster for large schemas (50+ tables). |

---

## Ollama General Model

Used by Agents 1, 2, and 5 (industry inference, metrics suggestion, plan refinement):

```bash
SCHEMALYTICS_OLLAMA_MODEL=gemma3:4b   # default
```

Override to use any Ollama model:

```bash
SCHEMALYTICS_OLLAMA_MODEL=llama3.2 schemalytics generate -c postgresql://...
```

---

## Per-Agent Model Overrides

Agents 3, 4a, and 4b use dedicated fine-tuned models by default. Override individually:

```bash
# Agent 3 — table classification (fact/dim/bridge/reference)
SCHEMALYTICS_AGENT3_MODEL=nichr0/schemalytics-classification-agent   # default

# Agent 4a — Silver layer plan (dim_*, fct_*)
SCHEMALYTICS_AGENT4A_MODEL=nichr0/schemalytics-silver-agent          # default

# Agent 4b — Gold layer plan (agg_*)
SCHEMALYTICS_AGENT4B_MODEL=nichr0/schemalytics-gold-agent            # default
```

To revert an agent to the general Ollama model:

```bash
SCHEMALYTICS_AGENT3_MODEL=gemma3:4b schemalytics generate -c postgresql://...
```

---

## Full Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SCHEMALYTICS_LLM_PROVIDER` | `ollama` | LLM backend: `ollama` or `anthropic` |
| `SCHEMALYTICS_OLLAMA_MODEL` | `gemma3:4b` | Ollama model for Agents 1, 2, 5 |
| `SCHEMALYTICS_AGENT3_MODEL` | `nichr0/schemalytics-classification-agent` | Model for Agent 3 (table classification) |
| `SCHEMALYTICS_AGENT4A_MODEL` | `nichr0/schemalytics-silver-agent` | Model for Agent 4a (Silver plan) |
| `SCHEMALYTICS_AGENT4B_MODEL` | `nichr0/schemalytics-gold-agent` | Model for Agent 4b (Gold plan) |
| `ANTHROPIC_API_KEY` | — | Required when `SCHEMALYTICS_LLM_PROVIDER=anthropic` |

---

## Example: Use Anthropic for All Agents

```bash
SCHEMALYTICS_LLM_PROVIDER=anthropic \
ANTHROPIC_API_KEY=sk-ant-... \
schemalytics generate \
  -c postgresql://user:pass@localhost/mydb \
  -o ./dbt_project
```

## Example: Use Fine-Tuned Models Explicitly

```bash
SCHEMALYTICS_AGENT3_MODEL=nichr0/schemalytics-classification-agent \
SCHEMALYTICS_AGENT4A_MODEL=nichr0/schemalytics-silver-agent \
SCHEMALYTICS_AGENT4B_MODEL=nichr0/schemalytics-gold-agent \
schemalytics generate \
  -c postgresql://user:pass@localhost/mydb \
  -o ./dbt_project
```

(These are already the defaults — this form is useful if you want to be explicit in scripts.)
