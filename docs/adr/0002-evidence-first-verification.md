# ADR 0002 — Evidence-First Verification

- **Status:** Accepted
- **Date:** 2026-10-12

## Context
The project must not claim features, tests, model performance, live integrations or deployment success without real evidence. External sports-data and LLM credentials may be unavailable.

## Decision
Record each command and its actual result in `docs/VERIFICATION_LOG.md`; generate `docs/TEST_REPORT.md` from executed test results; mark inaccessible live integrations UNVERIFIED with a reason. Use deterministic fixtures and mocks in CI. Never invent model metrics, probabilities, odds, provider payloads or booking-code confirmation identifiers.

## Consequences
- Documentation must distinguish implemented, executed, and live-verified states.
- Missing credentials block only live integration verification, not mock-based adapter development.
- Model reports must come from reproducible historical backtests and disclose benchmark comparisons and uncertainty.
