# Social Publishing Principles

Load this when touching `/publishing`, social distribution, official X account, content generation, trend radar, replies, reposts, metrics, platform API publishing, or social credentials.

## Human-Gated Official Communication

1. Public platform speech is representational communication. Agent may draft, edit, and risk-check; it must not publish, delete, or modify official-account content by itself.
2. Publishing to X, deleting X posts, and social credential changes require Human Gate or explicit operator click.
3. Social Publishing default view is human-review first: operator enters goal/prompt, Agent generates policy-checked title/body/image prompt, operator reviews and confirms.
4. Drafts blocked by policy or failed media generation cannot show external publish action.
5. Raw prompt, raw agent output, secret refs, and API payloads belong in Debug details.
6. New, edit, view, publish confirmation, and trend detail use centered Modal/Dialog with dark blocking overlay. Do not use Drawer, Slide-out, Offcanvas, Side Panel, or right-side detail rail.

## Content Generation

1. Social copy generation uses dedicated `SOCIAL_CONTENT_LLM_PROVIDER` / `SOCIAL_CONTENT_LLM_MODEL`, not Planner Sweep, acceptance matrix, or engineering execution prompts.
2. Local verified default is Codex + `gpt-5.4`; `gpt-5-codex` is not the default for Social Content in the current account.
3. OpenAI, Claude, and Copilot require explicit valid key/quota/OAuth. Provider unavailable, non-JSON output, missing fields, prompt-copying, local path/secret/workflow leak, or high-risk financial promise fails closed.
4. Context must include `.agents/product-marketing-context.md` and `.agents/skills/social-content/SKILL.md`.
5. Staging, launch, and product update prompts may use bounded `launch-strategy` guidance.
6. Agent Content Pack starts from structured JSON and resolved source context. Minimal code-fence cleanup is allowed; YAML/Markdown-table fallback is not.
7. Missing P0 `@synapse-context:*` tags fail closed with `insufficient_source_context`.
8. Generated output must not contain local paths, internal instructions, workflow JSON, acceptance matrix, secrets, or unreviewed financial commitments.
9. X Premium long-post generation is information-density driven: `MAX_LENGTH=4000`, no minimum length, and no padding. If useful content ends at 800 characters, stop there.

## Platform And Media Rules

1. Do not force 280-character limits in application layer. Show `character_count` and let real platform API response define publish failure.
2. Default X content is substantial operator content with hook, explanation, product value, and credible detail. Short content only when operator requests it or source material is too thin.
3. Image generation is separate provider step from `image_prompt`.
4. Single image is the default maximum for v1 social publishing.
5. Image prompts must not contain local path, secret, workflow JSON, internal deployment detail, or high-risk financial promise.
6. X media upload failure blocks publishing and records failure; do not silently downgrade to text-only.
7. If posting with image, upload media first and create X Post with `media_ids`; save external post id, media id, errors, and events.
8. X OAuth2 `access_token` is never persisted in DB or frontend state. Client id and client secret may stay in Secret Manager; the official-account refresh token may live in equivalent secret storage such as the encrypted local Postgres `local_secret_versions` table. Create short-lived access tokens only in publish request memory.
9. Never expose X API token, Authorization header, or raw API payload to frontend or logs.
10. Social Publishing does not automate password login, auto comments, voting, likes, follows, CAPTCHA bypass, unreviewed delete, video/GIF, multi-image, or cross-platform mass publish.
11. Platforms without a stable official publishing API use browser-assisted publishing only: the system may check status, open the platform, copy or prefill a reviewed draft, and then stop before the final submit. Private page endpoints are not a default API surface.
12. Account readiness is a computed preflight (`official_api`, `browser_assisted`, `manual_only`, or `blocked`) rather than a publish decision. The final public action still requires the platform-specific Human Gate.

## Social Ops Center

1. Organize operations as `Campaign Goal -> Content Ideas -> Draft Queue -> Risk Gate -> Human Review -> Publish/Reply/Repost -> Observe Metrics`.
2. X social recurring workflow keys use `x_social_*` prefix.
3. X daily content planner is low-risk inventory refill. Same operator-local day target is three unpublished human-reviewed drafts.
4. Existing active inventory (`generating`, `needs_review`, `approved`) counts toward target; `published`, `rejected`, and `failed` do not.
5. Inventory refill stops on any generation failure.
6. `generating` beyond timeout becomes `failed` and no longer counts.
7. Product change signals for daily planner must be public-safe and filter local paths, secrets, branch noise, workflow JSON, and raw stack traces.
8. X Social Sweep Scheduler can trigger only named `x_social_*` draft/read-only workflows. It is not a generic cron or external-platform executor.
9. New platforms require explicit name, Human Gate, and observability.

## Trends, Reposts, Replies, And Metrics

1. Trend radar, watchlist, replies, repost candidates, and metrics are read-only or draft-only decision inputs unless operator explicitly publishes.
2. Trend Radar v1 prioritizes real Watchlist timeline data over broad web search.
3. Watchlist accounts have sync throttle and cached `x_user_id`.
4. X read budget exhaustion, rate limit, auth failure, or permission issue writes diagnostic; do not retry aggressively or fake local seed as real trend.
5. Trend results show `source_platform=x`, author, source URL, collection time, and engagement summary for real X data.
6. Local trend seeds are inspiration only and must disable quote/repost action.
7. Repost/quote candidate needs real `source_url` and additional Synapse angle; mere agreement is not publishable.
8. `/publishing/trends` can search stored trend items but must not trigger fetch, reply, repost, or publish.
9. Reply candidates enter `social_reply_items` human review queue.
10. Reply generation must be value-add: positive, relevant, and substantive; no `Great point`, hard-sell link, or engagement bait.
11. No deterministic template fallback may impersonate unavailable reply Agent.
12. Each reply candidate can be publicly posted at most once and must bind `in_reply_to_tweet_id`.
13. Metrics observer is read-only. Missing permission writes diagnostic and must not fake effect data.
14. Manual X metrics entry is allowed after Human Gate publishing: views, profile visits, replies, bookmarks, follows, posted time, and format kind are operator-entered evidence, not automated scraping.
