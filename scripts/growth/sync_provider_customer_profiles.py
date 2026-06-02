#!/usr/bin/env python3
"""Sync sent provider outreach leads into the provider customer profile DB."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.database import SessionLocal, engine
from server.database_growth import GrowthProviderProfileRow
from server.services.growth.provider_profiles import sync_provider_profiles
from server.services.growth.serializer import json_loads


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--export-jsonl",
        default="",
        help="Optional path to export synced profiles as JSONL.",
    )
    args = parser.parse_args()

    GrowthProviderProfileRow.__table__.create(bind=engine, checkfirst=True)
    with SessionLocal() as db:
        profiles = sync_provider_profiles(db)
        if args.export_jsonl:
            export_jsonl(Path(args.export_jsonl), profiles)
        for profile in profiles:
            print(
                f"{profile.organization}: profile_id={profile.id} "
                f"lead_id={profile.lead_id} website={profile.website_url}"
            )
        print(f"synced_provider_profiles={len(profiles)}")
    return 0


def export_jsonl(path: Path, profiles: list[GrowthProviderProfileRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for profile in profiles:
            payload = {
                "id": profile.id,
                "lead_id": profile.lead_id,
                "organization": profile.organization,
                "website_url": profile.website_url,
                "company_description": profile.company_description,
                "contact_email": profile.contact_email,
                "contact_source_url": profile.contact_source_url,
                "source_url": profile.source_url,
                "latest_message_id": profile.latest_message_id,
                "latest_message_subject": profile.latest_message_subject,
                "latest_message_status": profile.latest_message_status,
                "last_contacted_at": profile.last_contacted_at.isoformat()
                if profile.last_contacted_at
                else None,
                "profile_status": profile.profile_status,
                "evidence": json_loads(profile.evidence_json, []),
                "metadata": json_loads(profile.metadata_json, {}),
            }
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
