---
id: blog_mcp_budget_cover_spec
title: Cover Image Spec — MCP Budgeted Tool Use Blog
role: dev_rel
status: ready
created_at: 2026-04-11
updated_at: 2026-04-11
author: AI-DevRel
---

# Cover Image Specification

**File:** `cover-mcp-budgeted-tool-use.png`  
**Hosted URL (after upload):** `https://synapsenetwork.io/assets/blog/cover-mcp-budgeted-tool-use.png`

## Dimensions

| Platform  | Required Size   | Safe Zone         |
|-----------|----------------|-------------------|
| Substack  | 1456 × 816 px  | Keep key content within center 1200 × 600 px |
| Hashnode  | 1600 × 840 px  | Keep key content within center 1400 × 720 px |
| Dev.to    | 1000 × 420 px  | Keep key content within center 900 × 380 px  |

> **Recommended master size:** 1600 × 840 px. Crop/export variants per platform from the master.

## Visual Concept

**Theme:** Dark-mode cyberpunk / developer aesthetic  
**Background:** Deep dark `#0D1117` (GitHub-style) with subtle circuit board or node-graph overlay  
**Accent colors:** Synapse purple `#7C3AED` and electric teal `#06B6D4`

### Key Visual Elements

1. **Center:** Simple code block floating in space:
   ```
   wallet = AgentWallet.connect(budget=5.00)
   agent = CodeAgent(tools=[wallet.mcp_tool(...)])
   agent.run(...)
   ```
2. **Left side:** Abstract "broke robot" icon (agent with empty wallet / zero balance indicator)
3. **Right side:** Abstract "happy API" icon (data flow, money symbol, green checkmark)
4. **Connecting element:** Arrow / data stream flowing left-to-right with `0.01 USDC` label mid-stream
5. **Bottom-right watermark:** Synapse Network logo (small, low opacity)

### Typography

- **Headline (optional overlay):** "AI Agents Can Now Pay for APIs"
  - Font: JetBrains Mono or Space Grotesk Bold
  - Color: White `#FFFFFF`
  - Size: ~72px on master canvas

### Alt Text (all platforms)

> "AI agent connecting to APIs through Synapse Network settlement layer — code snippet showing AgentWallet with $5.00 budget"

## Export Checklist

- [ ] PNG export, sRGB color space
- [ ] File size < 500 KB (compress with `pngquant` or TinyPNG)
- [ ] Upload to `synapsenetwork.io/assets/blog/` CDN
- [ ] Verify URL accessible before publishing any platform post
- [ ] Substack: upload directly via editor (not URL)
- [ ] Hashnode: paste CDN URL in "Cover Image" field
- [ ] Dev.to: paste CDN URL in `cover_image:` front matter field
