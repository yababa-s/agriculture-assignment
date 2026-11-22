"""Local LLM client (MLX). One model instance per (base, adapter) pair, greedy decoding, JSON helpers."""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass

from langsmith import traceable

from agri import config

_LOCK = threading.Lock()
_MODELS: dict[tuple[str, str | None], tuple] = {}


@dataclass
class LLMResult:
    text: str
    parsed: object | None
    ok: bool
    error: str | None
    latency_s: float
    prompt_tokens: int
    completion_tokens: int
    salvaged: bool = False     # reply was not valid JSON as a whole; complete leading items were recovered


class LLM:
    """Thin wrapper so agents never import mlx directly (lets us swap backends / disable the LLM)."""

    def __init__(self, base_model: str | None = None, adapter_path: str | None = None, backend: str | None = None):
        self.backend = backend or config.LLM_BACKEND
        self.base_model = base_model or config.BASE_MODEL
        self.adapter_path = (adapter_path if adapter_path is not None else config.ADAPTER_PATH) or None
        self.calls = 0

    @property
    def enabled(self) -> bool:
        return self.backend != "none"

    @property
    def label(self) -> str:
        return f"{self.base_model}" + (f" + LoRA({self.adapter_path})" if self.adapter_path else "")

    def _load(self):
        key = (self.backend, self.base_model, self.adapter_path)
        with _LOCK:
            if key not in _MODELS:
                if self.backend == "hf":
                    _MODELS[key] = _load_hf(self.adapter_path)
                elif self.backend == "mlx":
                    try:
                        from mlx_lm import load
                    except ImportError as e:  # not Apple Silicon, or mlx-lm not installed
                        raise RuntimeError("LLM_BACKEND=mlx needs Apple Silicon with mlx-lm installed. "
                                           "Use LLM_BACKEND=hf (pip install -r requirements-hf.txt) "
                                           "or LLM_BACKEND=none (rules only).") from e
                    _MODELS[key] = load(self.base_model, adapter_path=self.adapter_path)
                else:
                    raise RuntimeError(f"unknown LLM_BACKEND={self.backend!r} (use mlx, hf or none)")
            return _MODELS[key]

    @traceable(run_type="llm", name="local_llm")
    def chat(self, system: str, user: str, max_tokens: int | None = None) -> str:
        if not self.enabled:
            raise RuntimeError("LLM backend disabled")
        if self.backend == "hf":
            return self._chat_hf(system, user, max_tokens)
        model, tok = self._load()
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        prompt = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        self.calls += 1
        with _LOCK:  # MLX models are not safe for concurrent generation
            out = generate(model, tok, prompt=prompt, max_tokens=max_tokens or config.LLM_MAX_TOKENS,
                           sampler=make_sampler(temp=0.0), verbose=False)
        self._last_prompt_tokens = len(tok.encode(prompt))
        self._last_completion_tokens = len(tok.encode(out))
        return out

    def _chat_hf(self, system: str, user: str, max_tokens: int | None) -> str:
        import torch
        model, tok = self._load()
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        prompt = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        ids = tok(prompt, return_tensors="pt")["input_ids"].to(model.device)
        self.calls += 1
        with _LOCK, torch.no_grad():
            out = model.generate(ids, max_new_tokens=max_tokens or config.LLM_MAX_TOKENS, do_sample=False)
        new = out[0, ids.shape[1]:]
        self._last_prompt_tokens, self._last_completion_tokens = int(ids.shape[1]), int(new.shape[0])
        return tok.decode(new, skip_special_tokens=True)


    def json_call(self, system: str, user: str, max_tokens: int | None = None) -> LLMResult:
        t0 = time.time()
        try:
            text = self.chat(system, user, max_tokens)
        except Exception as e:  # noqa: BLE001 - surfaced to the agent as a failed tool result
            return LLMResult("", None, False, f"llm_error: {e}", time.time() - t0, 0, 0)
        parsed, err = parse_json(text)
        salvaged = False
        if parsed is None:
            parsed = salvage_list(text)
            salvaged = parsed is not None
        return LLMResult(text, parsed, parsed is not None, err, time.time() - t0,
                         getattr(self, "_last_prompt_tokens", 0), getattr(self, "_last_completion_tokens", 0), salvaged)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_json(text: str) -> tuple[object | None, str | None]:
    """Parse the first JSON object/array in a model reply. Tolerates code fences and trailing prose."""
    m = _FENCE.search(text)
    candidate = m.group(1) if m else text
    start = min([i for i in (candidate.find("{"), candidate.find("[")) if i >= 0], default=-1)
    if start < 0:
        return None, "no_json_found"
    dec = json.JSONDecoder()
    try:
        obj, _ = dec.raw_decode(candidate[start:])
        return obj, None
    except json.JSONDecodeError as e:
        # common small-model error: trailing commas
        fixed = re.sub(r",\s*([}\]])", r"\1", candidate[start:])
        try:
            obj, _ = dec.raw_decode(fixed)
            return obj, None
        except json.JSONDecodeError:
            return None, f"invalid_json: {e.msg} at {e.pos}"


_LEADING_ZERO = re.compile(r'(:\s*-?)0+(\d)')


def salvage_list(text: str) -> list | None:
    """Recover the complete objects at the start of a broken JSON list.

    Small models sometimes loop (repeating one item until the token limit) or emit
    numbers such as 09.0. Every recovered item is still checked by the caller's
    groundedness gate, so salvage can only add verified items, never unchecked ones.
    """
    start = text.find("[")
    if start < 0:
        return None
    body = _LEADING_ZERO.sub(r"\1\2", text[start + 1:])
    dec = json.JSONDecoder()
    items, i = [], 0
    while True:
        while i < len(body) and body[i] in " \n\t\r,":
            i += 1
        if i >= len(body) or body[i] != "{":
            break
        try:
            obj, end = dec.raw_decode(body, i)
        except json.JSONDecodeError:
            break
        items.append(obj)
        i = end
    return items or None


def _load_hf(adapter_path: str | None):
    """transformers + peft backend for machines without Apple MLX (CPU, CUDA or MPS)."""
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as e:
        raise RuntimeError("LLM_BACKEND=hf needs: pip install -r requirements-hf.txt") from e
    from pathlib import Path
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    dtype = torch.float32 if device == "cpu" else torch.float16
    tok = AutoTokenizer.from_pretrained(config.HF_BASE_MODEL)
    model = AutoModelForCausalLM.from_pretrained(config.HF_BASE_MODEL, dtype=dtype).to(device)
    if adapter_path:
        peft_dir = Path(adapter_path) / "peft"
        if not peft_dir.exists():
            raise RuntimeError(f"{peft_dir} not found. Convert the MLX adapter first: "
                               f"python scripts/convert_adapter_mlx_to_peft.py {adapter_path}")
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(peft_dir)).to(device)
    model.eval()
    return model, tok
