## Summary

- business surface:
- user/operator outcome:

## Agent-First Checks

- [ ] This change keeps `agent` as execution owner and does not push execution content decisions back into the program.
- [ ] This change belongs clearly to one governance surface: requirement, execution, release, runtime, stability, orchestration, or policy.
- [ ] If this change touches workflow shape, it still preserves the minimal default flow: `intake -> execute -> validate -> deliver`.

## Workbench UI Checks

- [ ] If UI changed, I identified the page as Requirement / Execution / Release.
- [ ] If UI changed, I reused the workbench shell, section, inspector, activity feed, and token system where applicable.
- [ ] This PR does not reintroduce a dashboard-card mosaic or same-weight white-card layout.
- [ ] This page has one clear primary workspace instead of multiple competing focal blocks.
- [ ] This PR does not put a long-lived create/edit form inline on a list page when `Toolbar + Drawer` would fit.
- [ ] If this is a list page, create/edit actions use the standard drawer pattern unless there is a documented quick-edit exception.

## Structure Checks

- [ ] I did not add new flat service modules or bypass facade boundaries.
- [ ] I documented any new public entrypoint or design token.
- [ ] If any file crossed the complexity threshold, I called it out explicitly in the PR description.
