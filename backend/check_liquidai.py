import urllib.request
import json
import sys


def check_liquidai():
    url = "http://localhost:8101/health"  # Assuming mapped to localhost
    try:
        print(f"Checking {url}...")
        with urllib.request.urlopen(url, timeout=2) as response:
            print(f"Status: {response.status}")
            print(response.read().decode())
    except Exception as e:
        print(f"Failed to connect to localhost:8101: {e}")

    # Also try the container name if resolvable (unlikely on host, but good to note)
    print(
        "Note: 'http://liquidai-vision-mcp:8101' is only resolving inside Docker network."
    )


if __name__ == "__main__":
    check_liquidai()
