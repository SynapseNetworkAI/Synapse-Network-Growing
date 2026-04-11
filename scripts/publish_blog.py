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
PUBLISH_DIR = REPO_ROOT / "roles/dev_rel/outputs/blog-publish-mcp"
DEVTO_CONTENT = PUBLISH_DIR / "devto.md"
HASHNODE_CONTENT = PUBLISH_DIR / "hashnode.md"
PUBLISHED_URLS = REPO_ROOT / "roles/dev_rel/outputs/blog-published-urls.md"
DEVTO_API = "https://dev.to/api/articles"
HASHNODE_GQL = "https://gql.hashnode.com"


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
    if not dry_run and not api_key:
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
    print(f"  5. Update blog-published-urls.md with the live URL")
    return url


def publish_hashnode(dry_run: bool = False) -> str:
    """Publish to Hashnode via GraphQL API. Returns draft/post URL."""
    token = os.environ.get("HASHNODE_TOKEN")
    publication_id = os.environ.get("HASHNODE_PUBLICATION_ID")

    if not dry_run:
        if not token:
            print("ERROR: HASHNODE_TOKEN environment variable not set.")
            print("Get your Personal Access Token at: https://hashnode.com/settings/developer")
            sys.exit(1)
        if not publication_id:
            print("ERROR: HASHNODE_PUBLICATION_ID not set.")
            print("Find it: Hashnode Dashboard → Your Blog → Settings → Publication ID")
            sys.exit(1)

    canonical_env = os.environ.get("CANONICAL_URL")
    raw = HASHNODE_CONTENT.read_text()
    meta, body = parse_frontmatter(raw)

    canonical_url = canonical_env or meta.get("hashnode_canonical_url", "")
    if not canonical_url or "PENDING" in str(canonical_url):
        print("ERROR: hashnode_canonical_url / CANONICAL_URL is not set.")
        print("Publish to Substack first, then set CANONICAL_URL env var.")
        sys.exit(1)

    title = meta.get("title", "Untitled")
    subtitle = meta.get("hashnode_subtitle", "")
    cover_image = meta.get("cover_image_url", "")
    raw_tags = meta.get("hashnode_tags", [])
    tags = [{"slug": t, "name": t.replace("-", " ").title()} for t in raw_tags]

    print(f"Title:         {title}")
    print(f"Subtitle:      {subtitle}")
    print(f"Canonical URL: {canonical_url}")
    print(f"Tags:          {[t['slug'] for t in tags]}")
    print(f"Cover image:   {cover_image}")
    print()

    if dry_run:
        print("[DRY RUN] Would POST to Hashnode GraphQL API with publication ID: <HASHNODE_PUBLICATION_ID>")
        print(f"  title: {title!r}")
        print(f"  canonical: {canonical_url}")
        print(f"  tags: {[t['slug'] for t in tags]}")
        return "https://hashnode.com/draft/dry-run"

    mutation = """
    mutation PublishPost($input: PublishPostInput!) {
      publishPost(input: $input) {
        post {
          id
          url
          title
          publishedAt
        }
      }
    }
    """

    variables: dict = {
        "input": {
            "title": title,
            "subtitle": subtitle,
            "contentMarkdown": body,
            "publicationId": publication_id,
            "tags": tags,
            "originalArticleURL": canonical_url,
        }
    }
    if cover_image:
        variables["input"]["coverImageOptions"] = {"coverImageURL": cover_image}

    resp = requests.post(
        HASHNODE_GQL,
        headers={"Authorization": token, "Content-Type": "application/json"},
        json={"query": mutation, "variables": variables},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    errors = data.get("errors")
    if errors:
        print(f"ERROR: Hashnode GraphQL errors: {errors}")
        sys.exit(1)

    post = data["data"]["publishPost"]["post"]
    url = post["url"]
    print(f"✅ Published to Hashnode")
    print(f"   ID:  {post['id']}")
    print(f"   URL: {url}")
    print()
    print("Next steps:")
    print("  1. Upload cover image (1600×840px) via Hashnode editor — see cover-image-spec.md")
    print(f"  2. Verify 'Original Article URL' → {canonical_url}")
    print(f"  3. Update blog-published-urls.md with the live URL")
    return url


def update_url_registry(results: dict[str, str | None], dry_run: bool = False) -> None:
    """Write blog-published-urls.md with current platform URLs.

    In dry-run mode, skips writing to avoid overwriting real URLs with placeholders.
    """
    if dry_run:
        print(f"[DRY RUN] Skipping URL registry update (would write to {PUBLISHED_URLS.relative_to(REPO_ROOT)})")
        return

    substack_url = results.get(
        "substack",
        "https://synapsenetwork.substack.com/p/how-to-let-ai-agents-discover-and-pay-for-apis",
    )
    hashnode_url = results.get("hashnode") or "⏳ PENDING"
    devto_url = results.get("devto") or "⏳ PENDING"

    def status(url: str | None) -> str:
        return "✅" if url and "PENDING" not in url and "dry-run" not in url else "⏳"

    content = f"""---
id: blog-published-urls-mcp
title: Blog Published URLs — MCP + Budgeted Tool Use
role: dev_rel
status: {"published" if all(u and "PENDING" not in u for u in results.values()) else "partial"}
created_at: 2026-04-11
updated_at: 2026-04-11
author: AI-DevRel
source: roles/dev_rel/contents/blog_mcp_budgeted_tool_use.md
---

# Blog Published URLs: MCP + Budgeted Tool Use

> Source: `roles/dev_rel/contents/blog_mcp_budgeted_tool_use.md`  
> Canonical platform: **Substack** — all other platforms set `canonical_url` → Substack

## Platform URLs

| Platform | URL | Status | Tags |
|----------|-----|:------:|------|
| **Substack** | {substack_url} | {status(substack_url)} | Engineering section |
| **Dev.to** | {devto_url} | {status(devto_url)} | #ai #machinelearning #python #web3 |
| **Hashnode** | {hashnode_url} | {status(hashnode_url)} | #ai-agents #mcp #web3 #python #micropayments |

## Canonical URL

```
{substack_url}
```

Dev.to and Hashnode both set their `canonical_url` / "Original Article URL" to the Substack URL
above to prevent duplicate content penalties.

## Tags Used

| Platform | Tags |
|----------|------|
| Substack | Engineering section (no hashtags on Substack) |
| Dev.to | `ai`, `machinelearning`, `python`, `web3` |
| Hashnode | `ai-agents`, `mcp`, `web3`, `python`, `micropayments` |

## Cover Image

**Spec:** 1200×630 px minimum (see `roles/dev_rel/outputs/blog-publish-mcp/cover-image-spec.md`)

| Platform | Required Size | Upload Method |
|----------|:------------:|---------------|
| Substack | 1456×816 px | Upload via editor (no URL support) |
| Dev.to | 1000×420 px | `cover_image:` in frontmatter |
| Hashnode | 1600×840 px | Cover Image URL field in post settings |

## Post-Publish SEO Checklist

- [ ] All three platform URLs resolve correctly
- [ ] Dev.to `<link rel="canonical">` → Substack URL (verify in page source)
- [ ] Hashnode "Original Article URL" → Substack URL (verify in post settings)
- [ ] Cover image renders on all three platforms
- [ ] Code blocks are syntax-highlighted
- [ ] Links to Developer Console and GitHub are live
- [ ] Submit Substack canonical URL to Google Search Console for indexing

## Automation

Generated by `scripts/publish_blog.py`.

To re-run publishing:
```bash
export DEVTO_API_KEY=your_key
export HASHNODE_TOKEN=your_token
export HASHNODE_PUBLICATION_ID=your_pub_id
export CANONICAL_URL=https://synapsenetwork.substack.com/p/...

python3 scripts/publish_blog.py --platform devto
python3 scripts/publish_blog.py --platform hashnode
```

Substack must be published manually — see `roles/dev_rel/outputs/blog-publish-mcp/publish-manifest.md`.
"""

    PUBLISHED_URLS.write_text(content.lstrip())
    print(f"\n✅ URL registry written: {PUBLISHED_URLS.relative_to(REPO_ROOT)}")


def main():
    parser = argparse.ArgumentParser(description="Publish blog post to developer platforms")
    parser.add_argument(
        "--platform",
        choices=["devto", "hashnode", "all"],
        default="all",
        help="Target platform(s) to publish to",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload without making API calls",
    )
    args = parser.parse_args()

    results: dict[str, str | None] = {}

    if args.platform in ("devto", "all"):
        results["devto"] = publish_devto(dry_run=args.dry_run)

    if args.platform in ("hashnode", "all"):
        results["hashnode"] = publish_hashnode(dry_run=args.dry_run)

    if args.platform == "all":
        print("[substack] No public API — publish manually per publish-manifest.md")
        results["substack"] = (
            "https://synapsenetwork.substack.com/p/how-to-let-ai-agents-discover-and-pay-for-apis"
        )

    update_url_registry(results, dry_run=args.dry_run)

    if args.dry_run:
        print("\n✅ Dry run complete — no posts were published.")
    else:
        published = [p for p, u in results.items() if u and "PENDING" not in u and "dry-run" not in u]
        print(f"\n✅ Done. Published to: {', '.join(published) or 'none'}")


if __name__ == "__main__":
    main()
