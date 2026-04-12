# Spec

## Goal

Turn system bugs into first-class operating inputs:

1. accept bugs from internal and external sources
2. normalize them into a stable bug registry
3. dedupe repeated failures into fingerprints
4. score severity and operating impact
5. convert high-value bugs into requirements
6. route each requirement to the affected project
7. require fix evidence and regression validation before closeout

The target state is not "collect more errors". The target state is "convert real failures into governed remediation work".

## Problem

Today, bug-like information is scattered across:

1. `server/logs/*`
2. task runtime logs
3. workflow incidents and artifacts
4. manual bug reports from operator
5. future external systems such as Sentry, webhook feeds, or product error streams

Some of this already becomes `optimization signals`, but the system still lacks a dedicated bug intake contract. That creates three gaps:

1. bug evidence may stay in logs instead of entering the requirement pool
2. repeated failures may waste tokens because the same bug is rediscovered many times
3. fixes may not be routed with explicit bug validation and regression coverage

## Core Design

### 1. Bug Source Registry

The system should treat bug sources as a registry, not hardcoded one-off scripts.

Each bug source should define:

1. `source_key`
2. `display_name`
3. `source_kind`
4. `ingest_mode`
   1. `push_api`
   2. `log_sweep`
   3. `artifact_derived`
   4. `external_webhook`
5. `project_resolution_rule`
6. `severity_mapping`
7. `dedupe_scope`
8. `auto_requirement_policy`

Initial built-in sources:

1. `manual_bug_report`
2. `runtime_log_error`
3. `workflow_incident`
4. `task_failure`
5. `delivery_blocker_bug`

### 2. Bug Record Contract

Every normalized bug should contain:

1. `bug_key`
2. `project_key`
3. `project_root_path`
4. `title`
5. `summary`
6. `severity`
7. `fingerprint`
8. `source_key`
9. `source_ref`
10. `environment`
11. `first_seen_at`
12. `last_seen_at`
13. `occurrence_count`
14. `evidence`
15. `status`
    1. `open`
    2. `triaged`
    3. `materialized`
    4. `resolved`
    5. `suppressed`

### 3. Dedupe And Fingerprinting

The system should never create a new requirement for every single log line.

Fingerprinting should combine:

1. project identity
2. source kind
3. normalized error code or exception class
4. normalized top stack frame or message stem
5. route / component / workflow step when available

The bug registry should preserve `occurrence_count` and time range, while only keeping representative evidence samples in prompts and summaries.

### 4. Bug Scoring

Bug priority should be determined by operating impact, not only by text severity.

Base inputs:

1. declared severity
2. recurrence count
3. freshness
4. whether the bug blocks execution
5. whether the bug blocks publish
6. whether it affects multiple projects
7. whether it breaks recurring workflows

Suggested output:

1. `priority`
   1. `critical`
   2. `high`
   3. `normal`
2. `auto_intake_eligible`
3. `intake_reason`

Not every bug should be "highest priority". Only bugs that block the operating system, production-critical flows, publish, or incident recovery should auto-upgrade to the top tier.

### 5. Bug-To-Requirement Contract

When a bug is materialized into a requirement, the requirement should carry:

1. `source = bug_intake`
2. `source_ref = bug_key`
3. `intake_metadata`
4. `target_project_path`
5. `acceptance_contract`
6. `approval_contract`
7. `validation_contract` focused on bug closure

Expected acceptance focus for bug requirements:

1. root cause documented
2. fix implemented in affected project
3. regression guard added
4. verification reproduces "before" and proves "after"
5. follow-up incidents for the same fingerprint stop recurring

### 6. Log Sweep Workflow

The system should add a recurring workflow dedicated to bug discovery:

`bug_log_sweep`

Responsibilities:

1. tail or read recent service logs
2. detect error candidates
3. normalize them into bug records
4. dedupe against existing open bugs
5. create or update bug evidence
6. optionally materialize high-value bugs into requirements

This workflow should be token-efficient:

1. regex or heuristic prefilter first
2. model only used for normalization when deterministic parsing is insufficient
3. repeated evidence deduped before prompting

### 7. Boundaries

Harness decides:

1. which sources are allowed
2. dedupe rules
3. project scope and routing boundary
4. severity and auto-intake policy
5. approval and validation requirements

Model decides:

1. bug summary wording
2. likely root-cause hypothesis
3. remediation plan
4. code/doc/config change shape inside allowed project scope

The system should not let the model invent bug sources, bypass project boundaries, or auto-close without validation evidence.

## Target Outputs

Once implemented, the system should expose:

1. bug source registry view
2. bug intake API
3. log-sweep recurring workflow
4. bug backlog in requirement source registry
5. company review sections for:
   1. open bug pressure
   2. recurring bug fingerprints
   3. bug remediation completion

## Non-Goals

This phase does not require:

1. full Sentry integration
2. log indexing for every repository in the workspace
3. autonomous production rollback
4. replacing `optimization signals`; bug intake should complement and feed them
