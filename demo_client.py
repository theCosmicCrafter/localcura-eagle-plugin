import requests
import sys
import json
import os


def process_image(image_path, api_url="http://localhost:8000/process"):
    if not os.path.exists(image_path):
        print(f"Error: File not found at {image_path}")
        return

    print(f"Sending {image_path} to LocalCura...")
    try:
        with open(image_path, "rb") as f:
            files = {"file": f}
            response = requests.post(api_url, files=files)

        if response.status_code == 200:
            print("\n--- Analysis Result ---")
            print(json.dumps(response.json(), indent=2))
        else:
            print(f"Error: Server returned {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Failed to connect to server: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        img_path = sys.argv[1]
    else:
        img_path = input("Enter path to image file: ").strip().strip('"')

    process_image(img_path)
