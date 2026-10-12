# ADR 0003 — Keep prediction calculations pure

- **Status:** Accepted
- **Context:** The prediction engine must be reproducible, testable, and independent of API/database side effects. The LLM must not compute authoritative probabilities.
- **Decision:** Implement scoreline grid and market derivation as pure Python functions. Services will later persist model versions, input snapshots, cutoff timestamps, and evaluation metrics. Return structured insufficient-data/unsupported results instead of fabricated probabilities.
- **Consequences:** Invariants can be tested without credentials or a database. M0 is a baseline only; Dixon–Coles fitting and empirical backtesting remain separate work and no model quality claims are made until measured.
