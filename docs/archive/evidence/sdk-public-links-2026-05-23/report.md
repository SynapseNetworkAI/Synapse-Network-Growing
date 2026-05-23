---
id: sdk-public-links-2026-05-23
title: SDK Public Links Local E2E Evidence
role: dev_rel
status: ready
created_at: 2026-05-23
updated_at: 2026-05-23
author: codex
target_repo: Synapse-Network-Growing
---

# SDK Public Links Local E2E Evidence

## Scope

Validated SDK `1.0.0` public registry links and install commands across the visible operator and developer surfaces:

1. Growing SDK release history and train detail.
2. Synapse docs SDK hub and language pages.
3. Synapse user-front Developer Resources page.

## Screenshots

| Surface | Evidence |
| --- | --- |
| Growing SDK Packages | `01-growing-sdk-packages.png` |
| Growing SDK Train `1.0.0` public links | `02-growing-sdk-train-public-links.png` |
| Docs SDK hub | `Synapse-Network-Docs/docs/archive/evidence/sdk-public-links-2026-05-23/01-docs-sdks-hub.png` |
| Docs Python SDK | `Synapse-Network-Docs/docs/archive/evidence/sdk-public-links-2026-05-23/02-docs-python-sdk.png` |
| Docs TypeScript SDK | `Synapse-Network-Docs/docs/archive/evidence/sdk-public-links-2026-05-23/03-docs-typescript-sdk.png` |
| Docs Go SDK | `Synapse-Network-Docs/docs/archive/evidence/sdk-public-links-2026-05-23/04-docs-go-sdk.png` |
| Docs Java SDK | `Synapse-Network-Docs/docs/archive/evidence/sdk-public-links-2026-05-23/05-docs-java-sdk.png` |
| Docs .NET SDK | `Synapse-Network-Docs/docs/archive/evidence/sdk-public-links-2026-05-23/06-docs-dotnet-sdk.png` |
| User Front Developer SDK cards | `Synapse-Network/docs/archive/evidence/sdk-public-links-2026-05-23/01-user-front-developer-sdk-cards.png` |

## Registry Verification

Commands validated public availability:

```bash
python -m pip download synapse-network-ai-sdk==1.0.0
npm pack @synapse-network-ai/sdk@1.0.0 --registry=https://registry.npmjs.org/
GOPROXY=https://proxy.golang.org,direct go list -m -json github.com/SynapseNetworkAI/Synapse-Network-Sdk/go@v1.0.0
mvn -q dependency:get -Dartifact=ai.synapse-network:synapse-network-sdk:1.0.0 -Dtransitive=false
curl -fsSI https://api.nuget.org/v3-flatcontainer/synapsenetwork.sdk/1.0.0/synapsenetwork.sdk.1.0.0.nupkg
```

Result: all five package registries resolved version `1.0.0`. Local `dotnet` CLI is not installed on this machine, so NuGet was verified through the public V3 feed and package download URL.

## Local Validation

1. `GET /api/releases/sdk-trains/1.0.0` returned `status_counts.published=5`.
2. Dashboard `ReleasesPage` tests passed.
3. Dashboard production build passed.
4. Synapse user-front page registry tests passed.
5. Synapse user-front production build passed after stopping the dev server to avoid `.next` build directory contention.
6. Synapse docs-front typecheck and production build passed.
7. SDK repo hygiene checks passed.
8. `git diff --check` passed across modified repositories.
