# Security Policy

## Supported stage

Batalla Medieval is currently preparing a closed beta. Security fixes are made against the current `main` branch and the release SHA active in staging/beta.

## Reporting a vulnerability

Do not publish exploit details, credentials, personal data, cross-account access, or destructive reproduction steps in a public issue.

Preferred reporting path during the closed beta:

1. use GitHub's private vulnerability/security advisory channel for this repository when available; or
2. use the support/security contact configured for the active beta environment (`SUPPORT_CONTACT`).

A report should include the affected release SHA, the impacted feature, observed behavior, expected behavior, and the minimum safe reproduction needed to verify the issue. Never include passwords, JWTs, database credentials, private keys, SMTP secrets, or other users' private data.

## Severity handling

Potential data loss/corruption, credential compromise, unauthorized cross-account or cross-world access, a broadly exploitable integrity failure, or inability to recover the service is treated as P0 until triage proves otherwise.

Critical gameplay/authentication failures, sustained 5xx errors, or severe availability/consistency failures are treated as P1.

P0/P1 findings freeze beta expansion until a fix is versioned, validated, deployed to staging, and verified with the relevant regression tests and operational smoke checks.

## Safe testing

Security testing must use accounts and infrastructure you are authorized to test. Do not access another player's private messages/data, disrupt other users, exfiltrate secrets, or perform destructive tests against production/beta data.

## Disclosure

Please allow time to investigate and remediate before public disclosure. Once a fix is deployed and risk is contained, the project can coordinate an appropriate disclosure summary without exposing user data or reusable secrets.
