# Schemalytics

Automated dbt project generation from PostgreSQL using local LLMs.

## Quick Start

**1. Install prerequisites**
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:7b

# Install Schemalytics  
pip install git+https://github.com/NiChr0/schemalytics.git
```

**2. Generate your dbt project**
```bash
schemalytics generate \
  -c postgresql://localhost/mydb \
  -o ./dbt_project
```

**3. Interactive refinement**
- AI generates initial plan
- You refine with natural language ("make revenue weekly")
- Approve when ready

**4. Configure and run**
```bash
cd dbt_project

# Configure your database connection in profiles.yml
# See: https://docs.getdbt.com/docs/core/connect-data-platform/profiles.yml

dbt run  # Build your models
```

## What It Does

- Extracts your database schema
- Classifies tables as facts/dimensions  
- Generates dbt models (Bronze/Silver/Gold)
- Creates semantic layer for LLM-powered analytics
- All processing happens locally (privacy-first)

## License

Apache 2.0 • Built by [NiChr0](https://github.com/NiChr0)
