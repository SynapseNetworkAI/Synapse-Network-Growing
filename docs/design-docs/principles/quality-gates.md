# Quality Gates Principles

Load this when touching CI, PRs, tests, coverage, linting, code quality, line count, complexity, security checks, dependency audit, or branch protection.

## Full Gate Source Of Truth

1. `scripts/ci/pr_checks.sh` is the full gate source of truth for main, nightly, manual full CI, and large/high-risk local validation.
2. Full gate can be split in CI with `PR_CHECKS_PHASE=quality|backend|dashboard|all`, but the combined phases must equal `all`.
3. PR CI uses `scripts/ci/ci_scope.py` for scoped checks. Unclear scope or workflow/dependency/schema/migration/non-classifier CI gate changes upgrade to full gate.
4. Docs-only scope does not install dashboard dependencies or run backend pytest. Dashboard-only scope skips backend pytest. Backend-only scope skips dashboard tests/build.
5. Local pre-push defaults to `scripts/ci/local_pr_checks.sh --scope auto`; use `SYNAPSE_CI_SCOPE=full` for major changes or release prep.
6. GitHub branch protection should require aggregate `pr-checks`; skipped scoped jobs must not become merge blockers.
7. GitHub Actions dependency caches are required: Python jobs use pip cache, Node jobs use yarn cache, and uv/uvx jobs use setup-uv cache. Do not cache `dashboard/node_modules` by default.
8. GitHub-hosted runner tools such as `rg` must be pinned and cached. PR CI should use `bootstrap_ci_tools.sh` for fixed-version ripgrep and cache `.ci-tools/ripgrep/<version>`.
9. Lightweight scope, docs, and aggregate jobs can use `ubuntu-slim`; heavy backend, dashboard, and full gates keep standard Ubuntu runners.
10. Python runtime is detected dynamically. Do not hardcode one machine's virtualenv as the only valid path.
11. Diff coverage must use a valid merge-base; fetch stale `origin/main` before judging coverage.
12. `--no-verify` can bypass only local hooks. It is not a qualified delivery result; remote CI remains the backstop.

## Push Quality Gates V2

1. `scripts/ci/code_quality_gates.sh` must cover typecheck, lint, complexity, line-count, duplicate code, secret scan, SAST, dependency audit, and branch-protection diagnostic.
2. Dependency audit can be skipped only in scoped PRs by risk policy; full gate must run it.
3. Line-count gate is baseline plus ratchet: new production files `<= 500` lines, new test files `<= 900` lines, and legacy over-limit files cannot grow unless the same PR reduces or splits them.
4. Python complexity gate uses changed/new-code ratchet. New runtime Python must satisfy Xenon `--max-absolute B`.
5. Function length hard gate remains `<= 120` lines for non-grandfathered production Python.
6. Context rules prevent bad shape before coding; CI is the merge hard gate. They cannot replace each other.
7. Split by responsibility. Long function -> private helper first. New module only for clear I/O, scanner, runner, serializer, adapter, client, policy, or strategy boundary.
8. Do not slice tightly coupled logic into meaningless fragments just to pass `500` lines.
9. PR description must explain why code was split and where the responsibility boundary moved when a line-count or complexity threshold is involved.

## Service Shape And Anti-Bloat

1. `server/services` must not return to a flat universal directory.
2. Requirement, release, runtime, review, project policy, signal, and bug intake live in clear functional surfaces.
3. New service files over `500` lines are a warning; over `900` lines must be split.
4. Each service package should have a `README.md` describing responsibility, entrypoints, dependency boundaries, and forbidden dependencies.
5. Routers depend on facades or stable public entrypoints, not private helpers.
6. One module serves one business surface.
7. Package public entrypoints should be minimal. Cross-directory calls should go through facade or shared helper.
8. Prefer composition through helpers, services, and policies. Do not add complex inheritance trees by default.
9. Upper orchestration depends on stable facades and schemas, not lower-level file layout.

## Security And Contracts

1. Duplicate-code gate prevents new large copy-paste blocks. Existing baseline debt is not a reason to keep copying.
2. Security gates fail closed on new secrets, high-risk Bandit issues, Python dependency vulnerabilities, or frontend high/critical audit findings.
3. CI output must be redacted. Never print token, secret, webhook URL, authorization header, or raw credential payload.
4. Branch protection check is fact absorption, not a promise. If GitHub plan only allows diagnostic mode, display that explicitly.
5. Public service return contracts are object-shaped. Core Planning, Social, Release, and API-facing functions must not expose raw `dict`, `Dict[str, Any]`, `dict[str, Any]`, `Mapping[str, Any]`, or frontend `Promise<Record<string, unknown>>`.
6. API-facing Python should return Pydantic result/response objects and serialize at the FastAPI/API boundary.
7. Raw maps are allowed only for request bodies, patches, schema/payload fields, metadata/blackboard fields, third-party payloads, test fixtures, or private helper intermediate data.
8. Private helpers start with `_`; cross-module public surfaces should become typed object contracts before exposure.

## PR Hygiene

1. PR body is reviewer-first: business summary, safety/review reason, human merge checklist, then evidence or links.
2. Long evidence, logs, retry history, and raw output should be folded or linked.
3. PR descriptions and GitHub comments must use real Markdown line breaks, not literal `\n` escape sequences.
4. If CI fails because of local runtime corruption, fix the hook/runtime path when possible; if using `--no-verify`, document what passed and why the local hook was bypassed.
