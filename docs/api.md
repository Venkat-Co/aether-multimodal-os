# API Surface

Each backend service exposes FastAPI docs under `/docs`.

## Public REST Endpoints

- `POST /api/v1/streams`
- `GET /api/v1/streams`
- `POST /api/v1/ingest`
- `POST /api/v1/memory/query`
- `POST /api/v1/reason`
- `POST /api/v1/governance/evaluate`
- `GET /api/v1/governance/audit`
- `POST /api/v1/actions/dispatch`
- `POST /api/v1/kernel/pipeline/run`
- `POST /api/v1/kernel/pipeline/demo`
- `GET /api/v1/memory/backends`

## WebSocket Endpoints

- `/ws/streams/{source_id}`
- `/ws/fusion`
- `/ws/memory/updates`
- `/ws/governance/alerts`
- `/ws/reasoning/results`
- `/ws/dashboard/state`

## Internal Contracts

- gRPC definitions live in [proto/aether.proto](/Users/venkatreddymittapalli/Documents/Codex/2026-04-21-here-is-your-premium-end-to/proto/aether.proto).
- Shared Pydantic schemas live in [packages/aether_core/src/aether_core/models.py](/Users/venkatreddymittapalli/Documents/Codex/2026-04-21-here-is-your-premium-end-to/packages/aether_core/src/aether_core/models.py).
