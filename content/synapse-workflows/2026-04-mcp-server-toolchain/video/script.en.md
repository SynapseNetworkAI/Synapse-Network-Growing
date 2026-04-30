---
title: "Video script: MCP Server workflow"
status: draft
language: en
created: 2026-04-30
---

# Video Script

## Opening

Most MCP Server demos show you the server. I want to show the workflow around the server.

This is how I use Claude Code, Apidog, SDK E2E tests, staging, and a publishing queue while building SynapseNetwork.

SynapseNetwork is a gateway where agents can discover APIs, call providers, and settle usage through a blockchain-backed payment layer.

## Workspace Map

The project is split into a few surfaces.

The gateway is the main product. Provider is the runtime that exposes services. SDK is the agent and developer integration layer. Growing is the ops console where requirements, executions, releases, and publishing drafts live. cliff-mind is where I keep strategy and content source material.

The key is that each repo has a clear role.

## Claude Code / Codex Loop

When I add or debug a provider service, I do not start by asking the model to write random code.

I first ask it to search existing patterns: router, schemas, catalog, onboarding, tests, and CI gates.

Then the loop is small:

search, patch, test, run the smallest relevant gate, then expand.

That makes AI coding much safer.

## Apidog Contract Debugging

Apidog is where I check the wire contract.

For provider services, direct anonymous calls should fail. Agents should call the gateway. The gateway handles pricing, idempotency, budgets, settlement, and then forwards a signed request to the provider.

So I use Apidog to inspect request bodies, headers, status codes, and error responses.

## SDK E2E

The real product test is not only unit tests.

The real product test is whether an agent can use the SDK:

provider register, gateway discovery, SDK search, SDK invoke, gateway-signed provider call, and receipt.

If that works locally and in staging, the system is real.

## Local vs Staging

Local is for speed. Staging is for truth.

Local uses local URLs and local-only credentials. Staging uses protected secrets and public URLs.

The provider runtime never gets owner private keys. It only gets runtime secrets like HMAC verification, rate limits, low-risk API keys, and database config.

That separation is important because provider runtimes are exposed to the public internet.

## Quality Gates

AI-native development needs rails.

I use quality gates for typed public returns, file and function size, complexity, duplicate code, coverage, docs consistency, and secret hygiene.

The point is not process for its own sake. The point is making agent-assisted changes safe enough to repeat.

## Publishing Loop

Finally, I turn the workflow into content.

The long articles, scripts, screenshots, and recordings live in git. Short social drafts go into the publishing queue, where they are reviewed before posting.

That creates a learning loop: failures become fixes, fixes become docs, docs become reusable workflows.

## Closing

If you are building MCP Servers or agent-facing API infrastructure, do not only design the server.

Design the debug loop, the staging proof, the SDK E2E, and the publishing loop.

That is what makes the system shippable.
