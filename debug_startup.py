import sys
import os

with open("debug_log.txt", "w") as f:
    f.write("Starting debug\n")
    try:
        import llama_cpp

        f.write("llama_cpp imported\n")
        from backend.localcura import create_app

        f.write("localcura imported\n")
        app = create_app()
        f.write("app created\n")
    except Exception as e:
        f.write(f"Error: {e}\n")
