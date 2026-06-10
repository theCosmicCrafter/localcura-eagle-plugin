import os
import sys
import logging
import shutil
from pathlib import Path
from huggingface_hub import hf_hub_download, snapshot_download
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("setup")

# Load env
load_dotenv()

MODELS_DIR = Path("models")
ENV_FILE = Path(".env")


def get_input(prompt, default=None):
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    else:
        return input(f"{prompt}: ").strip()


def update_env(key, value):
    lines = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text().splitlines()

    # Remove existing key if present
    lines = [l for l in lines if not l.startswith(f"{key}=")]
    # Append new key
    lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(lines))
    print(f"Updated .env: {key}={value}")


def setup_qwen():
    print("\n--- Qwen2.5-VL Setup ---")
    choice = get_input("Download Qwen model (y) or use local path (n)?", "y")

    if choice.lower() == "n":
        path = get_input("Enter full path to Qwen .gguf file")
        if path and os.path.exists(path):
            update_env("QWEN_PATH", path)
        else:
            print("Invalid path skipped.")
        return

    # Download
    repo = "bartowski/Qwen2.5-VL-7B-Instruct-GGUF"
    filename = "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"

    print(f"Downloading {filename} from {repo}...")
    target_dir = MODELS_DIR / "qwen"
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        path = hf_hub_download(
            repo_id=repo,
            filename=filename,
            local_dir=target_dir,
            local_dir_use_symlinks=False,
        )
        print(f"Downloaded to: {path}")
        # We don't strictly need to set QWEN_PATH if it's in the default location,
        # but setting it makes it explicit.
        # But for portability, maybe better NOT to set it if it's in default?
        # Actually, let's not set env var if it's in default,
        # so the 'Smart Discovery' in Config works if they move the folder later.
    except Exception as e:
        print(f"Error downloading Qwen: {e}")


def setup_clip():
    print("\n--- CLIP Tagging Model Setup ---")
    choice = get_input("Download CLIP model (y) or use local path (n)?", "y")

    if choice.lower() == "n":
        path = get_input("Enter full path to CLIP model folder")
        if path and os.path.exists(path):
            update_env("TAGGER_PATH", path)
        else:
            print("Invalid path skipped.")
        return

    # Download
    repo = "openai/clip-vit-large-patch14"
    print(f"Downloading {repo}...")
    target_dir = MODELS_DIR / "clip-vit-large-patch14"
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        path = snapshot_download(
            repo_id=repo,
            local_dir=target_dir,
            local_dir_use_symlinks=False,
            ignore_patterns=["*.msgpack", "*.h5", "*.tflite"],
        )
        print(f"Downloaded to: {path}")
    except Exception as e:
        print(f"Error downloading CLIP: {e}")


if __name__ == "__main__":
    print("=== CosmicTagger Setup Wizard ===\n")

    # 1. HF Token
    token = os.getenv("HF_TOKEN")
    if not token:
        print("Hugging Face Token is required for some models.")
        token = get_input("Enter HF Token (or press Enter to skip)")
        if token:
            update_env("HF_TOKEN", token)
            os.environ["HF_TOKEN"] = token

    # 2. Models
    setup_qwen()
    setup_clip()

    print("\n=== Setup Complete ===")
    print("You can now start the server from the Eagle Plugin.")
