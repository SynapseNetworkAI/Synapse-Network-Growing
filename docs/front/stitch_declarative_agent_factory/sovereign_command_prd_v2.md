# Sovereign Command: Human-Agent Control Plane (v2)

## 1. Vision
Transforming Synapse Ops into a high-fidelity cockpit where the operator manages intent and gates, while agents handle reasoning and deterministic atoms handle execution.

## 2. Core Domains & Navigation
- **Command Center:** The 'Today' view. Blockers, active runs, and budget telemetry.
- **Planning:** Goal-centric mission control. Active Manifest and Requirements.
- **Intake:** Signal discovery. Error fingerprints, watcher events, and feedback.
- **Oracle Gates:** Human-in-the-loop headquarters. Risk-Evidence decisions.
- **Execution:** The engine room. Workflow runs and the Run Explorer (Blackboard).
- **Delivery:** The final mile. PRs, releases, and post-deployment observation.
- **Factory:** The rails. YAML definitions, Atom registry, and Risk policies.
- **Knowledge:** The memory layer. SOPs, Artifacts, and Lesson learned.
- **System Ops:** Infrastructure health. Scheduled jobs and notification logs.

## 3. UI/UX Principles
- **Decision Paths, Not Tables:** Organize views by what the operator needs to decide NEXT.
- **Blackboard as UI:** No raw JSON in main views. Transform state data into Evidence Cards.
- **Risk-Evidence Balance:** Highlight high-risk actions with warning treatments and direct links to supporting evidence.
- **Obsidian Protocol:** Deep dark backgrounds (#10131a), raised panels (#191c22), machine-readable fonts for logs (JetBrains Mono), and Inter for human guidance.