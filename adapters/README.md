# LoRA adapter: 34_AN_qlora_v1

Only adapter weights are distributed (about 26 MB); the base model is downloaded from Hugging Face.

| Item | Value |
|---|---|
| Base model | `mlx-community/Qwen2.5-3B-Instruct-4bit`, a 4-bit MLX conversion of `Qwen/Qwen2.5-3B-Instruct` |
| Base licence | **Qwen Research License** (Qwen2.5-3B is the exception in the Qwen2.5 family; the 0.5B/1.5B/7B/14B/32B models are Apache-2.0). It permits research and non-commercial use including fine-tuning and derivatives, which covers this course project; confirm against the model card. For an Apache-2.0 setup, retrain the same adapter on `Qwen2.5-1.5B-Instruct` or `Qwen2.5-7B-Instruct` with `BASE_MODEL=...` |
| Method | QLoRA-style: LoRA adapters trained on top of 4-bit quantised base weights (`mlx_lm lora`, `--fine-tune-type lora`) |
| Layers adapted | last 16 transformer blocks (mlx-lm defaults: rank 8, scale 20, dropout 0) |
| Training | 250 iterations, batch 1, lr 1e-4, `--mask-prompt` (loss only on the JSON answer), max length 2048, seed 407 |
| Data | `data/training/train.jsonl` (84) + `valid.jsonl` (9): island-profile extraction from D08/D09, column mapping from D01/D03/D04/D05. **No evaluation document is used** |
| Loss | validation 0.222 → 0.009 (`logs/train_lora_v1.log`) |
| Hardware / time | Apple M4 Pro, 24 GB, about 35 min |
| Rebuild | `ADAPTER=adapters/34_AN_qlora_v1 ./scripts/train_lora.sh` |
| Use | `LLM(adapter_path="adapters/34_AN_qlora_v1")`, or `--adapter` on the scripts |

The folder `34_AN_qlora_v1/` holds `adapters.safetensors` (final), `adapter_config.json` and the
checkpoints taken every 50 steps. Large files go to the course's designated storage, not to GitHub
(`.gitignore` excludes `adapters/*/`).
