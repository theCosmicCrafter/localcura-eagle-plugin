import requests
import os
from dotenv import load_dotenv

load_dotenv()


def check_models():
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api")
    target_model = os.getenv("OLLAMA_MODEL", "qwen3-vl:8b")

    print(f"Checking for model: {target_model} at {base_url}...")

    try:
        # Ollama API: /api/tags lists models
        response = requests.get(f"{base_url.replace('/api', '')}/api/tags")
        if response.status_code == 200:
            models = response.json().get("models", [])
            found = False
            print("Available models:")
            for m in models:
                print(f" - {m['name']}")
                if m["name"] == target_model or m["name"].startswith(target_model):
                    found = True

            if found:
                print(f"\nSUCCESS: Model '{target_model}' is available.")
            else:
                print(f"\nWARNING: Model '{target_model}' not found in Ollama list.")
                print(f"You may need to run: ollama pull {target_model}")
        else:
            print(f"Failed to connect to Ollama. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error connecting to Ollama: {e}")


if __name__ == "__main__":
    check_models()
