"""
QLoRA fine-tune of Qwen3.5-4B (non-thinking mode) for Schemalytics table classification.

Target hardware : NVIDIA RTX 3060 Ti 8 GB (CUDA, Ampere)
Framework       : Unsloth — memory-optimised QLoRA for NVIDIA GPUs
Dataset format  : Same JSONL as the MLX pipeline (messages[])

Usage:
    pip install -r finetune/cuda/requirements.txt
    python finetune/cuda/finetune.py           # train only
    python finetune/cuda/finetune.py --export  # train then export to GGUF + Ollama

Run from the repo root so relative paths resolve correctly.
"""

import json
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Config — mirrors mlx/config.yaml exactly where possible
# ---------------------------------------------------------------------------

MODEL_ID        = "unsloth/Qwen3.5-4B"
ADAPTER_DIR     = "finetune/cuda/adapters-qwen3.5-4b-v6"
MAX_SEQ_LENGTH  = 1024   # schemas fit in 1024 tokens; saves VRAM

LORA = dict(
    r               = 8,
    lora_alpha      = 16,
    lora_dropout    = 0.05,
    target_modules  = [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    bias            = "none",
    use_gradient_checkpointing = "unsloth",  # Unsloth's optimised checkpointing
    random_state    = 42,
)

TRAIN = dict(
    output_dir                  = ADAPTER_DIR,
    per_device_train_batch_size = 4,
    gradient_accumulation_steps = 2,   # effective batch 8
    max_steps                   = 400,
    learning_rate               = 3e-5,
    lr_scheduler_type           = "cosine",
    warmup_steps                = 50,
    fp16                        = False,
    bf16                        = True,  # RTX 3060 Ti (Ampere): bfloat16 required by Unsloth 4-bit model
    logging_steps               = 10,
    eval_strategy               = "steps",
    eval_steps                  = 50,
    per_device_eval_batch_size  = 1,
    save_strategy               = "steps",
    save_steps                  = 400,
    load_best_model_at_end      = False,
    seed                        = 42,
    dataloader_num_workers      = 4,
    report_to                   = "none",
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
        enable_thinking=False,  # Qwen3.5 non-thinking mode
    )
    return {"text": text}


def main(export: bool = False):
    from unsloth import FastLanguageModel
    from trl import SFTTrainer, SFTConfig

    print(f"Loading model: {MODEL_ID}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name     = MODEL_ID,
        max_seq_length = MAX_SEQ_LENGTH,
        dtype          = None,        # auto (fp16 on RTX 3060 Ti)
        load_in_4bit   = True,
    )

    model = FastLanguageModel.get_peft_model(model, **LORA)

    # Dataset
    train_ds = load_jsonl("finetune/dataset/train.jsonl")
    eval_ds  = load_jsonl("finetune/dataset/eval.jsonl")

    trainer = SFTTrainer(
        model           = model,
        tokenizer       = tokenizer,
        train_dataset   = train_ds,
        eval_dataset    = eval_ds,
        args            = SFTConfig(**TRAIN),
        packing         = False,
    )

    print("Starting training…")
    trainer.train()
    print(f"Adapters saved to {ADAPTER_DIR}/")

    if export:
        _export(model, tokenizer)


def _export(model=None, tokenizer=None):
    """Fuse LoRA adapters and export to GGUF (Q4_K_M), then import into Ollama."""
    from unsloth import FastLanguageModel

    if model is None:
        print("Loading adapters for export…")
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name     = ADAPTER_DIR + "/checkpoint-400",
            max_seq_length = MAX_SEQ_LENGTH,
            dtype          = None,
            load_in_4bit   = True,
        )

    gguf_prefix = "finetune/cuda/schemalytics-classification-agent-v2"
    print(f"Exporting GGUF (Q4_K_M) -> {gguf_prefix}-unsloth.Q4_K_M.gguf ...")
    model.save_pretrained_gguf(gguf_prefix, tokenizer, quantization_method="q4_k_m")

    # Ollama Modelfile — use absolute path so Ollama can find the GGUF
    gguf_abs = str(Path(gguf_prefix + "-unsloth.Q4_K_M.gguf").resolve())
    modelfile = Path("finetune/cuda/Modelfile-classification-agent")
    modelfile.write_text(
        f"FROM {gguf_abs}\n"
        "PARAMETER temperature 0\n"
        "PARAMETER num_ctx 12288\n"
        "PARAMETER num_predict 2048\n",
        encoding="utf-8",
    )
    print(f"Modelfile written to {modelfile}")

    import subprocess
    print("Importing into Ollama as schemalytics-classification-agent…")
    subprocess.run(
        ["ollama", "create", "schemalytics-classification-agent", "-f", str(modelfile)],
        check=True,
    )
    print("\nDone! Test with:")
    print("  ollama run schemalytics-classification-agent")
    print("\nTo use in Schemalytics:")
    print("  SCHEMALYTICS_OLLAMA_MODEL=schemalytics-classification-agent schemalytics generate ...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export to GGUF and import into Ollama after training",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Skip training; only export already-saved adapters",
    )
    args = parser.parse_args()

    if args.export_only:
        _export()
    else:
        main(export=args.export)
