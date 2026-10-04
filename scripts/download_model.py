"""Explicit manual network setup; importing this module does not download."""

from pathlib import Path


def main():
    from huggingface_hub import snapshot_download

    snapshot_download(
        "Xenova/all-MiniLM-L6-v2",
        local_dir=str(Path(__file__).resolve().parents[1] / "models" / "Xenova" / "all-MiniLM-L6-v2"),
        allow_patterns=["*.onnx", "*.json", "*.txt"],
    )
    print("Model assets downloaded. Reload card vectors if the model revision changed.")


if __name__ == "__main__":
    main()
