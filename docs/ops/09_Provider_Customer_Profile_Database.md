---
id: provider_customer_profile_database
title: Provider Customer Profile Database
role: growth_lead
status: ready
created_at: 2026-06-02
updated_at: 2026-06-02
author: codex
target_repo: /Users/cliff/workspace/agent/Synapse-Network-Growing-agent-b
---

# Provider Customer Profile Database

## Purpose

Provider outreach should not disappear after an email is sent. Every provider
that has received an outreach email becomes a historical lead in a maintained
customer profile database.

The source of truth is the local Postgres table:

```text
growth_provider_profiles
```

## Data Model

Each profile stores:

1. `lead_id`: source `GrowthLead` id.
2. `organization`: company name.
3. `website_url`: official company website.
4. `company_description`: concise description of what the company provides.
5. `contact_email`: public contact email used for outreach.
6. `contact_source_url`: public source for the contact email.
7. `source_url`: original lead source URL.
8. `latest_message_id`, `latest_message_subject`, `latest_message_status`.
9. `last_contacted_at`: when the latest sent outreach happened.
10. `profile_status`: currently `historical_lead`.
11. `evidence_json`: source evidence for website, contact, and fit.
12. `metadata_json`: sync provenance and linked message metadata.

## Sync Flow

```text
GrowthLead(provider)
-> sent GrowthOutreachMessage
-> sync_provider_profiles(db)
-> growth_provider_profiles upsert
-> optional JSONL export
```

The sync only includes provider leads with at least one `sent` outreach message.
It is idempotent: re-running it updates existing rows by `lead_id`.

## Console Placement

The operator surface lives in `/growth` -> `Providers` -> `Provider Customer
Profiles`.

This belongs in the provider acquisition module because the rows are historical
outreach leads, not a standalone CRM workflow. The panel sits below the provider
lead queue and reads `/api/growth/provider-profiles` so operators can compare the
current acquisition queue with previously contacted provider companies.

## Command

```bash
python3 scripts/growth/sync_provider_customer_profiles.py \
  --export-jsonl runtime/provider-customer-profiles.jsonl
```

The command creates `growth_provider_profiles` if it does not exist, syncs all
sent provider leads, prints the synced rows, and optionally exports JSONL for
manual review or CRM import.

## Maintenance Rules

1. Do not store private API keys, tokens, cookies, SMTP passwords, or personal
   secrets in profile metadata.
2. Company descriptions must be sourced from public product pages or official
   docs.
3. If a provider replies `not interested`, mark the profile or lead as
   `do_not_contact` before any follow-up.
4. Use the profile database for history and segmentation; the append-only
   `growth_outreach_events` table remains the send/reply audit trail.
