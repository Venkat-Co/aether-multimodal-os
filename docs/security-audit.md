# Security Audit Baseline

## Implemented Baseline

- Secrets and service configuration are separated via environment variables and Helm secrets/config maps.
- Governance rules enforce hard stops for privacy, harmful intent, large transfers, and irreversible actions.
- Audit entries are chained with previous-entry hashes to provide tamper evidence.
- The Helm chart enables strict mTLS posture via Istio `PeerAuthentication`.
- Network policies default to namespace-scoped communication only.

## Remaining Production Work

- Replace placeholder secrets with Vault-injected dynamic credentials.
- Add OPA policy bundles and admission checks.
- Sign and attest container images with SBOM generation in CI.
- Add dependency and container scanning gates.
- Add formal verification hooks for high-risk action templates.

