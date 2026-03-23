---
base_model: unsloth/Qwen3.5-4B
library_name: transformers
model_name: adapters-qwen3.5-4b-v5
tags:
- generated_from_trainer
- sft
- trl
- unsloth
licence: license
---

# Model Card for adapters-qwen3.5-4b-v5

This model is a fine-tuned version of [unsloth/Qwen3.5-4B](https://huggingface.co/unsloth/Qwen3.5-4B).
It has been trained using [TRL](https://github.com/huggingface/trl).

## Quick start

```python
from transformers import pipeline

question = "If you had a time machine, but could only go to the past or the future once and never return, which would you choose and why?"
generator = pipeline("text-generation", model="None", device="cuda")
output = generator([{"role": "user", "content": question}], max_new_tokens=128, return_full_text=False)[0]
print(output["generated_text"])
```

## Training procedure

 


This model was trained with SFT.

### Framework versions

- TRL: 0.24.0
- Transformers: 5.2.0
- Pytorch: 2.10.0+cu128
- Datasets: 4.3.0
- Tokenizers: 0.22.2

## Citations



Cite TRL as:
    
```bibtex
@misc{vonwerra2022trl,
	title        = {{TRL: Transformer Reinforcement Learning}},
	author       = {Leandro von Werra and Younes Belkada and Lewis Tunstall and Edward Beeching and Tristan Thrush and Nathan Lambert and Shengyi Huang and Kashif Rasul and Quentin Gallou{\'e}dec},
	year         = 2020,
	journal      = {GitHub repository},
	publisher    = {GitHub},
	howpublished = {\url{https://github.com/huggingface/trl}}
}
```