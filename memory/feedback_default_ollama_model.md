---
name: Default Ollama model is gemma3:4b
description: The default general-purpose Ollama model for Schemalytics is gemma3:4b — never suggest gemma3:12b-it-qat or qwen3-30b-data
type: feedback
---

The default Ollama model is `gemma3:4b` (set in `llm.py` line 11).

**Why:** gemma3:4b (3.3 GB) vs gemma3:12b-it-qat (8.9 GB) — 3-4x faster per agent with near-identical output quality on Northwind. The smaller size allows all 4 models (gemma3:4b + 3× nichr0 fine-tuned) to coexist in 24 GB unified memory simultaneously, eliminating mid-pipeline model switching overhead (~196s per swap).

**How to apply:** Never suggest gemma3:12b-it-qat or qwen3-30b-data as the default. If suggesting a model upgrade path, gemma3n:e4b is the next candidate to evaluate. OLLAMA_MAX_LOADED_MODELS=4 is set via launchd to keep all models resident.
