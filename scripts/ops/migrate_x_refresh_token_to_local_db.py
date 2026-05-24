#!/usr/bin/env python
"""Move the X OAuth2 refresh token from Secret Manager into local encrypted DB."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from server import config  # noqa: E402
from server.database_local_secrets import LocalSecretVersionRow  # noqa: E402
from server.database import SessionLocal, init_db  # noqa: E402
from server.services.local_secrets import write_local_secret_version  # noqa: E402
from server.services.social.publishing import (  # noqa: E402
    SecretValueStore,
    SocialPublishError,
    XOAuth2TokenProvider,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate X refresh token to encrypted local DB storage."
    )
    parser.add_argument(
        "--secret",
        default=config.X_OAUTH_REFRESH_TOKEN_SECRET,
        help="Secret Manager secret ref to read.",
    )
    parser.add_argument(
        "--local-key",
        default=config.X_OAUTH_REFRESH_TOKEN_LOCAL_KEY,
        help="Local DB secret key to write.",
    )
    parser.add_argument(
        "--skip-verify", action="store_true", help="Skip X OAuth refresh verification."
    )
    parser.add_argument(
        "--verify-local-only",
        action="store_true",
        help="Only verify the local encrypted DB token; do not read Secret Manager.",
    )
    args = parser.parse_args()

    init_db()
    store = SecretValueStore()
    version = None
    if not args.verify_local_only:
        refresh_token = store.read(args.secret)
        with SessionLocal() as db:
            row = write_local_secret_version(
                db,
                args.local_key,
                refresh_token,
                metadata={
                    "source": "secret_manager_migration",
                    "secret_ref": args.secret,
                },
                keep_active=3,
            )
            db.commit()
            version = int(row.version)

    with SessionLocal() as db:
        active_version_count = (
            db.query(LocalSecretVersionRow)
            .filter(
                LocalSecretVersionRow.secret_key == args.local_key,
                LocalSecretVersionRow.status == "active",
            )
            .count()
        )

    verified = False
    rotated = False
    if not args.skip_verify:
        os.environ["X_OAUTH_REFRESH_TOKEN_STORAGE"] = "local_db"  # nosec B105 - storage mode, not a secret
        provider = XOAuth2TokenProvider(store)
        try:
            token = provider.get_access_token()
            verified = bool(token.access_token)
            rotated = bool(token.refresh_token_rotated)
        except SocialPublishError as exc:
            print(
                json.dumps(
                    {
                        "status": "verification_failed",
                        "local_key": args.local_key,
                        "local_version": version,
                        "active_version_count": int(active_version_count or 0),
                        "verified_refresh": False,
                        "failure_kind": exc.kind,
                        "failure_summary": exc.summary,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1

    print(
        json.dumps(
            {
                "status": "verified" if args.verify_local_only else "migrated",
                "local_key": args.local_key,
                "local_version": version,
                "active_version_count": int(active_version_count or 0),
                "verified_refresh": verified,
                "refresh_token_rotated_during_verify": rotated,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
