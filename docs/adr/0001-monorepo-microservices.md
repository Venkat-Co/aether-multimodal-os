# ADR 0001: Monorepo With Independent Runtime Boundaries

## Status

Accepted

## Context

AETHER spans seven cooperating layers, shared schemas, multiple infrastructure targets, and a dashboard. The team needs strong cross-service consistency without giving up the ability to ship services independently.

## Decision

We will keep AETHER in a single monorepo with:

- `packages/aether_core` for shared contracts and operational utilities
- One deployment unit per service under `services/`
- Frontend code under `dashboard/`
- Platform assets under `infra/`

## Consequences

- Shared contracts stay versioned with service changes.
- Refactoring system-wide flows is faster than across multiple repos.
- CI must test service boundaries explicitly to avoid accidental coupling.
- Production deployment still treats each service as an independent image and release artifact.

