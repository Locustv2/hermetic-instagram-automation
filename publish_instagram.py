#!/usr/bin/env python3
"""
Daily Instagram Publisher for the Principle of Correspondence Series.

Selects the next unpublished quote post from posts.json, verifies the quote image,
builds the Instagram caption (description + 5 hashtags), and publishes it via
the Official Instagram Graph API.
"""

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
POSTS_FILE = BASE_DIR / "posts.json"
ENV_FILE = BASE_DIR / ".env"
DEFAULT_IMAGE_BASE_URL = (
    "https://raw.githubusercontent.com/Locustv2/hermetic-instagram-automation/main"
)


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


def api_get_json(url: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_ig_user_id(access_token: str) -> tuple[str, str]:
    """
    Auto-discover the Instagram Account ID and appropriate Graph API host
    ('https://graph.instagram.com/v21.0' or 'https://graph.facebook.com/v21.0')
    from the provided access token.
    """
    q = urllib.parse.urlencode({"access_token": access_token})

    # 1. Try Instagram API with Instagram Login (tokens typically start with IG...)
    try:
        ig_me = api_get_json(
            f"https://graph.instagram.com/v21.0/me?fields=id,user_id,username&{q}"
        )
        uid = ig_me.get("user_id") or ig_me.get("id")
        if uid:
            return str(uid), "https://graph.instagram.com/v21.0"
    except Exception:
        pass

    # 2. Try Facebook Graph API connected pages -> instagram_business_account
    try:
        fb_accounts = api_get_json(
            f"https://graph.facebook.com/v21.0/me/accounts?fields=id,name,instagram_business_account&{q}"
        )
        for page in fb_accounts.get("data", []):
            ig_acct = page.get("instagram_business_account")
            if ig_acct and ig_acct.get("id"):
                return str(ig_acct["id"]), "https://graph.facebook.com/v21.0"
    except Exception:
        pass

    raise RuntimeError(
        "Could not automatically discover IG_USER_ID from IG_ACCESS_TOKEN. "
        "Please set IG_USER_ID explicitly in .env or verify token permissions "
        "(instagram_basic / instagram_content_publish or instagram_business_content_publish)."
    )


def publish_to_instagram_graph_api(
    ig_user_id: str,
    access_token: str,
    image_url: str,
    caption: str,
    api_host: str = "https://graph.facebook.com/v21.0",
) -> str:
    """Create a media container and publish it via the Instagram Graph API."""
    base_api = f"{api_host.rstrip('/')}/{ig_user_id}"

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

    image_base_url = os.environ.get(
        "IG_IMAGE_BASE_URL", DEFAULT_IMAGE_BASE_URL
    ).strip() or DEFAULT_IMAGE_BASE_URL
    image_url = next_post.get("image_url") or (
        f"{image_base_url.rstrip('/')}/{next_post['image_path']}"
    )

    caption = format_caption(next_post)
    print(f"=== Selected Post #{next_post['id']}: {next_post['concept']} ===")
    print(f"Quote on Image : {next_post['quote']}")
    print(f"Local Image    : {image_file}")
    print(f"Public HTTPS   : {image_url}")
    print(f"Caption        :\n{caption}\n")

    if args.dry_run:
        print("Dry run complete. Post is ready for publishing.")
        return 0

    access_token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    ig_user_id = os.environ.get("IG_USER_ID", "").strip()

    if not access_token:
        print(
            "Instagram Graph API token is not set yet.\n"
            "Paste your token into /Users/locustv2/Documents/antigravity/elegant-bose/.env:\n"
            "  IG_ACCESS_TOKEN=<your-instagram-graph-api-access-token>\n"
            "  IG_USER_ID=<optional: auto-discovered if left blank>",
            file=sys.stderr,
        )
        return 2

    api_host = (
        "https://graph.instagram.com/v21.0"
        if access_token.startswith("IG")
        else "https://graph.facebook.com/v21.0"
    )
    if not ig_user_id:
        ig_user_id, api_host = resolve_ig_user_id(access_token)
        print(f"Auto-discovered IG_USER_ID: {ig_user_id} ({api_host})")

    media_id = publish_to_instagram_graph_api(
        ig_user_id=ig_user_id,
        access_token=access_token,
        image_url=image_url,
        caption=caption,
        api_host=api_host,
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
