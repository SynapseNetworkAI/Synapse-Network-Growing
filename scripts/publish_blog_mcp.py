#!/usr/bin/env python3
"""
Blog publishing script: MCP + Budgeted Tool Use
Publishes to Dev.to (REST API) and Hashnode (GraphQL API).
Substack has no public publishing API — follow the manual checklist in the manifest.

Usage:
    # Dry-run (prints request payload, does not publish)
    python3 scripts/publish_blog_mcp.py --dry-run

    # Publish to Dev.to only
    DEVTO_API_KEY=xxx python3 scripts/publish_blog_mcp.py --platform devto

    # Publish to Hashnode only
    HASHNODE_TOKEN=xxx HASHNODE_PUBLICATION_ID=xxx python3 scripts/publish_blog_mcp.py --platform hashnode

    # Publish to both (Substack must be done manually first to establish canonical URL)
    DEVTO_API_KEY=xxx HASHNODE_TOKEN=xxx HASHNODE_PUBLICATION_ID=xxx \
        python3 scripts/publish_blog_mcp.py --platform all

    # After publishing, record the resulting URLs
    python3 scripts/publish_blog_mcp.py --record \
        --substack-url "https://synapsenetwork.substack.com/p/..." \
        --devto-url "https://dev.to/synapsenetwork/..." \
        --hashnode-url "https://blog.synapse.network/..."

Environment variables:
    DEVTO_API_KEY           — Dev.to personal API key (Settings → Account → DEV Community API Keys)
    HASHNODE_TOKEN          — Hashnode personal access token (hashnode.com/settings/developer)
    HASHNODE_PUBLICATION_ID — Hashnode publication/blog ID (from your blog dashboard URL or API)
"""

import argparse
import json
import os
import re
import sys
import textwrap
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
DEVTO_FILE = REPO_ROOT / "roles/dev_rel/outputs/blog-publish-mcp/devto.md"
HASHNODE_FILE = REPO_ROOT / "roles/dev_rel/outputs/blog-publish-mcp/hashnode.md"
PUBLISHED_URLS_FILE = REPO_ROOT / "roles/dev_rel/outputs/blog-published-urls.md"

# ─── Canonical URL (Substack — must exist before publishing to other platforms) ─

CANONICAL_URL = "https://synapsenetwork.substack.com/p/how-to-let-ai-agents-discover-and-pay-for-apis"

# ─── Dev.to ───────────────────────────────────────────────────────────────────

DEVTO_API_BASE = "https://dev.to/api"

DEVTO_ARTICLE_PAYLOAD = {
    "article": {
        "title": "How to Let AI Agents Discover and Pay for APIs (MCP + Budgeted Tool Use)",
        "description": (
            "AI agents are smart but broke. Here's how Synapse Network + MCP lets them "
            "autonomously discover and pay for APIs with a $5 budget and 3 lines of Python."
        ),
        "tags": ["aiagents", "mcp", "web3", "developertools"],
        "canonical_url": CANONICAL_URL,
        "cover_image": "https://synapse.network/blog/mcp-budgeted-tool-use-cover.png",
        "published": False,  # set to True to publish immediately; False creates a draft
    }
}


def _read_body_from_md(path: Path) -> str:
    """Strip YAML frontmatter and HTML comments from a Markdown file, return body."""
    text = path.read_text(encoding="utf-8")
    # Remove YAML frontmatter (--- ... ---)
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)
    # Remove HTML comments (<!-- ... -->)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return text.strip()


def publish_devto(api_key: str, dry_run: bool = False) -> str | None:
    """Create a Dev.to article draft. Returns the published URL on success."""
    body_markdown = _read_body_from_md(DEVTO_FILE)
    payload = dict(DEVTO_ARTICLE_PAYLOAD)
    payload["article"] = dict(payload["article"])
    payload["article"]["body_markdown"] = body_markdown

    if dry_run:
        print("[DRY-RUN] Dev.to payload:")
        print(json.dumps(payload, indent=2)[:2000])
        return None

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{DEVTO_API_BASE}/articles",
        data=data,
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            url = result.get("url") or result.get("canonical_url") or ""
            print(f"✅ Dev.to draft created: {url}")
            return url
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"❌ Dev.to API error {e.code}: {body}", file=sys.stderr)
        return None


# ─── Hashnode ─────────────────────────────────────────────────────────────────

HASHNODE_API_URL = "https://gql.hashnode.com/"

# GraphQL mutation to create a draft post
HASHNODE_CREATE_DRAFT_MUTATION = """
mutation CreateDraft($input: CreateDraftInput!) {
  createDraft(input: $input) {
    draft {
      id
      title
      slug
    }
  }
}
"""


def publish_hashnode(token: str, publication_id: str, dry_run: bool = False) -> str | None:
    """Create a Hashnode draft post. Returns draft URL on success."""
    body_markdown = _read_body_from_md(HASHNODE_FILE)

    variables = {
        "input": {
            "title": "How to Let AI Agents Discover and Pay for APIs (MCP + Budgeted Tool Use)",
            "subtitle": (
                "AI agents are brilliant but broke. Give them a $5 budget and 3 lines of Python "
                "— they'll handle the rest."
            ),
            "publicationId": publication_id,
            "contentMarkdown": body_markdown,
            "tags": [
                {"name": "AI Agents", "slug": "ai-agents"},
                {"name": "MCP", "slug": "mcp"},
                {"name": "Web3", "slug": "web3"},
                {"name": "Python", "slug": "python"},
                {"name": "Micropayments", "slug": "micropayments"},
            ],
            "originalArticleURL": CANONICAL_URL,
            "coverImageOptions": {
                "coverImageURL": "https://synapse.network/blog/mcp-budgeted-tool-use-cover.png",
            },
        }
    }

    if dry_run:
        print("[DRY-RUN] Hashnode GraphQL variables:")
        print(json.dumps(variables, indent=2)[:2000])
        return None

    payload = json.dumps(
        {"query": HASHNODE_CREATE_DRAFT_MUTATION, "variables": variables}
    ).encode("utf-8")

    req = urllib.request.Request(
        HASHNODE_API_URL,
        data=payload,
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if "errors" in result:
                print(f"❌ Hashnode GraphQL error: {result['errors']}", file=sys.stderr)
                return None
            draft = result.get("data", {}).get("createDraft", {}).get("draft", {})
            draft_id = draft.get("id", "")
            slug = draft.get("slug", "")
            # Draft URL format: https://hashnode.com/draft/<id>
            url = f"https://hashnode.com/draft/{draft_id}" if draft_id else ""
            print(f"✅ Hashnode draft created: {url} (slug: {slug})")
            return url
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"❌ Hashnode API error {e.code}: {body}", file=sys.stderr)
        return None


# ─── URL recording ────────────────────────────────────────────────────────────

def record_urls(substack_url: str, devto_url: str, hashnode_url: str) -> None:
    """Update blog-published-urls.md with the real post URLs."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    content = textwrap.dedent(f"""\
        ---
        id: blog-published-urls-mcp
        title: Blog Published URLs — MCP + Budgeted Tool Use
        role: dev_rel
        status: published
        created_at: 2026-04-11
        updated_at: {now}
        author: AI-DevRel
        source_file: roles/dev_rel/contents/blog_mcp_budgeted_tool_use.md
        ---

        # Blog Published URLs: MCP + Budgeted Tool Use

        > Source: `roles/dev_rel/contents/blog_mcp_budgeted_tool_use.md`
        > Canonical: Substack (all other platforms point here)

        ## Platform URLs

        | Platform | URL | Status | Published At |
        |----------|-----|:------:|--------------|
        | **Substack** (canonical) | {substack_url or "_pending_"} | {"✅" if substack_url else "⏳"} | {now if substack_url else "—"} |
        | **Dev.to** | {devto_url or "_pending_"} | {"✅" if devto_url else "⏳"} | {now if devto_url else "—"} |
        | **Hashnode** | {hashnode_url or "_pending_"} | {"✅" if hashnode_url else "⏳"} | {now if hashnode_url else "—"} |

        ## Canonical Settings Verification

        | Platform | Canonical → Substack | `<link rel="canonical">` in HTML |
        |----------|:--------------------:|:--------------------------------:|
        | Substack | N/A (is the canonical) | N/A |
        | Dev.to | {"✅" if devto_url else "⏳ pending publish"} | {"✅" if devto_url else "⏳"} |
        | Hashnode | {"✅" if hashnode_url else "⏳ pending publish"} | {"✅" if hashnode_url else "⏳"} |

        ## Tags

        | Platform | Tags Applied |
        |----------|-------------|
        | Substack | Section: Engineering |
        | Dev.to | `#aiagents` `#mcp` `#web3` `#developertools` |
        | Hashnode | `ai-agents` `mcp` `web3` `python` `micropayments` |

        ## Cover Image

        - Spec: `roles/dev_rel/outputs/blog-publish-mcp/cover-image-spec.md`
        - CDN URL: `https://synapse.network/blog/mcp-budgeted-tool-use-cover.png`
        - Dimensions: 1600×840px master (platform crops applied per spec)

        ## Post-Publish Checklist

        - [ ] Dev.to: canonical URL verified in rendered `<head>`
        - [ ] Hashnode: "Original Article URL" set to Substack URL in post settings
        - [ ] All three posts link to [Developer Console](https://synapse.network/console) and [GitHub SDK](https://github.com/synapse-network/synapse-sdk)
        - [ ] Campaign manifest updated: `campaigns/*/manifest.md` → `[x] Blog: MCP Budgeted Tool Use`
        - [ ] Share links on X, HN, Discord after all three are live

        ## Update Instructions

        To update URLs after publishing, run:

        ```bash
        python3 scripts/publish_blog_mcp.py --record \\
            --substack-url "<url>" \\
            --devto-url "<url>" \\
            --hashnode-url "<url>"
        ```
    """)

    PUBLISHED_URLS_FILE.write_text(content, encoding="utf-8")
    print(f"✅ Recorded URLs to {PUBLISHED_URLS_FILE.relative_to(REPO_ROOT)}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish MCP blog post to Dev.to and Hashnode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--platform",
        choices=["devto", "hashnode", "all"],
        default="all",
        help="Which platform(s) to publish to (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print request payloads without making API calls",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Record post URLs to blog-published-urls.md (use after publishing)",
    )
    parser.add_argument("--substack-url", default="", help="Live Substack post URL")
    parser.add_argument("--devto-url", default="", help="Live Dev.to post URL")
    parser.add_argument("--hashnode-url", default="", help="Live Hashnode post URL")
    args = parser.parse_args()

    if args.record:
        record_urls(args.substack_url, args.devto_url, args.hashnode_url)
        return

    devto_api_key = os.environ.get("DEVTO_API_KEY", "")
    hashnode_token = os.environ.get("HASHNODE_TOKEN", "")
    hashnode_pub_id = os.environ.get("HASHNODE_PUBLICATION_ID", "")

    if not args.dry_run:
        if args.platform in ("devto", "all") and not devto_api_key:
            print(
                "❌ DEVTO_API_KEY not set. Export it or use --dry-run.",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.platform in ("hashnode", "all") and not (hashnode_token and hashnode_pub_id):
            print(
                "❌ HASHNODE_TOKEN and HASHNODE_PUBLICATION_ID must both be set. "
                "Export them or use --dry-run.",
                file=sys.stderr,
            )
            sys.exit(1)

    print("📋 Pre-flight check:")
    print(f"   Canonical URL : {CANONICAL_URL}")
    print(f"   Dev.to file   : {DEVTO_FILE.relative_to(REPO_ROOT)}")
    print(f"   Hashnode file : {HASHNODE_FILE.relative_to(REPO_ROOT)}")
    print(f"   Dry-run       : {args.dry_run}")
    print()

    devto_url, hashnode_url = "", ""

    if args.platform in ("devto", "all"):
        print("── Dev.to ──────────────────────────────")
        devto_url = publish_devto(devto_api_key, dry_run=args.dry_run) or ""

    if args.platform in ("hashnode", "all"):
        print("── Hashnode ────────────────────────────")
        hashnode_url = publish_hashnode(hashnode_token, hashnode_pub_id, dry_run=args.dry_run) or ""

    if not args.dry_run and (devto_url or hashnode_url):
        print()
        print("── Recording URLs ──────────────────────")
        record_urls(
            substack_url=args.substack_url,
            devto_url=devto_url,
            hashnode_url=hashnode_url,
        )

    if not args.dry_run:
        print()
        print("⚠️  Substack has no public publishing API.")
        print("   Publish manually using: roles/dev_rel/outputs/blog-publish-mcp/substack.md")
        print(f"   Then record the URL: python3 scripts/publish_blog_mcp.py --record --substack-url <url>")


if __name__ == "__main__":
    main()
