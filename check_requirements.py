#!/usr/bin/env python3
"""
Check if all requirements are properly installed for CosmicTagger.
Run this after installing dependencies to verify everything is ready.
"""

import sys

def check_import(module_name, feature):
    """Try to import a module and report status."""
    try:
        __import__(module_name)
        print(f"✅ {module_name:<30} - {feature}")
        return True
    except ImportError as e:
        print(f"❌ {module_name:<30} - {feature} - ERROR: {e}")
        return False

def main():
    print("=" * 60)
    print("CosmicTagger Requirements Check")
    print("=" * 60)
    print()
    
    all_ok = True
    
    # Core dependencies
    print("Core Dependencies:")
    all_ok &= check_import("fastapi", "Web API framework")
    all_ok &= check_import("uvicorn", "ASGI server")
    all_ok &= check_import("requests", "HTTP client")
    all_ok &= check_import("dotenv", "Environment configuration")
    print()
    
    # Image processing
    print("Image Processing:")
    all_ok &= check_import("PIL", "Image processing (Pillow)")
    all_ok &= check_import("pillow_avif", "AVIF image support")
    all_ok &= check_import("pillow_heif", "HEIF/HEIC image support")
    print()
    
    # Video processing
    print("Video Processing:")
    cv2_ok = check_import("cv2", "Video frame extraction (OpenCV)")
    if not cv2_ok:
        print("   ⚠️  Video support disabled. Install with: pip install opencv-python-headless")
    print()
    
    # AI/ML
    print("AI/ML Models:")
    all_ok &= check_import("transformers", "Hugging Face transformers")
    all_ok &= check_import("accelerate", "Model acceleration")
    print()
    
    # Document processing
    print("Document Processing:")
    check_import("pypdfium2", "PDF text extraction")  # Optional
    check_import("docx", "Word document support")  # Optional
    print()
    
    # Check Ollama connectivity
    print("Ollama Connectivity:")
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name", "unknown") for m in models]
            print(f"✅ Ollama running               - Available models: {', '.join(model_names[:3])}")
        else:
            print(f"⚠️  Ollama responded with status {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ Ollama not running            - Start Ollama before using the plugin")
        print("   Download from: https://ollama.com")
    except Exception as e:
        print(f"⚠️  Could not check Ollama: {e}")
    print()
    
    # Summary
    print("=" * 60)
    if all_ok:
        print("✅ All critical requirements satisfied!")
        print("   Ready to use CosmicTagger.")
    else:
        print("❌ Some requirements missing.")
        print("   Install with: pip install -r backend/requirements.txt")
    print("=" * 60)
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
