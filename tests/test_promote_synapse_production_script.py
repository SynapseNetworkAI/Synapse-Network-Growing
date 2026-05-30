from pathlib import Path


def test_gateway_prod_promote_script_disables_trigger_style_envs_for_jobs():
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts/local/promote_synapse_production.sh"
    ).read_text()

    assert "build_gateway_job_env_flags()" in script
    assert "DEPOSIT_INDEXER_TRIGGER_ENABLED=false" in script
    assert "NOTIFICATION_OUTBOX_TRIGGER_ENABLED=false" in script
    assert "ALCHEMY_DEPOSIT_WEBHOOK_ENABLED=false" in script
    assert 'build_gateway_job_env_flags\n    update_gateway_prod_jobs "${prod_digest}"' in script
