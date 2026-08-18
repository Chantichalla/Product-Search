"""
ONNX Reranker Module
---------------------
Cross-encoder reranker using ms-marco-MiniLM-L6-v2 via ONNX Runtime.

Strategy:
  Primary:  Jina Reranker API (free, 10M tokens) — higher quality
  Fallback: Local ONNX ms-marco-MiniLM-L6-v2    — no API dependency

ms-marco-MiniLM-L6-v2 specs:
  - 22M parameters
  - ~45MB disk (INT8 ONNX quantized)
  - ~180MB RAM while loaded
  - ~60ms to rerank 20 documents on CPU
  - NDCG@10: 74.30 on MS-MARCO benchmark

Usage:
    from config.onnx_reranker import rerank

    ranked = rerank(
        query="iPhone 16 Pro price India",
        passages=["Amazon page...", "Flipkart page...", ...],
        top_n=7
    )
    # returns list of {"text": ..., "score": float, "index": int} sorted by score desc
"""

import os
import numpy as np
from pathlib import Path
from typing import List, Dict, Any

# Local ONNX cache directory
_MODELS_DIR = Path(__file__).parent.parent / "models" / "onnx"
_RERANK_MODEL_DIR = _MODELS_DIR / "ms-marco-minilm-l6-v2"
_HF_RERANK_MODEL_ID = "cross-encoder/ms-marco-MiniLM-L6-v2"

# Global singletons
_rerank_session = None
_rerank_tokenizer = None


def _load_reranker():
    """
    Load or export the ONNX reranker model.
    First run: downloads from HF + converts to ONNX (one-time).
    Subsequent runs: loads from local .onnx in ~0.8s, no internet.
    """
    global _rerank_session, _rerank_tokenizer

    if _rerank_session is not None:
        return

    try:
        from transformers import AutoTokenizer
        import onnxruntime as ort

        _RERANK_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        onnx_file = _RERANK_MODEL_DIR / "model.onnx"

        if onnx_file.exists():
            # Fast path — local cache exists, no internet needed
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_OFFLINE"] = "1"
            print("[OnnxRerank] ⚡ Loading reranker from local ONNX cache...")
            _rerank_tokenizer = AutoTokenizer.from_pretrained(str(_RERANK_MODEL_DIR))
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            _rerank_session = ort.InferenceSession(
                str(onnx_file),
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )
        else:
            # First-ever run: download + export (runs once)
            print(f"[OnnxRerank] ⏳ First run: downloading {_HF_RERANK_MODEL_ID} + exporting to ONNX...")
            print("[OnnxRerank] This takes ~60s once, then loads in 0.8s forever after.")
            from optimum.onnxruntime import ORTModelForSequenceClassification
            model = ORTModelForSequenceClassification.from_pretrained(
                _HF_RERANK_MODEL_ID, export=True
            )
            model.save_pretrained(str(_RERANK_MODEL_DIR))
            tok = AutoTokenizer.from_pretrained(_HF_RERANK_MODEL_ID)
            tok.save_pretrained(str(_RERANK_MODEL_DIR))

            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            _rerank_session = ort.InferenceSession(
                str(onnx_file),
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )
            _rerank_tokenizer = tok
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_OFFLINE"] = "1"
            print("[OnnxRerank] ✅ Reranker exported and cached locally.")

        print("[OnnxRerank] ✅ Reranker ready")

    except ImportError as e:
        raise ImportError(
            f"[OnnxRerank] Missing dependencies: {e}\n"
            "Install with: pip install optimum[exporters] onnxruntime"
        )


def _rerank_local(query: str, passages: List[str], top_n: int) -> List[Dict[str, Any]]:
    """Run local ONNX cross-encoder reranking."""
    _load_reranker()
    scores = []
    for i, passage in enumerate(passages):
        inputs = _rerank_tokenizer(
            query,
            passage,
            return_tensors="np",
            max_length=512,
            truncation=True,
            padding=True,
        )
        output = _rerank_session.run(None, dict(inputs))
        # Cross-encoder outputs logits — higher = more relevant
        score = float(output[0][0][0])
        scores.append({"text": passage, "score": score, "index": i})

    scores.sort(key=lambda x: x["score"], reverse=True)
    return scores[:top_n]


def _rerank_jina(query: str, passages: List[str], top_n: int) -> List[Dict[str, Any]]:
    """Use Jina Reranker API (primary, free 10M tokens)."""
    import httpx
    api_key = os.getenv("JINA_API_KEY", "")
    resp = httpx.post(
        "https://api.jina.ai/v1/rerank",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "jina-reranker-v2-base-multilingual",
            "query": query,
            "documents": passages,
            "top_n": top_n,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    results = resp.json()["results"]
    return [
        {
            "text": r["document"]["text"],
            "score": r["relevance_score"],
            "index": r["index"],
        }
        for r in results
    ]


def rerank(query: str, passages: List[str], top_n: int = 7) -> List[Dict[str, Any]]:
    """
    Rerank passages by relevance to query.

    Args:
        query:    The search query
        passages: List of text passages (URL titles, snippets, etc.)
        top_n:    How many top results to return (default 7)

    Returns:
        List of dicts sorted by score descending:
        [{"text": str, "score": float, "index": int (original position)}, ...]
    """
    if not passages:
        return []

    jina_key = os.getenv("JINA_API_KEY", "")

    if jina_key:
        try:
            results = _rerank_jina(query, passages, top_n)
            print(f"[Reranker] ✅ Jina API: {len(passages)} → top {top_n}")
            return results
        except Exception as e:
            print(f"[Reranker] ⚠️ Jina failed ({e}), falling back to local ONNX...")

    # Fallback: local ONNX
    results = _rerank_local(query, passages, top_n)
    print(f"[Reranker] ✅ Local ONNX: {len(passages)} → top {top_n}")
    return results


def preload():
    """
    Preload reranker at server startup.
    Call from FastAPI lifespan to eliminate per-request load cost.
    """
    jina_key = os.getenv("JINA_API_KEY", "")
    if not jina_key:
        # Only preload local model if Jina is not configured
        _load_reranker()
    else:
        print("[OnnxRerank] Jina API key found — local ONNX will only load if Jina fails.")
