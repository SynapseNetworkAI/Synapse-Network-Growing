---
id: review-blog-publish-req15
title: "Review Report — Req #15: Blog Multi-Platform Publish (MCP + Budgeted Tool Use)"
role: dev_rel
status: approved
created_at: 2026-04-11
updated_at: 2026-04-11
author: AI-DevRel-Reviewer
requirement: "[DevRel] 技术博客多平台发布 — Hashnode / Dev.to / Substack"
verdict: APPROVED (with fixes applied)
---

# Review Report: Req #15 — Blog Multi-Platform Publish

## Verdict: ✅ APPROVED (bugs fixed during review)

---

## Requirement Checklist

| Requirement Item | Status | Notes |
|-----------------|:------:|-------|
| Blog source `blog_mcp_budgeted_tool_use.md` exists and is ready | ✅ | Content is accurate, complete, and on-brand |
| Platform content files created (`devto.md`, `hashnode.md`, `substack.md`) | ✅ | All three present in `blog-publish-mcp/` |
| Tags: `#AIAgents #MCP #Web3 #DeveloperTools` | ✅ | Fixed in `publish_blog_mcp.py` and `publish_blog.py` (see Bugs Fixed) |
| Canonical URL all pointing to Substack | ✅ | Set correctly in `devto.md` and `hashnode.md` frontmatter |
| Cover image spec defined (1200×630px minimum) | ✅ | `cover-image-spec.md` defines per-platform sizes; master at 1600×840px |
| `blog-published-urls.md` created | ✅ | File exists with correct structure and pending placeholders |
| Publishing automation script (`publish_blog.py`) | ✅ | Reads frontmatter dynamically; dry-run verified |
| `--dry-run` mode works without credentials | ✅ | Bug was previously fixed by implementer |
| Publishing manifest created | ✅ | `publish-manifest.md` has complete step-by-step checklist |

---

## Files Reviewed

| File | Finding |
|------|---------|
| `roles/dev_rel/outputs/blog-publish-mcp/devto.md` | ✅ Correct tags, correct canonical URL in frontmatter |
| `roles/dev_rel/outputs/blog-publish-mcp/hashnode.md` | ✅ Correct tags, canonical URL set |
| `roles/dev_rel/outputs/blog-publish-mcp/substack.md` | ✅ Marked `canonical: true`, Substack-formatted |
| `roles/dev_rel/outputs/blog-publish-mcp/cover-image-spec.md` | ✅ All three platform sizes documented |
| `roles/dev_rel/outputs/blog-publish-mcp/publish-manifest.md` | ✅ Step-by-step checklist; publishing order correct (Substack → Dev.to → Hashnode) |
| `roles/dev_rel/outputs/blog-published-urls.md` | ✅ Correct tags, pending status, SEO checklist included |
| `scripts/publish_blog.py` | ✅ Fixed (see below) |
| `scripts/publish_blog_mcp.py` | ✅ Fixed (see below) |

---

## Bugs Fixed During Review

### Bug 1 — Wrong Dev.to tags in `publish_blog_mcp.py`

**File:** `scripts/publish_blog_mcp.py` line 66

**Problem:** `DEVTO_ARTICLE_PAYLOAD` hardcoded wrong tags `["ai", "python", "web3", "machinelearning"]` which did not match the requirement `#AIAgents #MCP #Web3 #DeveloperTools`.

**Fix:** Changed to `["aiagents", "mcp", "web3", "developertools"]`.

### Bug 2 — Wrong tags in `record_urls()` output template (`publish_blog_mcp.py`)

**File:** `scripts/publish_blog_mcp.py` `record_urls()` function

**Problem:** The generated `blog-published-urls.md` template showed `#ai #python #web3 #machinelearning` for Dev.to.

**Fix:** Changed to `` `#aiagents` `#mcp` `#web3` `#developertools` ``.

### Bug 3 — Wrong tags in `update_url_registry()` template (`publish_blog.py`)

**File:** `scripts/publish_blog.py` `update_url_registry()` function

**Problem:** Generated content hardcoded `#ai #machinelearning #python #web3` and `ai, machinelearning, python, web3` for Dev.to, which would overwrite the correct tags in `blog-published-urls.md` on a real run.

**Fix:** Changed to `#aiagents #mcp #web3 #developertools` and `aiagents, mcp, web3, developertools`.

---

## Dry-Run Verification

```
$ python3 scripts/publish_blog.py --platform all --dry-run

Tags: ['aiagents', 'mcp', 'web3', 'developertools']   ✅
Canonical URL: https://synapsenetwork.substack.com/p/how-to-let-ai-agents-discover-and-pay-for-apis  ✅
Published: draft   ✅

$ python3 scripts/publish_blog_mcp.py --dry-run

"tags": ["aiagents", "mcp", "web3", "developertools"]  ✅
```

Both scripts exit 0 in dry-run mode without credentials. ✅

---

## Content Quality Assessment

- **Hook:** Strong — "AI agents are smart but broke" immediately speaks to the ICP pain
- **Code example:** Correct Python syntax, 3 lines as promised, uses `smolagents` (realistic)
- **Under the Hood section:** Accurately describes Discovery → Lock → Execute → Settle flow
- **CTA:** Clear dual CTA (Developer Console + Provider apply)
- **Canonical strategy:** Substack as canonical is correct (highest subscriber conversion value)

---

## Remaining Manual Steps (Not blocking review)

The following must be completed by a human at publish time:

1. Create actual Synapse Network accounts on Substack, Dev.to, and Hashnode
2. Generate and upload the cover image per `cover-image-spec.md`
3. Publish Substack first to establish canonical URL
4. Run `python3 scripts/publish_blog.py --platform all` with real credentials
5. Update `blog-published-urls.md` pending placeholders with real URLs via `--record` flag
6. Verify `<link rel="canonical">` in rendered HTML on Dev.to and Hashnode

---

## Review Acceptance Check

| Check | Pass? |
|-------|:-----:|
| All required files present | ✅ |
| Tags match requirement (`#AIAgents #MCP #Web3 #DeveloperTools`) | ✅ |
| Canonical URLs all point to Substack | ✅ |
| Cover image spec defined | ✅ |
| `blog-published-urls.md` exists with correct structure | ✅ |
| Automation scripts work in dry-run | ✅ |
| No credential leaks or secrets committed | ✅ |
| Substack-only note documented (no public API) | ✅ |

**Result: APPROVED** ✅
