import requests
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("eagle_client")
logging.basicConfig(level=logging.INFO)


class EagleClient:
    """Client for interacting with the Eagle App API (localhost:41595)."""

    BASE_URL = "http://localhost:41595/api"

    def __init__(self, token: str = ""):
        self.token = token  # Eagle API might not need token for localhost, strictly speaking, but good to have placeholder

    def get_info(self) -> Dict[str, Any]:
        """Check if Eagle is running and get info."""
        try:
            resp = requests.get(f"{self.BASE_URL}/info")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to connect to Eagle: {e}")
            return {}

    def get_items(
        self, limit: int = 50, offset: int = 0, folders: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get a list of items from Eagle."""
        params = {"limit": limit, "offset": offset, "orderBy": "-createdAt"}
        if folders:
            params["folders"] = folders

        try:
            resp = requests.get(f"{self.BASE_URL}/item/list", params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except Exception as e:
            logger.error(f"Failed to get items: {e}")
            return []

    def get_item_file_path(self, item_id: str) -> Optional[str]:
        """Get the full local file path for an item."""
        try:
            resp = requests.get(f"{self.BASE_URL}/item/info", params={"id": item_id})
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("filePath")
        except Exception as e:
            logger.error(f"Failed to get item info for {item_id}: {e}")
            return None

    def update_item_tags(self, item_id: str, tags: List[str]) -> bool:
        """Add tags to an item."""
        payload = {"id": item_id, "tags": tags}
        try:
            resp = requests.post(f"{self.BASE_URL}/item/update", json=payload)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to update tags for {item_id}: {e}")
            return False

    def update_item_rating(self, item_id: str, rating: int) -> bool:
        """Update star rating (0-5)."""
        payload = {"id": item_id, "star": rating}
        try:
            resp = requests.post(f"{self.BASE_URL}/item/update", json=payload)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to update rating for {item_id}: {e}")

    def update_item(self, item_id: str, data: Dict[str, Any]) -> bool:
        """Generic update for an item (tags, name, annotation, etc)."""
        payload = {"id": item_id, **data}
        try:
            resp = requests.post(f"{self.BASE_URL}/item/update", json=payload)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to update item {item_id}: {e}")
            return False


if __name__ == "__main__":
    client = EagleClient()
    info = client.get_info()
    if info:
        print(f"Connected to Eagle {info.get('data', {}).get('version', 'unknown')}")
        items = client.get_items(limit=5)
        print(f"Found {len(items)} items.")
        if items:
            first = items[0]
            print(f"Sample Item: {first.get('name')} ({first.get('id')})")
            path = client.get_item_file_path(first.get("id"))
            print(f"Local Path: {path}")
    else:
        print("Could not connect to Eagle. Is it running?")
