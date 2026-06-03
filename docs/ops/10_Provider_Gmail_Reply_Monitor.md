---
id: provider_gmail_reply_monitor
title: Provider Gmail Reply Monitor
role: growth_lead
status: ready
created_at: 2026-06-02
updated_at: 2026-06-02
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing-agent-b
---

# Provider Gmail Reply Monitor

## Purpose

Monitor `cliff@synapse-network.ai` for replies to provider outreach and turn
matched provider replies into human-reviewed response drafts.

The monitor does not send email. It reads Gmail INBOX through IMAP, matches
messages against sent provider outreach in the Growth ledger, records the inbound
reply, and creates a `growth_outreach_messages(status=needs_review)` reply draft.

## Data Flow

```text
Gmail INBOX
-> provider_reply_monitor.py
-> match sent GrowthOutreachMessage(provider)
-> growth_provider_replies
-> GrowthOutreachEvent(reply_received)
-> GrowthOutreachMessage(provider_reply, needs_review)
-> /growth Provider Reply Inbox
-> operator review/send path
```

## Configuration

Use Gmail app-password credentials in ignored `.env` or secret manager:

```bash
GMAIL_IMAP_HOST=imap.gmail.com
GMAIL_IMAP_PORT=993
GMAIL_IMAP_USERNAME=cliff@synapse-network.ai
GMAIL_IMAP_APP_PASSWORD=<gmail app password>
```

If `GMAIL_IMAP_*` is unset, the monitor falls back to
`GMAIL_SMTP_USERNAME` and `GMAIL_SMTP_APP_PASSWORD`.

## Commands

Dry run:

```bash
python3 scripts/growth/provider_reply_monitor.py --days 14 --limit 50
```

Apply matched replies and create drafts:

```bash
python3 scripts/growth/provider_reply_monitor.py --apply --days 14 --limit 50
```

Continuous monitor mode:

```bash
python3 scripts/growth/provider_reply_monitor.py \
  --watch \
  --interval-seconds 900 \
  --apply \
  --days 14 \
  --limit 50
```

Each run appends structured history to
`server/logs/growth-provider-reply-monitor.jsonl` by default. Use
`--run-history-jsonl ""` only for throwaway local experiments.

Fixture mode for CI or local tests:

```bash
python3 scripts/growth/provider_reply_monitor.py \
  --fixture-json docs/archive/evidence/growth/provider-reply-fixture.json \
  --apply
```

## Safety Rules

1. Never auto-send provider replies.
2. Only match replies to `provider` leads with a `sent` outreach message.
3. Dedupe by Gmail `Message-ID` / mailbox message id.
4. Store body excerpts only; do not store credentials, cookies, API keys, or
   private attachments.
5. Classify `not interested` as a stop signal and surface it for operator
   review before any follow-up.
6. Generated replies must avoid guaranteed revenue, guaranteed traffic, or
   implied partnership claims.

## Operator Surface

Open `/growth`, select `Providers`, and review `Provider Reply Inbox`.

The panel shows the matched Gmail sender, received time, classification,
confidence score, inbound snippet, and the suggested reply body. The reply draft
stays in `needs_review` until an operator opens the lead and approves or sends it
through the existing human-gated outreach path.
