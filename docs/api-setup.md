# Sports data and LLM setup

## Implemented adapter status
- football-data.org v4 adapter: implemented for competition/team listing, fixture/result date-range retrieval and standings. It requires a server-side API token, validates payload shapes, uses bounded retries with Retry-After support, and applies a short circuit-breaker cooldown after repeated transport failures.
- football-data.co.uk CSV parser and CLI import: implemented for historical final scores. Import validates required columns and score/result consistency, stores a sync-run audit record, and is idempotent for provider fixture IDs.
- Team-name resolver: Unicode normalization, explicit aliases, RapidFuzz candidate scoring, and ambiguous/unmatched outcomes.

## Configure football-data.org
Set PROVIDER_API_KEY in backend/.env. Never expose it as a NEXT_PUBLIC_* variable or commit the value. Use the provider's current official documentation to verify the account's available competitions, endpoints, rate limits and terms before enabling scheduled sync. The adapter has not been tested against a live provider in this build.

The adapter explicitly reports odds, xG, injuries, cards, corners, H2H and news as unsupported where no verified implementation exists. Do not interpret an unsupported capability as an empty successful response.

## Import historical CSV results
Download a CSV from football-data.co.uk according to that site's current terms, then from the backend directory run:

    python -m app.sports.csv_import path/to/results.csv --competition-code E0 --season 2025-2026

The competition code and season label are provenance supplied by the operator. The importer does not infer a competition's display name from the code. CSV rows without a Time value retain their match date but have no kickoff timestamp; the importer does not fabricate one. Do not use date-only records for pre-kickoff prediction timing or live market staleness calculations.

Current importer limitations: cross-provider canonical duplicate resolution is conservative and relies on identical canonical team identities; CSV odds are not imported. The football-data.org sync stores the raw JSON response and content hash in provider_raw_payloads before strict normalization; this hook is active for the sync service, not arbitrary direct adapter calls.

## LLM configuration
LLM provider abstraction and tool orchestration are not implemented yet. Future API keys must remain server-side in environment variables or a secret manager. OCR, news and provider responses are untrusted data. The LLM must not run code or mutate tickets without an explicit confirmation request from the UI.

## UNVERIFIED
No live provider requests, current rate-limit checks, live coverage/licence review, external data import or end-to-end sync has been run in this build. Confirm terms, attribution and quota against the provider's current official documentation before use.
