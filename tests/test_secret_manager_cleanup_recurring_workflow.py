import pytest

from server.services.scheduling.recurring_workflows import (
    get_recurring_workflow,
    run_recurring_workflow,
    sync_recurring_workflows,
)


def test_secret_manager_cleanup_recurring_workflow_is_not_registered(db_session):
    sync_recurring_workflows(db_session)

    with pytest.raises(ValueError, match="Recurring workflow not found"):
        get_recurring_workflow(db_session, "secret_manager_version_cleanup_sweep")
    with pytest.raises(ValueError, match="Recurring workflow not found"):
        run_recurring_workflow(
            db_session, workflow_key="secret_manager_version_cleanup_sweep", dry_run=True
        )
