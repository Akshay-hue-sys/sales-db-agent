from huggingface_hub import snapshot_download

snapshot_download(
    "Xenova/all-MiniLM-L6-v2",
    local_dir="models/Xenova/all-MiniLM-L6-v2",
    allow_patterns=["*.onnx", "*.json", "*.txt"]
)
print("done")
