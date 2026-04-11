#!/usr/bin/env python3
"""
blog_publish_record.py — Record published blog URLs into blog-published-urls.md

Usage:
    python3 scripts/blog_publish_record.py --platform substack --url "https://..."
    python3 scripts/blog_publish_record.py --platform devto    --url "https://..."
    python3 scripts/blog_publish_record.py --platform hashnode --url "https://..."
    python3 scripts/blog_publish_record.py --status            # show current status
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

URLS_FILE = Path("roles/dev_rel/outputs/blog-published-urls.md")
PLATFORMS = ("substack", "devto", "hashnode")

PLATFORM_LABELS = {
    "substack": "Substack",
    "devto": "Dev.to",
    "hashnode": "Hashnode",
}

PLATFORM_CANONICAL = {
    "substack": "✅ Is the canonical",
    "devto": "✅ Points to Substack",
    "hashnode": "✅ Points to Substack",
}


def read_file() -> str:
    if not URLS_FILE.exists():
        sys.exit(f"ERROR: {URLS_FILE} not found. Run from project root.")
    return URLS_FILE.read_text(encoding="utf-8")


def write_file(content: str) -> None:
    URLS_FILE.write_text(content, encoding="utf-8")


def show_status(content: str) -> None:
    """Print current platform publish status."""
    print("\n📋 Blog Publish Status — MCP + Budgeted Tool Use\n")
    for platform, label in PLATFORM_LABELS.items():
        # Match the entire row for this platform
        pattern = rf"\| \*\*{re.escape(label)}\*\* \| ([^|]+) \| ([^|]+) \|"
        match = re.search(pattern, content)
        if match:
            status_cell = match.group(1).strip()
            url_cell = match.group(2).strip()
            if "PENDING" in url_cell or "⏳" in status_cell:
                print(f"  ⏳ {label:<12} — not yet published")
            else:
                print(f"  ✅ {label:<12} — {url_cell}")
        else:
            print(f"  ❓ {label:<12} — row not found in file")
    print()


def record_url(content: str, platform: str, url: str) -> str:
    """Replace PENDING cell for the given platform with the real URL."""
    label = PLATFORM_LABELS[platform]
    today = date.today().isoformat()

    # Match the table row for this platform and replace URL + status + date
    pattern = (
        rf"(\| \*\*{re.escape(label)}\*\* \| )"
        rf"⏳ Pending"
        rf"( \| )"
        rf"`PENDING[^`]*`"
        rf"( \| {re.escape(PLATFORM_CANONICAL[platform])} \| )"
        rf"— \|"
    )
    replacement = (
        rf"\g<1>✅ Published\g<2>{url}\g<3>{today} |"
    )

    new_content, count = re.subn(pattern, replacement, content)
    if count == 0:
        # Try simpler pattern in case the row was already partially updated
        simple_pattern = (
            rf"(\| \*\*{re.escape(label)}\*\*[^\n]+\| )"
            rf"`PENDING[^`]*`"
            rf"([^\n]+\|)"
        )
        new_content, count = re.subn(simple_pattern, rf"\g<1>{url}\g<2>", content)

    if count == 0:
        print(f"WARNING: Could not auto-replace row for {label}.")
        print(f"Please manually update {URLS_FILE} with: {url}")
        return content

    # Update `updated_at` in frontmatter
    new_content = re.sub(
        r"^(updated_at: )\d{4}-\d{2}-\d{2}",
        rf"\g<1>{today}",
        new_content,
        count=1,
        flags=re.MULTILINE,
    )

    # If all platforms are published, flip status to 'published'
    if "PENDING" not in new_content and "⏳ Pending" not in new_content:
        new_content = re.sub(
            r"^(status: )draft",
            r"\g<1>published",
            new_content,
            count=1,
            flags=re.MULTILINE,
        )
        print("🎉 All platforms published! Status updated to 'published'.")

    return new_content


def main() -> None:
    parser = argparse.ArgumentParser(description="Record blog publish URLs")
    parser.add_argument(
        "--platform",
        choices=PLATFORMS,
        help="Platform to record URL for",
    )
    parser.add_argument("--url", help="Published post URL")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current publish status",
    )
    args = parser.parse_args()

    content = read_file()

    if args.status or (not args.platform and not args.url):
        show_status(content)
        return

    if not args.platform or not args.url:
        parser.error("--platform and --url are both required when recording a URL")

    if not args.url.startswith("http"):
        sys.exit("ERROR: URL must start with http:// or https://")

    label = PLATFORM_LABELS[args.platform]
    print(f"Recording {label} URL: {args.url}")

    updated = record_url(content, args.platform, args.url)
    write_file(updated)
    print(f"✅ Updated {URLS_FILE}")
    print()
    show_status(updated)


if __name__ == "__main__":
    main()
