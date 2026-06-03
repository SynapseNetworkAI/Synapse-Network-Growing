---
id: provider_outreach_runbook
title: Provider Outreach Runbook
role: growth_lead
status: ready
created_at: 2026-06-02
updated_at: 2026-06-02
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing-agent-b
---

# Provider Outreach Runbook

## Goal

Find API and data-service providers that can register service interfaces on
Synapse Network, then send a concise operator-approved introduction email from
`cliff@synapse-network.ai`.

## Batch Strategy

1. Target providers whose APIs are already useful to AI agents, automation, web
   data, SERP/search, browser, scraping, or data enrichment workflows.
2. Use only public company contact addresses from official product, docs,
   contact, FAQ, or support pages.
3. Import each provider into `/growth` as a `GrowthLead` with source evidence,
   contact provenance, fit score, and confidence score.
4. Create one `OutreachMessage` per provider with the official site
   `https://synapse-network.ai/` in the body.
5. Send only after explicit operator confirmation.
6. Write append-only `message_sent` evidence into the Growth ledger.

## Local Command

Dry run and ledger preparation:

```bash
python3 scripts/growth/provider_outreach_batch.py
```

Real send:

```bash
python3 scripts/growth/provider_outreach_batch.py \
  --send \
  --confirm SEND_PROVIDER_OUTREACH_20260602
```

The script refuses to send unless both `EMAIL_FROM` and
`GMAIL_SMTP_USERNAME` equal `cliff@synapse-network.ai`.

## Safety Notes

1. Do not use personal Gmail as the sender.
2. Do not send without public contact provenance.
3. Do not claim guaranteed revenue or guaranteed agent demand.
4. Keep the CTA low-friction: ask whether registration details and a sample
   service contract would be useful.
5. Honor any `not interested` reply and mark the lead `do_not_contact`.

## Reply Monitoring

After sends, run the Gmail reply monitor in dry-run or apply mode:

```bash
python3 scripts/growth/provider_reply_monitor.py --days 14 --limit 50
python3 scripts/growth/provider_reply_monitor.py --apply --days 14 --limit 50
python3 scripts/growth/provider_reply_monitor.py --watch --interval-seconds 900 --apply --days 14 --limit 50
```

The monitor reads Gmail INBOX through IMAP, matches replies to sent provider
messages, records `growth_provider_replies`, and creates a human-reviewed reply
draft visible in `/growth` -> `Providers` -> `Provider Reply Inbox`. It never
sends replies automatically.
