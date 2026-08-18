"""
ONNX Embedding Module
---------------------
Shared embedding utility using all-MiniLM-L6-v2 via ONNX Runtime.

Replaces both:
- Previous: SentenceTransformer (30s HF validation on every restart)
- Previous: Ollama nomic-embed-text (requires Ollama running 24/7)

This solution:
- Loads the model ONCE at server startup (~0.5s from local .onnx file)
- Zero internet dependency after the first download
- Zero external service dependency (no Ollama, no API key)
- Works on any CPU, any cloud server

all-MiniLM-L6-v2 specs:
  - 384 dimensions
  - 512 token context window
  - ~23MB on disk (INT8 ONNX quantized)
  - ~90MB RAM while loaded
  - ~15ms per query on CPU
"""

import os
import numpy as np
from pathlib import Path

# Block HuggingFace network validation after first download
# This eliminates the 8-12 HEAD request dance on every restart
os.environ.setdefault("TRANSFORMERS_OFFLINE", "0")  # Allow first download
os.environ.setdefault("HF_HUB_OFFLINE", "0")

# Where to cache the exported ONNX model locally
_MODELS_DIR = Path(__file__).parent.parent / "models" / "onnx"
_EMBED_MODEL_DIR = _MODELS_DIR / "all-minilm-l6-v2"

EMBEDDING_DIMENSION = 384  # all-MiniLM-L6-v2 output dimension
_HF_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"

# Global singleton — loaded once, shared by all requests
_embed_session = None
_tokenizer = None


def _load_model():
    """
    Load or export the ONNX embedding model.
    On first run: downloads from HuggingFace + exports to ONNX (one-time, ~30s).
    All subsequent runs: loads from local .onnx file (~0.5s, no internet).
    """
    global _embed_session, _tokenizer

    if _embed_session is not None:
        return

    try:
        from optimum.onnxruntime import ORTModelForFeatureExtraction
        from transformers import AutoTokenizer
        import onnxruntime as ort

        _EMBED_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        onnx_file = _EMBED_MODEL_DIR / "model.onnx"

        if onnx_file.exists():
            # Fast path: load pre-exported local ONNX file (0.5s, no internet)
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_OFFLINE"] = "1"
            print("[OnnxEmbed] ⚡ Loading from local ONNX cache...")
            _tokenizer = AutoTokenizer.from_pretrained(str(_EMBED_MODEL_DIR))
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            _embed_session = ort.InferenceSession(
                str(onnx_file),
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )
        else:
            # First-ever run: download + export to ONNX (runs once, then cached)
            print(f"[OnnxEmbed] ⏳ First run: downloading + exporting {_HF_MODEL_ID} to ONNX...")
            print(f"[OnnxEmbed] This takes ~30s once, then loads in 0.5s forever after.")
            model = ORTModelForFeatureExtraction.from_pretrained(
                _HF_MODEL_ID, export=True
            )
            model.save_pretrained(str(_EMBED_MODEL_DIR))
            tok = AutoTokenizer.from_pretrained(_HF_MODEL_ID)
            tok.save_pretrained(str(_EMBED_MODEL_DIR))

            # Now load via raw ORT session for performance
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            _embed_session = ort.InferenceSession(
                str(onnx_file),
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )
            _tokenizer = tok
            # Lock offline mode now that model is cached
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_OFFLINE"] = "1"
            print("[OnnxEmbed] ✅ Model exported and cached locally.")

        print(f"[OnnxEmbed] ✅ Embedding model ready ({EMBEDDING_DIMENSION}-dim)")

    except ImportError as e:
        raise ImportError(
            f"[OnnxEmbed] Missing dependencies: {e}\n"
            "Install with: pip install optimum[exporters] onnxruntime"
        )


def get_embedding(text: str) -> np.ndarray:
    """
    Generate a 384-dim embedding vector for text via ONNX.
    Model is loaded on first call and shared globally.
    """
    _load_model()
    inputs = _tokenizer(
        text,
        return_tensors="np",
        max_length=512,
        truncation=True,
        padding=True,
    )
    outputs = _embed_session.run(None, dict(inputs))
    # Mean pooling over token dimension
    token_embeddings = outputs[0]          # shape: (1, seq_len, 384)
    attention_mask = inputs["attention_mask"]  # shape: (1, seq_len)
    mask = attention_mask[..., np.newaxis].astype(np.float32)
    summed = np.sum(token_embeddings * mask, axis=1)
    counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
    mean_pooled = summed / counts
    # L2 normalize
    norm = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
    normalized = mean_pooled / np.clip(norm, 1e-9, None)
    return normalized[0].astype(np.float32)


def get_embedding_bytes(text: str) -> bytes:
    """Return embedding as raw bytes for Redis vector storage."""
    return get_embedding(text).tobytes()


def preload():
    """
    Explicitly preload the embedding model.
    Call this at server startup (FastAPI lifespan) so the first user
    request doesn't pay the load cost.
    """
    _load_model()
