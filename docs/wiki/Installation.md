# Installation

## Prerequisites

Schemalytics requires three things before you install the package itself:

### 1. Python 3.10+

```bash
python3 --version  # must be 3.10 or higher
```

### 2. PostgreSQL access

You need a connection string to a running PostgreSQL database:

```
postgresql://user:password@host:port/database
```

Schemalytics only reads the schema — it never modifies your database.

### 3. Ollama (local LLM runtime)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the general pipeline model (Agents 1, 2, 5)
ollama pull gemma3:4b

# Pull the fine-tuned models (used by default for Agents 3, 4a, 4b)
ollama pull nichr0/schemalytics-classification-agent
ollama pull nichr0/schemalytics-silver-agent
ollama pull nichr0/schemalytics-gold-agent

# Verify Ollama is running
curl http://localhost:11434/api/tags
```

Ollama must be running on `localhost:11434` when you use Schemalytics.

The three fine-tuned models (~2.6 GB each, Qwen3.5-4B QLoRA) are the defaults for Agents 3, 4a, and 4b respectively. `gemma3:4b` handles Agents 1, 2, and 5.

---

## Install Schemalytics

```bash
pip install schemalytics
```

### Verify

```bash
schemalytics --help
```

Expected output:
```
Usage: schemalytics [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  extract   Extract schema from a PostgreSQL database to JSON
  generate  Generate a full dbt project from a PostgreSQL database
```

---

## Install from Source (development)

```bash
git clone https://github.com/NiChr0/schemalytics.git
cd schemalytics
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

The `[dev]` extras install `pytest`, `pytest-cov`, and `ruff`.

---

## Test Database (optional)

For testing without a real database, use the Northwind sample database via Docker:

```bash
docker run -d \
  -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  ghcr.io/nichr0/northwind-postgres:latest
```

Connection string: `postgresql://postgres:mypassword@localhost:5432/northwind`

---

## Checklist

- [ ] Python 3.10+ installed
- [ ] `pip install schemalytics` complete
- [ ] `ollama serve` running
- [ ] `ollama list` shows `gemma3:4b`
- [ ] `ollama list` shows `nichr0/schemalytics-classification-agent` (Agent 3)
- [ ] `ollama list` shows `nichr0/schemalytics-silver-agent` (Agent 4a)
- [ ] `ollama list` shows `nichr0/schemalytics-gold-agent` (Agent 4b)
- [ ] PostgreSQL database accessible

Once all checked, proceed to [Getting Started](Getting-Started).
