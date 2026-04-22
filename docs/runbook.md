# Operator Runbook

## Boot Local Stack

1. Copy `.env.example` to `.env` if you need to override defaults.
2. Run `make start` or `./scripts/start-local.sh`.
3. Open the dashboard at `http://localhost:3000`.
4. Confirm each service responds on `/healthz`.
5. Trigger the demo pipeline with `make demo` or `./scripts/demo-local.sh`.

## Simulate An End-to-End Flow

1. Register a stream with `POST /api/v1/streams`.
2. Emit packets from the ingestion service with `POST /api/v1/streams/{source_id}/emit`.
3. If you are using `AETHER_EVENT_BUS_BACKEND=memory`, send packets to fusion with `POST /api/v1/fusion/ingest`.
4. If you are using `redis_streams` or `kafka_redis`, ingestion publishes packets onto the `streams` topic and fusion consumes them automatically.
5. Fuse a window with `POST /api/v1/fusion/window`.
6. Store the resulting event as a `MemoryNode` with `POST /api/v1/memory/store`.
7. Run a reasoning pass through `POST /api/v1/reason`.
8. Evaluate any proposed action with `POST /api/v1/governance/evaluate`.
9. Dispatch allowed actions with `POST /api/v1/actions/dispatch`.

## Fast Demo Path

1. Boot the local stack with `./scripts/start-local.sh --demo`.
2. Watch the dashboard update as stream packets, fusion output, memory writes, reasoning results, and governance alerts are published through the realtime gateway.
3. If you want to rerun the pipeline without rebuilding the stack, use `./scripts/demo-local.sh`.

## Data Plane Checks

- Confirm the event bus mode with `AETHER_EVENT_BUS_BACKEND` in your runtime environment.
- Check memory persistence readiness at `GET /api/v1/memory/backends`.
- Check kernel control-plane persistence at `GET /api/v1/kernel/backends`.
- Check fusion packet intake with `GET /api/v1/fusion/buffer`.
- If Redis or Kafka are unavailable, the services fall back to in-process behavior for local continuity.

## Incident Handling

- If governance blocks unexpectedly, inspect `GET /api/v1/governance/audit`.
- If action dispatch fails repeatedly, inspect `GET /api/v1/actions/dead-letter`.
- If the dashboard is stale, confirm the realtime gateway is reachable on port `8007`.
- If the end-to-end loop is stalled, confirm the kernel service is reachable on port `8008`.
- If agents, task runs, workflows, or reviews do not survive a restart, inspect `GET /api/v1/kernel/backends`.
- If memory is not persisting durably, inspect `GET /api/v1/memory/backends`.
- If Prometheus is empty, confirm `/metrics` is reachable on each service.
- Use `make logs` to tail the stack logs during diagnosis.
