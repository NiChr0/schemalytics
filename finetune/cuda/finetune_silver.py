"""
QLoRA fine-tune of Qwen3.5-4B for Schemalytics Agent 4a (Silver plan generation).

Target hardware : NVIDIA RTX 3090 24 GB (CUDA, Ampere)
Framework       : Unsloth — memory-optimised QLoRA for NVIDIA GPUs
Dataset format  : JSONL with messages[] (silver_train.jsonl / silver_eval.jsonl)

Agent 4a task: given a schema + pipeline context + table roles, output a Silver
ModelingPlan (bronze list + dimension models + fact models).

max_seq_length=8192 covers all schema sizes including large 100+ table schemas.
MAX_CHARS filter removed from build_dataset_agent4.py for this run.

Usage:
    pip install -r finetune/cuda/requirements.txt
    python finetune/cuda/finetune_silver.py           # train only
    python finetune/cuda/finetune_silver.py --export  # train then export to GGUF + Ollama

Run from the repo root so relative paths resolve correctly.
"""

import json
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL_ID        = "unsloth/Qwen3.5-4B"
ADAPTER_DIR     = "finetune/cuda/adapters-silver-v2"
MAX_SEQ_LENGTH  = 1024   # must match 3060Ti config — linear attn OOMs at higher values

LORA = dict(
    r               = 8,
    lora_alpha      = 16,
    lora_dropout    = 0.05,
    target_modules  = [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    bias            = "none",
    use_gradient_checkpointing = "unsloth",
    random_state    = 42,
)

TRAIN = dict(
    output_dir                  = ADAPTER_DIR,
    per_device_train_batch_size = 4,
    gradient_accumulation_steps = 2,            # effective batch = 8
    max_steps                   = 600,          # more data needs more steps
    learning_rate               = 2e-5,         # slightly lower for larger batch
    lr_scheduler_type           = "cosine",
    warmup_steps                = 60,
    fp16                        = False,
    bf16                        = True,
    logging_steps               = 10,
    eval_strategy               = "steps",
    eval_steps                  = 100,
    per_device_eval_batch_size  = 1,
    save_strategy               = "steps",
    save_steps                  = 600,
    load_best_model_at_end      = False,
    seed                        = 42,
    dataloader_num_workers      = 4,
    report_to                   = "none",
    dataset_text_field          = "text",
    max_seq_length              = MAX_SEQ_LENGTH,
)

# ---------------------------------------------------------------------------

def load_jsonl(path: str):
    from datasets import Dataset
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return Dataset.from_list(records)


def apply_chat_template(sample, tokenizer):
    text = tokenizer.apply_chat_template(
        sample["messages"],
        tokenize=False,
        add_generation_prompt=False,
        enable_thinking=False,
    )
    return {"text": text}


def main(export: bool = False):
    from unsloth import FastLanguageModel
    from trl import SFTTrainer, SFTConfig

    print(f"Loading model: {MODEL_ID}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name     = MODEL_ID,
        max_seq_length = MAX_SEQ_LENGTH,
        dtype          = None,
        load_in_4bit   = True,
    )

    model = FastLanguageModel.get_peft_model(model, **LORA)

    train_ds = load_jsonl("finetune/dataset/silver_train.jsonl")
    eval_ds  = load_jsonl("finetune/dataset/silver_eval.jsonl")

    fn = lambda s: apply_chat_template(s, tokenizer)
    train_ds = train_ds.map(fn)
    eval_ds  = eval_ds.map(fn)

    trainer = SFTTrainer(
        model           = model,
        tokenizer       = tokenizer,
        train_dataset   = train_ds,
        eval_dataset    = eval_ds,
        args            = SFTConfig(**TRAIN),
    )

    print("Starting training…")
    trainer.train()
    print(f"Adapters saved to {ADAPTER_DIR}/")

    if export:
        _export(model, tokenizer)


def _export(model=None, tokenizer=None, skip_ollama: bool = False):
    """Fuse LoRA adapters and export to GGUF (Q4_K_M), then optionally import into Ollama."""
    from unsloth import FastLanguageModel

    if model is None:
        print("Loading adapters for export…")
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name     = ADAPTER_DIR + "/checkpoint-600",
            max_seq_length = MAX_SEQ_LENGTH,
            dtype          = None,
            load_in_4bit   = True,
        )

    gguf_prefix = "finetune/cuda/schemalytics-silver-agent-qwen3.5-4b"
    print(f"Exporting GGUF (Q4_K_M) -> {gguf_prefix}-unsloth.Q4_K_M.gguf ...")
    model.save_pretrained_gguf(gguf_prefix, tokenizer, quantization_method="q4_k_m")

    gguf_abs = str(Path(gguf_prefix + "-unsloth.Q4_K_M.gguf").resolve())
    print(f"\nGGUF saved to: {gguf_abs}")

    if skip_ollama:
        print("Skipping Ollama import (--export-only-gguf).")
        print("To import locally after rsyncing:")
        print(f"  ollama create schemalytics-silver-agent -f <Modelfile>")
        return

    modelfile = Path("finetune/cuda/Modelfile-silver-agent")
    modelfile.write_text(
        f"FROM {gguf_abs}\n"
        "PARAMETER temperature 0\n"
        "PARAMETER num_ctx 12288\n"
        "PARAMETER num_predict 4096\n",
        encoding="utf-8",
    )
    print(f"Modelfile written to {modelfile}")

    import subprocess
    print("Importing into Ollama as schemalytics-silver-agent…")
    subprocess.run(
        ["ollama", "create", "schemalytics-silver-agent", "-f", str(modelfile)],
        check=True,
    )
    print("\nDone! Test with:")
    print("  ollama run schemalytics-silver-agent")
    print("\nTo use in Schemalytics:")
    print("  SCHEMALYTICS_SILVER_MODEL=schemalytics-silver-agent schemalytics generate ...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", action="store_true",
                        help="Export to GGUF and import into Ollama after training")
    parser.add_argument("--export-only", action="store_true",
                        help="Skip training; export adapters and import into Ollama")
    parser.add_argument("--export-only-gguf", action="store_true",
                        help="Skip training; export GGUF only (no Ollama import — for pod use)")
    args = parser.parse_args()

    if args.export_only_gguf:
        _export(skip_ollama=True)
    elif args.export_only:
        _export()
    else:
        main(export=args.export)
