#!/usr/bin/env python3
"""
Daily Instagram Publisher for the Principle of Correspondence Series.

Selects the next unpublished quote post from posts.json, verifies the quote image,
builds the Instagram caption (description + 5 hashtags), and publishes it via
the Instagram Graph API.
"""

import argparse
import datetime
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
POSTS_FILE = BASE_DIR / "posts.json"
ENV_FILE = BASE_DIR / ".env"


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def format_caption(post: dict) -> str:
    hashtags_str = " ".join(post.get("hashtags", []))
    return f'{post["description"]}\n\n{hashtags_str}'


def publish_to_instagram_graph_api(
    ig_user_id: str,
    access_token: str,
    image_url: str,
    caption: str,
) -> str:
    """Create a media container and publish it via the Instagram Graph API."""
    base_api = f"https://graph.facebook.com/v21.0/{ig_user_id}"

    # Step 1: Create media container
    container_data = urllib.parse.urlencode(
        {
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        }
    ).encode("utf-8")
    req = urllib.request.Request(f"{base_api}/media", data=container_data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        container_payload = json.loads(resp.read().decode("utf-8"))

    creation_id = container_payload.get("id")
    if not creation_id:
        raise RuntimeError(f"Failed to create media container: {container_payload}")

    # Step 2: Publish media container
    publish_data = urllib.parse.urlencode(
        {
            "creation_id": creation_id,
            "access_token": access_token,
        }
    ).encode("utf-8")
    pub_req = urllib.request.Request(
        f"{base_api}/media_publish", data=publish_data, method="POST"
    )
    with urllib.request.urlopen(pub_req, timeout=30) as resp:
        publish_payload = json.loads(resp.read().decode("utf-8"))

    media_id = publish_payload.get("id")
    if not media_id:
        raise RuntimeError(f"Failed to publish media container: {publish_payload}")
    return str(media_id)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish the next Principle of Correspondence post to Instagram."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the next post without calling the Instagram Graph API.",
    )
    args = parser.parse_args()

    load_env(ENV_FILE)

    if not POSTS_FILE.exists():
        print(f"Error: {POSTS_FILE} not found.", file=sys.stderr)
        return 1

    posts = json.loads(POSTS_FILE.read_text(encoding="utf-8"))
    next_post = next((p for p in posts if not p.get("published")), None)

    if not next_post:
        print("All posts in posts.json have already been published!")
        return 0

    image_file = BASE_DIR / next_post["image_path"]
    if not image_file.exists():
        print(f"Error: Image file {image_file} does not exist.", file=sys.stderr)
        return 1

    caption = format_caption(next_post)
    print(f"=== Selected Post #{next_post['id']}: {next_post['concept']} ===")
    print(f"Quote on Image : {next_post['quote']}")
    print(f"Image Path     : {image_file}")
    print(f"Caption        :\n{caption}\n")

    if args.dry_run:
        print("Dry run complete. Post is ready for publishing.")
        return 0

    ig_user_id = os.environ.get("IG_USER_ID", "").strip()
    access_token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    image_base_url = os.environ.get(
        "IG_IMAGE_BASE_URL",
        "https://raw.githubusercontent.com/Locustv2/hermetic-instagram-automation/main",
    ).strip()
    image_url = next_post.get("image_url") or (
        f"{image_base_url.rstrip('/')}/{next_post['image_path']}"
        if image_base_url
        else ""
    )

    if not ig_user_id or not access_token or not image_url:
        print(
            "Instagram Graph API credentials are not yet configured in .env.\n"
            "Required environment variables in /Users/locustv2/Documents/antigravity/elegant-bose/.env:\n"
            "  IG_USER_ID=<your-instagram-business-account-id>\n"
            "  IG_ACCESS_TOKEN=<your-instagram-graph-api-access-token>\n"
            "  IG_IMAGE_BASE_URL=<public-https-base-url-hosting-the-images-folder>",
            file=sys.stderr,
        )
        return 2

    media_id = publish_to_instagram_graph_api(
        ig_user_id=ig_user_id,
        access_token=access_token,
        image_url=image_url,
        caption=caption,
    )
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    next_post["published"] = True
    next_post["published_at"] = now_iso
    next_post["instagram_media_id"] = media_id
    POSTS_FILE.write_text(json.dumps(posts, indent=2) + "\n", encoding="utf-8")
    print(f"Successfully published Post #{next_post['id']} (Media ID: {media_id}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
