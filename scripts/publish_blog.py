#!/usr/bin/env python3
"""
publish_blog.py — Multi-platform blog publishing automation for Synapse Network.

Supports Dev.to (REST API) and Hashnode (GraphQL API).
Substack has no public API — follow the manual checklist in publish-manifest.md.

Usage:
    export DEVTO_API_KEY=your_key_here
    export HASHNODE_TOKEN=your_hashnode_pat
    export HASHNODE_PUBLICATION_ID=your_publication_id
    export CANONICAL_URL=https://synapsenetwork.substack.com/p/how-to-let-ai-agents-discover-and-pay-for-apis

    python3 scripts/publish_blog.py --platform devto [--dry-run]
    python3 scripts/publish_blog.py --platform hashnode [--dry-run]
    python3 scripts/publish_blog.py --platform all [--dry-run]

Requirements:
    pip install requests pyyaml

Post-publish:
    URLs are automatically recorded to:
    roles/dev_rel/outputs/blog-published-urls.md

Finding your Hashnode Publication ID:
    Dashboard → Your Blog → Settings → scroll to "Publication ID"
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import requests
    import yaml
except ImportError:
    print("Missing dependencies. Run: pip install requests pyyaml")
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent
DEVTO_CONTENT = REPO_ROOT / "roles/dev_rel/outputs/blog-publish-mcp/devto.md"
PUBLISHED_URLS = REPO_ROOT / "roles/dev_rel/outputs/blog-published-urls.md"
DEVTO_API = "https://dev.to/api/articles"


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Split YAML frontmatter from markdown body."""
    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not match:
        return {}, content
    meta = yaml.safe_load(match.group(1))
    body = content[match.end():]
    # Strip HTML comment blocks used as platform notes
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip()
    return meta, body


def publish_devto(dry_run: bool = False) -> str:
    api_key = os.environ.get("DEVTO_API_KEY")
    if not api_key:
        print("ERROR: DEVTO_API_KEY environment variable not set.")
        print("Get your key at: https://dev.to/settings/extensions")
        sys.exit(1)

    canonical_env = os.environ.get("CANONICAL_URL")
    raw = DEVTO_CONTENT.read_text()
    meta, body = parse_frontmatter(raw)

    canonical_url = canonical_env or meta.get("canonical_url", "")
    if not canonical_url or "PENDING" in canonical_url:
        print("ERROR: canonical_url is not set.")
        print("Publish to Substack first, then set CANONICAL_URL env var.")
        sys.exit(1)

    # Dev.to tags: max 4, lowercase, no spaces
    tags = [t.strip().lower().replace(" ", "") for t in str(meta.get("tags", "")).split(",")][:4]

    payload = {
        "article": {
            "title": meta.get("title", ""),
            "body_markdown": body,
            "published": False,  # creates as draft — human reviews before publishing live
            "canonical_url": canonical_url,
            "description": meta.get("description", ""),
            "tags": tags,
            "cover_image": meta.get("cover_image", ""),
        }
    }

    print(f"Title:         {payload['article']['title']}")
    print(f"Canonical URL: {canonical_url}")
    print(f"Tags:          {tags}")
    print(f"Published:     draft (set to true manually after review)")
    print()

    if dry_run:
        print("[DRY RUN] Would POST to dev.to API:")
        print(json.dumps(payload, indent=2))
        return "https://dev.to/synapsenetwork/dry-run-no-post-created"

    resp = requests.post(
        DEVTO_API,
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        print(f"ERROR: Dev.to API returned {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    data = resp.json()
    url = data.get("url", "")
    post_id = data.get("id", "")
    print(f"✅ Draft created on Dev.to")
    print(f"   ID:  {post_id}")
    print(f"   URL: {url}")
    print()
    print("Next steps:")
    print("  1. Review the draft at the URL above")
    print("  2. Upload cover image (1000×420px) — see cover-image-spec.md")
    print(f"  3. Verify canonical_url → {canonical_url}")
    print("  4. Publish manually via dev.to dashboard")
    print(f"  5. Update PENDING in: {PUBLISHED_URLS.relative_to(REPO_ROOT)}")
    return url


def main():
    parser = argparse.ArgumentParser(description="Publish blog post to developer platforms")
    parser.add_argument(
        "--platform",
        choices=["devto"],
        required=True,
        help="Target platform (only 'devto' supports API automation)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload without making API calls",
    )
    args = parser.parse_args()

    if args.platform == "devto":
        url = publish_devto(dry_run=args.dry_run)
        if not args.dry_run:
            print()
            print("For Substack and Hashnode, follow the manual steps in:")
            print("  roles/dev_rel/outputs/blog-publish-mcp/publish-manifest.md")
    else:
        print(f"Platform '{args.platform}' not yet supported by this script.")
        print("See publish-manifest.md for manual publishing steps.")
        sys.exit(1)


if __name__ == "__main__":
    main()
