"""Convert an mlx-lm LoRA adapter into a Hugging Face PEFT adapter (for LLM_BACKEND=hf).

mlx-lm computes  y = W x + scale * (x @ A) @ B   with A: (in, r), B: (r, out)
PEFT computes    y = W x + (alpha / r) * B' (A' x) with A': (r, in), B': (out, r)
so A' = A.T, B' = B.T and alpha = scale * r.

Usage:  python scripts/convert_adapter_mlx_to_peft.py adapters/34_AN_qlora_v1
Writes: adapters/34_AN_qlora_v1/peft/{adapter_model.safetensors, adapter_config.json}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from safetensors.numpy import load_file, save_file

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agri import config  # noqa: E402


def convert(adapter_dir: Path, base_model: str) -> Path:
    cfg = json.loads((adapter_dir / "adapter_config.json").read_text())
    lp = cfg["lora_parameters"]
    rank, scale = int(lp["rank"]), float(lp["scale"])
    weights = load_file(str(adapter_dir / "adapters.safetensors"))
    out, targets = {}, set()
    for key, arr in weights.items():
        module, kind = key.rsplit(".", 1)              # model.layers.20.mlp.down_proj, lora_a
        targets.add(module.rsplit(".", 1)[1])
        peft_kind = "lora_A" if kind == "lora_a" else "lora_B"
        out[f"base_model.model.{module}.{peft_kind}.weight"] = np.ascontiguousarray(arr.T.astype(np.float32))
    layers = sorted({int(k.split(".")[2]) for k in weights})
    peft_cfg = {
        "peft_type": "LORA", "task_type": "CAUSAL_LM", "base_model_name_or_path": base_model,
        "r": rank, "lora_alpha": scale * rank, "lora_dropout": float(lp.get("dropout", 0.0)),
        "target_modules": sorted(targets), "layers_to_transform": layers, "bias": "none",
        "fan_in_fan_out": False, "inference_mode": True,
    }
    dst = adapter_dir / "peft"
    dst.mkdir(exist_ok=True)
    save_file(out, str(dst / "adapter_model.safetensors"))
    (dst / "adapter_config.json").write_text(json.dumps(peft_cfg, indent=2))
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("adapter_dir", type=Path)
    ap.add_argument("--base-model", default=config.HF_BASE_MODEL)
    a = ap.parse_args()
    dst = convert(a.adapter_dir, a.base_model)
    print(f"PEFT adapter written to {dst} (base {a.base_model})")


if __name__ == "__main__":
    main()
