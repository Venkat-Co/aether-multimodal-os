# Benchmark Plan

## Service-Level Targets

- Fusion P99 latency under 500ms
- Reasoning P99 latency under 2s
- Governance P99 latency under 10ms
- Memory query latency under 100ms for 1M nodes

## Validation Approach

- Unit tests for algorithm correctness
- Integration tests using TestClient and Testcontainers
- Load tests with Locust against the ingestion and reasoning APIs
- Chaos testing via Chaos Mesh once the cluster deployment is in place

## Current Gap

The scaffold in this repository is designed for those tests but does not yet include load generators, historical datasets, or GPU-backed model-serving benchmarks.

