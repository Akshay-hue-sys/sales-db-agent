"""Lean ONNX embedder: all-MiniLM-L6-v2 -> 384-d, ~147 MB, no PyTorch."""

from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "Xenova" / "all-MiniLM-L6-v2"


class OnnxEmbedder:
    def __init__(self, model_dir: Path = MODEL_DIR):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        # Target the explicit ONNX graph location
        onnx_path = model_dir / "onnx" / "model.onnx"
        if not onnx_path.exists():
            onnx_path = model_dir / "model.onnx"
        self.session = ort.InferenceSession(str(onnx_path))

    def encode(self, text: str):
        import numpy as np

        if not isinstance(text, str) or not text.strip():
            raise ValueError("Embedding text must be nonempty.")
        encoded = self.tokenizer.encode(text)
        # Supply all 3 required input tensors for BERT-family graphs
        inputs = {
            "input_ids": np.array([encoded.ids], dtype=np.int64),
            "attention_mask": np.array([encoded.attention_mask], dtype=np.int64),
            "token_type_ids": np.array([encoded.type_ids], dtype=np.int64),
        }
        # Forward pass -> hidden states of shape (1, seq_len, 384)
        hidden = self.session.run(None, inputs)[0]
        # Mean pooling across the sequence dimension
        mask = inputs["attention_mask"][..., None]
        vector = (hidden * mask).sum(axis=1)[0] / max(1, mask.sum())
        # L2-normalize to unit length for direct cosine distance ranking
        norm = np.linalg.norm(vector)
        return vector / norm if norm > 0 else vector
