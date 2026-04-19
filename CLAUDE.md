# Claude Instructions

This file is a short pointer for Claude-style coding assistants. Do not duplicate the architecture constitution here; use the shared repo files as source of truth.

Before editing this repository, read:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `docs/design-docs/system-design-principles.md`

For workflow, planning, scheduler, release, notification, runtime, auth, finance, settlement, or production-safety work, also read `.github/instructions/architecture-constraints.instructions.md`.

Hard default: agents produce structured output, deterministic runners own state transitions, and high-risk actions require human gate.
