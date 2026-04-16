# .code-review-graph

This directory keeps the local architecture export for `Synapse-Network-Growing`.

- `graph.svg`: canonical SVG architecture graph
- `architecture-overview.json`: subsystem and edge summary used by the docs

Regenerate with:

```bash
python3 scripts/generate_architecture_graph.py
```

The output format intentionally mirrors the artifact layout used by `code-review-graph visualize --format svg`,
while staying offline-friendly for this repository's sandboxed execution environment.

Direct package download was attempted with:

```bash
python3 -m pip download code-review-graph --no-deps -d /tmp/code-review-graph-download
```

That command failed because the sandbox shell cannot reach the package index, so this repository keeps
an offline-compatible export instead of pretending the upstream package is installed locally.