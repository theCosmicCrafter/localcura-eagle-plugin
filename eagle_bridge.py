import requests
import logging
import time
from eagle_integration import EagleClient

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("eagle_bridge")

LOCALCURA_API = "http://localhost:8000/process"


class EagleBridge:
    def __init__(self):
        self.eagle = EagleClient()
        self.processed_count = 0

    def map_score_to_rating(self, score: float) -> int:
        """Map aesthetic score (0-10) to Eagle rating (1-5)."""
        if score >= 8.0:
            return 5
        if score >= 7.0:
            return 4
        if score >= 6.0:
            return 3
        if score >= 5.0:
            return 2
        if score >= 4.0:
            return 1
        return 0

    def process_item(self, item: dict):
        item_id = item.get("id")
        name = item.get("name")
        file_path = self.eagle.get_item_file_path(item_id)

        if not file_path:
            logger.warning(f"Skipping {name} (no file path found)")
            return

        logger.info(f"Processing: {name}...")

        # 1. Send to LocalCura API
        try:
            with open(file_path, "rb") as f:
                response = requests.post(LOCALCURA_API, files={"file": f}, timeout=120)

            if response.status_code != 200:
                logger.error(f"LocalCura failed for {name}: {response.text}")
                return

            result = response.json()
            if not result:  # skipped due to low score or error
                logger.info(f"Skipped {name} (low score or filtered)")
                return

        except Exception as e:
            logger.error(f"API Error for {name}: {e}")
            return

        # 2. Extract Data
        tags = result.get("tags", [])
        aesthetic_score = result.get("aesthetic", 0.0)
        analysis = result.get("analysis", {})

        # Add VLM subjects/styles to tags if available
        if isinstance(analysis, dict):
            if "subjects" in analysis:
                tags.extend(analysis["subjects"])
            if "visual_style" in analysis:
                tags.append(analysis["visual_style"])
            # Maybe add summary to comments? Eagle has a 'annotation' or 'comment' field?
            # API doesn't document 'comment' update easily in simple endpoint, skipping for now.

        # Deduplicate tags
        tags = list(set(tags))

        # 3. Update Eagle
        # 3. Update Eagle
        updates = {}

        # Tags from joytag
        if tags:
            updates["tags"] = list(set(tags))  # start with joytag tags if any

        # Merge VLM data
        if isinstance(analysis, dict):
            # 1. Description -> Annotation
            if "description" in analysis:
                updates["annotation"] = analysis["description"]

            # 2. Renaming
            if "suggested_name" in analysis and analysis["suggested_name"]:
                new_name = analysis["suggested_name"]
                if new_name != name:
                    updates["name"] = new_name
                    logger.info(f"Renaming '{name}' -> '{new_name}'")

            # 3. Custom Tags (with prefixes)
            # keys matched to photography_template
            tag_map = {
                "genre": "Genre",
                "lighting": "Lighting",
                "color_and_tone": "Color/Tone",
                "time_or_season": "Time/Season",
                "subjects": "Subject",
                "similar_artists": "Similar Artist",
            }

            current_tags = updates.get("tags", [])
            for key, prefix in tag_map.items():
                vals = analysis.get(key)
                if isinstance(vals, list):
                    for v in vals:
                        tag_str = f"{prefix}: {v}"
                        if tag_str not in current_tags:
                            current_tags.append(tag_str)

            updates["tags"] = current_tags

        # Update Rating
        rating = self.map_score_to_rating(aesthetic_score)
        if rating > 0:
            updates["star"] = rating

        # Apply updates
        if updates:
            self.eagle.update_item(item_id, updates)
            logger.info(f"Updated {name}: {list(updates.keys())}")

        self.processed_count += 1

    def run_batch(self, limit=10, process_all=False):
        """
        Run on recent items.
        process_all: If True, tries to paginate through everything (careful!)
        """
        logger.info("Connecting to Eagle...")
        info = self.eagle.get_info()
        if not info:
            logger.error("Eagle not found! Please open Eagle App.")
            return

        offset = 0
        batch_size = 10
        total_limit = limit if not process_all else 999999

        while offset < total_limit:
            items = self.eagle.get_items(limit=batch_size, offset=offset)
            if not items:
                break

            for item in items:
                # Optional: Skip if already tagged to save time?
                # current_tags = item.get("tags", [])
                # if current_tags and not process_all:
                #    continue

                self.process_item(item)

                if self.processed_count >= total_limit:
                    return

            offset += batch_size
            time.sleep(0.5)  # Be nice to API


if __name__ == "__main__":
    bridge = EagleBridge()
    # By default process 5 most recent items to test
    print("Starting Eagle Bridge...")
    print("Ensure LocalCura server is running on port 8000")
    bridge.run_batch(limit=5)
    print("Done.")
