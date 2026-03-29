"""
QLoRA fine-tune of Qwen3.5-4B for Schemalytics Agent 4b (Gold plan generation).

Target hardware : NVIDIA RTX 3090 24 GB (CUDA, Ampere)
Framework       : Unsloth — memory-optimised QLoRA for NVIDIA GPUs
Dataset format  : JSONL with messages[] (gold_train.jsonl / gold_eval.jsonl)

Agent 4b task: given sanitized Silver facts + pipeline context, output Gold
aggregation models (agg_<grain>_<metric> with SUM/COUNT/AVG metrics).

Gold inputs are compact so 4096 seq_len is ample. Main gains from r=32 and
larger batch size on the 3090.

Usage:
    pip install -r finetune/cuda/requirements.txt
    python finetune/cuda/finetune_gold.py           # train only
    python finetune/cuda/finetune_gold.py --export  # train then export to GGUF + Ollama

Run from the repo root so relative paths resolve correctly.
"""

import json
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL_ID        = "unsloth/Qwen3.5-4B"
ADAPTER_DIR     = "finetune/cuda/adapters-gold-v2"
MAX_SEQ_LENGTH  = 1024   # reduced from 4096 — gold I/O is compact, matches silver speed

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
    per_device_train_batch_size = 4,            # up from 1 — 3090 has headroom
    gradient_accumulation_steps = 2,            # effective batch = 8
    max_steps                   = 600,          # more data needs more steps
    learning_rate               = 2e-5,
    lr_scheduler_type           = "cosine",
    warmup_steps                = 60,
    fp16                        = False,
    bf16                        = True,
    logging_steps               = 10,
    eval_strategy               = "steps",
    eval_steps                  = 100,
    per_device_eval_batch_size  = 2,
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

    train_ds = load_jsonl("finetune/dataset/gold_train.jsonl")
    eval_ds  = load_jsonl("finetune/dataset/gold_eval.jsonl")

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
    """Fuse LoRA adapters and export to GGUF (Q4_K_M), then optionally import into Ollama.

    Uses manual llama.cpp pipeline instead of save_pretrained_gguf to avoid the
    newer unsloth bug where Qwen3.5 is incorrectly treated as a VLM.
    """
    import subprocess
    from unsloth import FastLanguageModel

    if model is None:
        print("Loading adapters for export…")
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name     = ADAPTER_DIR + "/checkpoint-600",
            max_seq_length = MAX_SEQ_LENGTH,
            dtype          = None,
            load_in_4bit   = False,
        )

    # Step 1: merge LoRA into full HF model (16bit)
    merged_dir = "finetune/cuda/merged-gold"
    print(f"Merging LoRA into {merged_dir} ...")
    model.save_pretrained_merged(merged_dir, tokenizer, save_method="merged_16bit")

    # Step 2: convert to F16 GGUF using llama.cpp
    llama_cpp = Path("/root/.unsloth/llama.cpp")
    convert_script = llama_cpp / "convert_hf_to_gguf.py"
    f16_gguf = Path("finetune/cuda/schemalytics-gold-agent-f16.gguf")
    print(f"Converting to F16 GGUF -> {f16_gguf} ...")
    subprocess.run(
        ["python3", str(convert_script), merged_dir,
         "--outfile", str(f16_gguf), "--outtype", "f16"],
        check=True,
    )

    # Step 3: quantize to Q4_K_M
    quantize_bin = llama_cpp / "build" / "bin" / "llama-quantize"
    gguf_path = Path("finetune/cuda/schemalytics-gold-agent-qwen3.5-4b-unsloth.Q4_K_M.gguf")
    print(f"Quantizing to Q4_K_M -> {gguf_path} ...")
    subprocess.run(
        [str(quantize_bin), str(f16_gguf), str(gguf_path), "Q4_K_M"],
        check=True,
    )
    f16_gguf.unlink()  # remove intermediate F16 file

    gguf_abs = str(gguf_path.resolve())
    print(f"\nGGUF saved to: {gguf_abs}")

    if skip_ollama:
        print("Skipping Ollama import (--export-only-gguf).")
        print("To import locally after rsyncing:")
        print(f"  ollama create schemalytics-gold-agent -f <Modelfile>")
        return

    modelfile = Path("finetune/cuda/Modelfile-gold-agent")
    modelfile.write_text(
        f"FROM {gguf_abs}\n"
        "PARAMETER temperature 0\n"
        "PARAMETER num_ctx 8192\n"
        "PARAMETER num_predict 2048\n",
        encoding="utf-8",
    )
    print(f"Modelfile written to {modelfile}")

    import subprocess
    print("Importing into Ollama as schemalytics-gold-agent…")
    subprocess.run(
        ["ollama", "create", "schemalytics-gold-agent", "-f", str(modelfile)],
        check=True,
    )
    print("\nDone! Test with:")
    print("  ollama run schemalytics-gold-agent")
    print("\nTo use in Schemalytics:")
    print("  SCHEMALYTICS_GOLD_MODEL=schemalytics-gold-agent schemalytics generate ...")


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
