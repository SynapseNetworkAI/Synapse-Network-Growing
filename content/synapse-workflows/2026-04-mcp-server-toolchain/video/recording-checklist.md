---
title: "Recording checklist"
status: draft
created: 2026-04-30
---

# Recording Checklist

Use this checklist before any local screen recording.

## Environment

- [ ] Use a separate browser profile named `Synapse Demo`.
- [ ] Close personal email, messaging apps, calendars, and password managers.
- [ ] Disable desktop notifications.
- [ ] Use staging/testnet or local mock services only.
- [ ] Use placeholder credentials: `agt_xxx`, `REPLACE_ME`, `mock_secret`.
- [ ] Do not open GCP Secret Manager secret values.
- [ ] Do not open `.env*`, wallet, credential, certificate, or private key files.
- [ ] Do not show production dashboards or production balances.

## Terminal

- [ ] Clear terminal scrollback before recording.
- [ ] Confirm shell history will not reveal secrets.
- [ ] Use safe commands copied from docs or scripts.
- [ ] If a command needs a secret, show it with an environment variable placeholder only.
- [ ] Avoid printing full JWT, API key, HMAC secret, private key, or Secret Manager output.

## Browser

- [ ] Record a specific window, not the full screen.
- [ ] Hide bookmarks if they expose private tools or client names.
- [ ] Use public docs, staging dashboard, or local pages only.
- [ ] Confirm account avatars and usernames are acceptable to show.

## Raw Recording Review

- [ ] Watch the full raw recording before editing.
- [ ] Confirm the raw recording has microphone narration.
- [ ] Cut notification popups.
- [ ] Cut accidental secret/path exposure.
- [ ] Cut dead time and failed takes.
- [ ] Move raw files to `assets/recordings/raw/`.
- [ ] Move publishable edits to `assets/recordings/edited/`.
- [ ] Only publish files from `assets/recordings/edited/` or `assets/final/`.

## Final Artifact Review

- [ ] Export final MP4 to `assets/final/synapse-workflow-demo.mp4`.
- [ ] Generate English SRT at `assets/final/synapse-workflow.en.srt`.
- [ ] Confirm subtitles align with the voiceover.
- [ ] Optionally create a burned-subtitle version at `assets/final/synapse-workflow-demo-subtitled.mp4`.
- [ ] Backfill the final video URL in `distribution.md` after upload.

## Text Scan

Run before publishing subtitles, scripts, or descriptions:

```bash
cd /Users/cliff/workspace/agent/Synapse-Network-Growing/content/synapse-workflows/2026-04-mcp-server-toolchain
rg -i "private key|bearer|jwt|secret|token|api_key|password|mnemonic|gcloud secrets versions access|BEGIN .* KEY" .
```

Allowed matches:
Only checklist warnings and placeholder examples.
