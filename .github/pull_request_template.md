## Purpose

Describe the problem and the smallest coherent change.

## Architecture and safety impact

- Affected ownership boundary:
- Point-in-time, replay, and idempotency impact:
- Credential, data-license, and capital-boundary impact:
- Failure and rollback behavior:

## Verification

- [ ] `./alta test`
- [ ] Opportunity OS tests, Ruff lint, and Ruff format check
- [ ] Isolated capital-package tests
- [ ] Locked install and relevant clean-clone verification
- [ ] No credentials, account data, licensed payloads, or generated local state
- [ ] Documentation and attribution updated where needed

## Research-only confirmation

- [ ] This change does not add a live-account or real-order path.
- [ ] Performance statements, if any, are explicitly bounded by evidence and sample size.
