import os
import sys
import logging
from PIL import Image
import json

# Ensure backend is in path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from backend.localcura import Config, VLMAgent

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_ollama")


def test_ollama():
    # Load config (will read .env)
    cfg = Config()

    print(f"VLM Provider: {cfg.vlm_provider}")
    print(f"Ollama URL:   {cfg.ollama_base_url}")
    print(f"Ollama Model: {cfg.ollama_model}")

    if cfg.vlm_provider != "ollama":
        print("ERROR: VLM_PROVIDER is not 'ollama'. Check .env")
        return

    # Force enable models for this test instance
    cfg.enable_models = True

    try:
        agent = VLMAgent(cfg)
    except ImportError as e:
        print(f"ImportError: {e}")
        print("Did you install 'openai'? pip install openai")
        return

    # Create a dummy image (red square)
    img = Image.new("RGB", (100, 100), color="red")

    print("\n--- Sending Dummy Image to Ollama ---")
    try:
        result = agent.analyze(img)
        print("\n--- Result Content ---")
        print(json.dumps(result, indent=2))

        if "error" in result:
            print("\n[FAIL] Ollama returned an error.")
        else:
            print("\n[SUCCESS] Ollama responded with JSON!")
            keys = result.keys()
            print(f"Keys found: {list(keys)}")
            if "genre" in keys or "subjects" in keys:
                print("Custom schema detected.")

    except Exception as e:
        print(f"\n[FAIL] Exception during analysis: {e}")


if __name__ == "__main__":
    test_ollama()
