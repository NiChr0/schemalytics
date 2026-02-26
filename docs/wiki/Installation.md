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

# Pull the required model
ollama pull qwen2.5-coder:7b

# Verify Ollama is running
curl http://localhost:11434/api/tags
```

Ollama must be running on `localhost:11434` when you use Schemalytics.

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

Connection string: `postgresql://postgres:postgres@localhost:5432/northwind`

---

## Checklist

- [ ] Python 3.10+ installed
- [ ] `pip install schemalytics` complete
- [ ] `ollama serve` running
- [ ] `ollama list` shows `qwen2.5-coder:7b` or `qwen-data:latest`
- [ ] PostgreSQL database accessible

Once all checked, proceed to [Getting Started](Getting-Started).
