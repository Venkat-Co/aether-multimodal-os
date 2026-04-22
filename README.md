# AETHER

**Realtime agent orchestration platform for governed multimodal operations.**

AETHER is a platform for running governed multimodal agents in environments where reliability, visibility, and control matter. It combines live signal ingestion, context fusion, memory, reasoning, governance, and action orchestration into a single operational layer for mission-critical systems.

Most agent systems are built like chat products. AETHER is built like infrastructure. It is designed for teams that need agents to observe live conditions, reason over evolving context, act through approved tools, and escalate to humans when risk, ambiguity, or policy requires it.

## What It Is

AETHER runs governed multimodal agents for mission-critical operations.

In practical terms, that means:

- agents can observe video, audio, text, and sensor inputs
- agents can reason over live and historical state
- agents can retain working and persistent memory
- agents can execute actions through controlled interfaces
- every decision can be evaluated by governance before it is allowed to proceed
- human operators stay in the loop through the dashboard, audit trail, and escalation paths

## Why We Built It

We built AETHER because agents become far more useful when they can operate with realtime awareness, retained memory, and enforcement boundaries.

In high-stakes environments, raw model output is not enough. Teams need:

- realtime context instead of isolated prompts
- persistent memory instead of stateless interactions
- policy-governed execution instead of unrestricted tool calls
- operator visibility instead of opaque automation
- escalation and override paths instead of brittle autonomy

AETHER explores what an agent runtime looks like when it is designed for operational trust from the beginning.

## How It Is Built

AETHER is implemented as a service-oriented system with a premium operator console on top.

- **Python microservices** provide ingestion, fusion, memory, reasoning, governance, action orchestration, realtime sync, and kernel coordination
- **Shared contracts** live in `packages/aether_core` so services speak a common language
- **Event-driven architecture** supports in-memory, Redis Streams, and Kafka-plus-Redis transport paths
- **Hybrid persistence** allows memory to remain local for demos while also supporting PostgreSQL/pgvector and Neo4j-backed operation
- **React + Three.js** powers the command-center dashboard
- **Docker Compose and Helm** support local development and a production-oriented deployment path
- **GitHub Actions and GitHub Pages** provide automated validation and a public demo surface

## What AETHER Does Today

The current repository delivers a working platform backbone:

- multimodal stream registration and simulated signal emission
- fusion of vision, audio, text, and sensor context into a unified event
- storage of fused events into working memory
- reasoning over current system state
- governance decisions before action dispatch
- action orchestration and dashboard visibility
- local Docker startup, API surfaces, and a public GitHub Pages dashboard demo

This repo is best understood as a serious platform prototype: the architecture, runtime boundaries, dashboard, and deployment scaffolding are real, while some heavyweight integrations remain scaffold-grade.

## Platform Architecture

These services map directly to the agent-platform model:

- `services/ingestion`
  Agent context adapters for multimodal sources
- `services/fusion`
  Multimodal context synthesis into coherent operational state
- `services/memory`
  Working and persistent memory for agent recall
- `services/reasoning`
  Reactive, proactive, predictive, and causal inference
- `services/governance`
  Policy evaluation, auditability, escalation, and execution controls
- `services/action`
  Tool dispatch, retries, rollback, and human-loop integration
- `services/realtime`
  State fan-out for the live command surface
- `services/kernel`
  Orchestration runtime coordinating the end-to-end loop
- `dashboard`
  Premium operator console for oversight and intervention

## Repository Layout

```text
packages/aether_core        Shared models, settings, observability, utilities
services/ingestion          Stream registration and modality adapters
services/fusion             Multimodal fusion engine
services/memory             Persistent memory graph API
services/reasoning          Reactive, proactive, predictive, and causal reasoning
services/governance         Constitutional governance and audit pipeline
services/action             Action orchestration and rollback coordination
services/realtime           WebSocket fan-out and dashboard state sync
services/kernel             End-to-end orchestration across all services
dashboard                   React + Three.js operator interface
infra/docker                Multi-stage container definitions
infra/helm/aether-os        Helm chart for production deployment
docs                        ADRs, runbooks, architecture notes
tests                       Unit and integration tests
proto                       gRPC contracts
```

## Quick Start

1. Copy `.env.example` to `.env` if you want to override defaults.
2. Start the full stack with `make start` or `./scripts/start-local.sh`.
3. Trigger the end-to-end demo loop with `make demo`, `./scripts/demo-local.sh`, or `./scripts/start-local.sh --demo`.
4. Open the dashboard at `http://localhost:3000`.
   - The dashboard will auto-target the kernel review API at `http://localhost:8008` for local approval actions.
5. Open service docs:
   - Ingestion: `http://localhost:8001/docs`
   - Fusion: `http://localhost:8002/docs`
   - Memory: `http://localhost:8003/docs`
   - Reasoning: `http://localhost:8004/docs`
   - Governance: `http://localhost:8005/docs`
   - Action: `http://localhost:8006/docs`
   - Realtime: `http://localhost:8007/docs`
   - Kernel: `http://localhost:8008/docs`
6. Stop the stack with `make stop` or `./scripts/stop-local.sh`.

## Local Control

- `make start` boots the stack, waits for the HTTP surfaces, and prints the main URLs
- `make demo` runs the kernel demo endpoint and prints the JSON result
- `make logs` tails the compose logs
- `make stop` shuts the stack down

## Data Plane Notes

- Set `AETHER_EVENT_BUS_BACKEND` to `memory`, `redis_streams`, or `kafka_redis`
- Local Docker Compose is prewired for Redis and Kafka through [.env.example](/Users/venkatreddymittapalli/Documents/Codex/2026-04-21-here-is-your-premium-end-to/.env.example)
- Memory backend status is available at `GET /api/v1/memory/backends`
- When the event bus is distributed, ingestion publishes packet events onto `streams` and fusion consumes them automatically before `fuse_window`

## Public Demo

The repo also ships with a public GitHub Pages experience:

- [https://venkat-co.github.io/aether-multimodal-os/](https://venkat-co.github.io/aether-multimodal-os/)

Because GitHub Pages is a static host, the public site runs in curated demo mode by default. It publishes the premium command surface, but not the full Python services, Kafka, Redis, Neo4j, or live WebSocket backend.

If you later host the realtime layer somewhere else, you can point the Pages build at it with:

- `https://venkat-co.github.io/aether-multimodal-os/?ws=wss://your-realtime-host`
- `https://venkat-co.github.io/aether-multimodal-os/?ws=wss://your-realtime-host&api=https://your-kernel-host`

## Current Maturity

AETHER is production-shaped, but not yet a finished production platform.

What is already in place:

- clear service boundaries
- an end-to-end operational loop
- a premium realtime dashboard
- governance and audit surfaces
- local deployment and public demo paths
- CI and deploy automation

What still needs deeper production work:

- real model serving for Whisper, CLIP, and large reasoning models
- hardened auth, secrets, and policy integrations such as Vault and OPA
- scale validation under sustained distributed load
- richer agent definitions, tool registries, and workflow runtime semantics
- verticalized product workflows for real operators and real customers

## Product Direction

The intended direction for AETHER is not “general AI assistant.”

It is:

**A governed multimodal agent orchestration platform for mission-critical operations.**

That means the next layer of maturity is about turning the current runtime into a stronger agent platform with:

- formal agent definitions
- reusable tool registries
- task and workflow state management
- policy-first execution gates
- multi-agent coordination
- better operator supervision and intervention tooling
