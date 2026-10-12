# Sports data and LLM setup

## Current status
Provider adapters and LLM orchestration are not implemented yet. No live provider behaviour has been verified. Do not add API keys to frontend variables or commit them.

## Planned sports-data providers
- football-data.org: use its official API and check the current competition coverage, rate limits, terms and data licence before enabling it.
- football-data.co.uk: historical CSV import for results and odds; review the current site's data-use terms and source attribution requirements before redistributing imported data.
- Optional API-Football adapter: only after current coverage, quota and licence terms are checked.

The application will store raw provider payloads with hashes, validate records before normalisation, track sync runs and enforce configurable request budgets. Unsupported provider capabilities must be returned explicitly, not represented as empty successful data.

## LLM configuration
A server-side provider abstraction is planned. API keys must be environment variables or secret-manager values available only to the backend. OCR, news and provider responses are untrusted data. The LLM cannot run code or mutate tickets without an explicit confirmation request from the UI.

## UNVERIFIED
Current API coverage, rate limits, prices, quotas, provider licence interpretation and live connectivity have not been verified in this build.
