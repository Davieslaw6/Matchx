# ADR 0004: Current stable frontend toolchain

- Status: Accepted for the implementation branch; compatibility remains unverified.
- Date: 2026-10-12

## Context
The project requirement is to use current stable tooling rather than remain on the original Next.js 15 / React 19.0 / TypeScript 5.8 package ranges. Runtime support should favour an actively supported LTS release for local use and deployment.

## Decision
- Next.js 16.4 package range.
- React and React DOM 19.3 package ranges.
- TypeScript 7.0 package range.
- Node.js 24 LTS for CI and documented local setup.
- Keep the product specification's Python 3.12 and PostgreSQL 16 baseline for now; upgrade these separately after dependency and deployment compatibility review.
- Keep npm dependency ranges on supported major versions and require install, lint, typecheck, tests, production build and audit checks in CI.

## Consequences
- The framework/toolchain is aligned with official releases available on the decision date.
- A fresh dependency install and Next.js 16 / TypeScript 7 compatibility test are required before this branch can be considered runnable.
- CI audits are blocking gates; do not bypass reported high/critical dependency advisories to obtain a green build.

## References
- Next.js 16.4 release: https://nextjs.org/blog
- React 19.3 release: https://react.dev/blog/2026/09/09/react-19-3
- TypeScript 7.0 announcement: https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/
- Node.js supported release lines: https://nodejs.org/en/about/previous-releases
- Next.js announced security update schedule (check current advisories before deployment): https://nextjs.org/blog
