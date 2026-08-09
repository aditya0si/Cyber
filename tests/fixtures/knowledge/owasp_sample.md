# OWASP Top 10 (2021) — sample entries (fixture, docs/12 §1)

## A01:2021 — Broken Access Control
Broken Access Control is the top web security risk in 2021. Applications that fail to
enforce authorization properly allow attackers to access unauthorized functions or data,
such as IDOR (Insecure Direct Object References). Prevention: deny-by-default access
controls, enforce object-level authorization, and log access failures.
tags: A01:2021, idor, access control

## A03:2021 — Injection
Injection flaws, such as SQL and NoSQL injection, occur when untrusted data is sent to an
interpreter as part of a command or query. Prevention: use parameterized queries and
prepared statements, apply input validation, and use safe APIs.
tags: A03:2021, sql injection, xss

## A07:2021 — Identification and Authentication Failures
Broken authentication allows attackers to compromise passwords, keys, or session tokens.
Prevention: enforce multi-factor authentication, rate limit login attempts, and do not
ship default credentials.
tags: A07:2021, brute force, auth

## A08:2021 — Software and Data Integrity Failures
Software and data integrity failures relate to code and infrastructure that do not protect
against integrity violations, such as untrusted plugins or malicious packages in the
supply chain. Prevention: verify software provenance, use signed packages, and pin
dependency versions.
tags: A08:2021, supply chain, malicious package
