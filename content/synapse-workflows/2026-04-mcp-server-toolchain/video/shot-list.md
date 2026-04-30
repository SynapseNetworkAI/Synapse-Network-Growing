---
title: "Video shot list"
status: draft
created: 2026-04-30
---

# Video Shot List

Working title:
`How I Build MCP Servers with Claude Code, Apidog, and SynapseNetwork`

Target length:
6-8 minutes.

Recording style:
Segmented local recording. Record one window at a time. Use staging/testnet and mock credentials only.

## Shots

| # | Duration | Shot | What to Show | Risk Notes |
| --- | ---: | --- | --- | --- |
| 1 | 30s | Opening architecture map | Workspace folders: Synapse-Network, Provider, SDK, Growing, cliff-mind. | Avoid full personal path if possible. |
| 2 | 60s | Claude Code / Codex workflow | Search existing provider patterns, inspect tests, show smallest gate. | Do not show hidden env files. |
| 3 | 60s | MCP/provider endpoint contract | Provider endpoint shape and gateway_signed boundary. | Use mock headers; no real HMAC secret. |
| 4 | 60s | Apidog API debugging | Inspect request/response/status for Gateway or Provider. | Use mock or staging-safe request. |
| 5 | 90s | SDK E2E proof | Show provider onboarding -> discovery -> invoke -> receipt commands. | Mask agent key and owner key. |
| 6 | 60s | Local vs staging separation | Show local script and staging script names, not secret values. | Do not open Secret Manager values. |
| 7 | 60s | Quality gates | Show source API shape, coverage, maintainability gates passing. | No sensitive logs. |
| 8 | 45s | Publishing loop | Show `/publishing` queue with draft content. | Do not show personal social tokens/accounts beyond public handle. |
| 9 | 30s | Close | Summarize: debug loop + staging proof + SDK E2E + publishing loop. | None. |

## B-roll Ideas

- Terminal running local E2E with placeholders.
- Browser on staging docs or marketplace page.
- Apidog request collection with safe sample payload.
- Ops console publishing draft list.
- Git content folder at `Synapse-Network-Growing/content/synapse-workflows`.

## Visual Cues

- Use black-background terminal.
- Keep font size large enough for mobile viewers.
- Highlight only one command or concept per shot.
- Prefer zoomed window recording over full desktop.
