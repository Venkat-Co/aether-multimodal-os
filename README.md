# AETHER

AETHER is a production-oriented starter monorepo for a real-time multimodal reasoning operating system. This repository scaffolds the seven-layer architecture from the specification as independently deployable services with shared contracts, local orchestration, Kubernetes deployment assets, and operator documentation.

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

## Current Status

This initial cut emphasizes a runnable backbone:

- Shared schemas and service settings
- Async FastAPI microservices for each layer
- A kernel service that coordinates a complete multimodal reasoning loop
- In-memory and pluggable implementations for core logic
- Shared event-bus abstractions with Redis Streams and Kafka+Redis backends
- Hybrid memory persistence that can use PostgreSQL/pgvector and Neo4j when available
- Docker Compose and Helm scaffolding
- React dashboard shell with live WebSocket hooks
- GitHub Actions CI for backend and dashboard validation
- Unit and contract tests for the critical reasoning/governance path

It is intentionally structured so production integrations like Kafka, Redis Streams, Neo4j, pgvector, TimescaleDB, Vault, and OPA can be wired in without breaking service boundaries.

## Data Plane Notes

- Set `AETHER_EVENT_BUS_BACKEND` to `memory`, `redis_streams`, or `kafka_redis`.
- Local Docker Compose is prewired for Redis and Kafka through [.env.example](/Users/venkatreddymittapalli/Documents/Codex/2026-04-21-here-is-your-premium-end-to/.env.example).
- Memory backend status is available at `GET /api/v1/memory/backends`.
- When the event bus is distributed, ingestion publishes packet events onto `streams` and fusion consumes them automatically before `fuse_window`.

## Local Control

- `make start` boots the stack, waits for the HTTP surfaces, and prints the main URLs.
- `make demo` runs the kernel demo endpoint and prints the JSON result.
- `make logs` tails the compose logs.
- `make stop` shuts the stack down.

## GitHub Pages

- The repository now includes `.github/workflows/pages.yml` to publish the dashboard to GitHub Pages on every push to `main`.
- Because GitHub Pages is a static host, it can publish the premium dashboard shell but not the Python microservices, Redis, Kafka, Neo4j, or realtime WebSocket backend. The public Pages site therefore runs in a curated demo mode unless you point it at an external realtime endpoint.
- Once Pages is enabled for the repository, the default project-site URL will be `https://venkat-co.github.io/aether-multimodal-os/`.
- If you later host the realtime service somewhere else, you can override the dashboard socket target with a query parameter:
  - `https://venkat-co.github.io/aether-multimodal-os/?ws=wss://your-realtime-host`
