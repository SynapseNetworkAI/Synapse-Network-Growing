---
name: social-distribution-content-pack
description: Platform contracts for turning one canonical article into human-gated social distribution drafts.
metadata:
  version: 1.0.0
---

# Social Distribution Content Pack

Use this playbook when a source content task is approved for `/publishing` distribution.

## Generation Order

1. Generate or reuse `source_plan`.
2. Generate `canonical_article` as the long-form source of truth.
3. Generate one `platform_draft` per selected channel.
4. Require human review before any external publish or manual live backfill.

## Platform Contracts

| Platform | Format | Target |
| --- | --- | --- |
| X | `x_long_post`, `single_x_post`, or `x_thread` | English-only for the official account. Default deep technical articles and founder stories to Premium long posts under 4000 chars; use single/thread only for short updates or explicit thread requests. |
| Hacker News | `hn_submission` | Plain title, canonical/source URL, optional first comment draft only. |
| Reddit | `discussion_post` | Title <= 300 chars; body around 1200-3000 chars, community discussion style. |
| V2EX | `discussion_post` | Chinese title around 20-60 chars; body around 800-2000 Chinese chars. |
| DEV | `long_article` | Complete Markdown article, 1200-2500 words, headings, examples, conclusion. |
| Hashnode | `long_article` | Complete Markdown article, 1200-2500 words, canonical URL checklist. |

## Dynamic X Variant

Return only one X shape. Default to Premium long post for substantial content:

```json
{
  "x_format": "long_post",
  "post_text": "...",
  "rationale": "..."
}
```

Legacy short update/thread shape:

```json
{
  "x_format": "single",
  "tweets": ["..."],
  "rationale": "..."
}
```

Use `single` only for simple short updates. Use `thread` only when the operator explicitly asks for a thread. Long posts must be density-driven, max 4000 chars, and must not pad, repeat, or invent details.
For long posts, do not enforce a minimum length. Set `platform_body` and `post_text` to the same final X text, stop as soon as the useful content is complete, and rewrite shorter before returning JSON if the draft is over 3900 chars.
