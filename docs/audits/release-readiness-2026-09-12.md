# Release-readiness review — September 12, 2026

This is a bounded engineering verification of the current application and its
publication set. It is not an uptime certification, brokerage acceptance, legal
opinion or evidence of profitable Alpha. Earlier dated reviews remain historical.

## What changed

The release combines the three-language operator console, stopped-runtime model
and credential controls, experimental broker profiles, expanded read-only research
tools, source pacing and deadline/cancellation work recorded in the changelog.
Application behavior remains outside the attributed Codex vendor tree.

Two additional defects were addressed during real research verification:

1. A rejected Scout response could produce a failure artifact exceeding the
   database's 16,384-byte JSON bound. Failure recording rolled back and aborted
   the whole cycle. A focused `failure_artifact` module now budgets PostgreSQL-style
   escaped JSON bytes, preserves provenance before preview text, and marks
   exceptional truncation with count/hash metadata. A real PostgreSQL regression
   verifies that the terminal failure commits. Valid evidence limits did not change.
2. Models sometimes invented call IDs while citing retrieved URLs. Scout prompt
   v28 and its generated schema now leave IDs empty for binding to actual completed
   calls by exact URL. Historical parsing remains compatible. This improves the
   generation contract; it does not make arbitrary model output valid.

## Verification matrix

| Gate                                                               | Result                                                      |
| ------------------------------------------------------------------ | ----------------------------------------------------------- |
| Node gateway, tools, supervisor and operator controls              | 302 passed                                                  |
| Research application with isolated PostgreSQL test databases       | 399 passed                                                  |
| Isolated Tiger Paper package                                       | 38 passed                                                   |
| Experimental broker contracts, all optional dependencies installed | 44 passed                                                   |
| Dashboard contracts and three-language catalog parity              | 33 passed                                                   |
| Total                                                              | **816 passed**                                              |
| Research Ruff lint/format                                          | Passed; 163 files                                           |
| Broker Ruff lint/format                                            | Passed; 18 files                                            |
| Prettier, Markdown, Oxlint, TypeScript, production frontend build  | Passed                                                      |
| pnpm complete dependency advisory check                            | No known vulnerabilities returned after the follow-up below |

The 816 tests also passed from an isolated source export containing no development
runtime state or provider credentials. Locked pnpm installation, managed Python
3.12.13 setup and the isolated broker/capital installations succeeded there.
The test copy used its own Compose project and explicit free ports because the
operator's default ports were already occupied. Port collision was reported, not
silently redirected to another database. See [Reproducibility](../../REPRODUCIBILITY.md).

A bare research `pytest` without `DATABASE_URL` first reported fixture setup
errors. The complete accepted command was `./alta env python -m pytest`, which
supplies the managed environment. The README now makes this prerequisite explicit.

The credential-free `demo` and `replay` commands produced the same replay hash:
`a60c6c36dd53dff2ba41b6950f4f05e79eac76d5a08e00a42aca1d067ad2527d`.
The deterministic market-session soak passed 14 cycles with no manual database
repair. Its 23,400 seconds are **event time**, not a 6.5-hour wall-clock uptime test.
These fixtures were confined to the isolated verification database and were not
used for the README screenshots.

## Actual research, not an investment-performance claim

Trading authorization was disabled before verification; the Paper account's
read-only snapshot showed zero positions and zero open orders. Massive quote
access and the autonomous scheduler were disabled for this bounded check.
Two explicit one-shot research cycles used real configured model/retrieval
providers. The managed HTTP service exposed the saved records for inspection.
No broker order was submitted, and no open Shadow position existed.

| Cycle (UTC)                                      | Result                                                                                                                                    |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `live-20260912-161812-579779`, 16:18:12–16:23:43 | Failed with the oversized failure-artifact constraint; one Candidate persisted. Recovered stale work later reached a terminal state.      |
| `live-20260912-162913-222228`, 16:29:13–16:43:50 | `MVP_IDLE`, exit 0, zero consecutive cycle failures; one Candidate became a forming Opportunity and received two independent assessments. |

Final-cycle facts:

- Market Dislocation Scout: Candidate, first attempt, DeepSeek v4 Flash.
- Causal Policy Scout: valid abstention, first attempt, DeepSeek v4 Flash.
- Change Event and Expectation Gap Scouts: rejected after three attempts each.
  Diagnostics include schema validation, output-byte and freshness refusal.
- Thesis Assessor: DeepSeek v4 Pro, `hold` / further research.
- Disconfirming Assessor: Grok 4.6, `reject`.
- No new rank, expression, Shadow position or broker order. The process completed
  correctly by waiting; this is not a completed profitable trading lifecycle.

The new record is `opportunity_b9165f89cdd49dcb009523dd99df9818`, known at
16:31:36.981854 UTC, `forming`, `limited` investability. It brought the recent
registry to **7 distinct Opportunity records**. The library showed **15 records**
when Candidates were included; Candidates and their resulting Opportunities are
not independent trades. Titles and numeric thesis claims are Agent-authored
research hypotheses, not independently verified market facts or recommendations.

The default Scout budget is 11 calls, 98k budget-counted tokens and 300 seconds
per attempt. Recorded model tokens include cached input and are not an invoice.
Budgets do not entitle a response to pass freshness, evidence, risk or audit gates.

## API and browser observations

- Liveness, readiness, runtime, summary, MVP status and two durable Opportunity
  detail endpoints returned HTTP 200. Sample local response times were 0–44 ms;
  this small read-only sample is not a load-test SLA.
- An unauthenticated runtime request returned 401. The temporary probe server
  was terminated and its socket verified closed.
- The current runtime reported prompt v28 and research tool catalog v11.
- English, Simplified Chinese and Traditional Chinese navigation, record viewing,
  language switching, configuration and model-dialog opening were exercised.
  While research was active, credential changes and model saving were locked.
  The credential page contained no populated password field.
- Browser capture tooling initially produced stitched/cropped rendering artifacts.
  Those images were rejected. Publication images use verified native viewport or
  focused section captures, not edited status labels or rewritten research rows.

## Screenshot provenance

The nine images were captured from the current production-built console connected
to the operator's actual research database on September 12, 2026. Interface labels
match each README language; original Agent artifacts retain their authored language.
No model prompt, credential form, account page, bootstrap URL or raw provider
response is photographed. PNG text/EXIF chunks are absent.

The workspace images focus on recent research cards; reviewer images focus on
the two independent assessments and saved handoffs; detail images open
`opportunity_56059a51f1d8fe44739ea50209ab8313` (known at 15:57:26.411170 UTC).
That older same-day hypothesis had a thesis `hold` and countercase `reject`.
The reviewer snapshots instead belong to the final cycle's newer Opportunity:
`run_a462ec38df794a8c1343a83c6d6ef12a` and
`run_0105446d181908c64ac1e35983c66acc`. Do not join them to the detail record.

These are scoped product views, not a claim that every Agent succeeded. Failed
attempts remain in the database, visible in activity history and documented above.
Image hashes identify the exact publication files; they do not establish the truth
of an investment thesis. Audit records and licensed source responses stay private.

## Publication safety

### Image manifest

| File in `docs/assets/`           | SHA-256                                                            |
| -------------------------------- | ------------------------------------------------------------------ |
| `alta-agent-desk-en.png`         | `0d9e4ca5da3e6ca73f41fce391b29da421d90cee0aa8ae83f718738ae5f62467` |
| `alta-agent-desk-hk.png`         | `896754840a065a0427079bdac0734e16651e901a80f8f111e13f985fde0b9a4e` |
| `alta-agent-desk-zh.png`         | `0166407900100a36c5a13f21be5756baf3fd9de4432cf0c064ab3d8bc328bc3c` |
| `alta-operator-console-en.png`   | `1cec60640ded99d1757d245bff539c6cd9b28c154d2764891f31e4aacadf0e6e` |
| `alta-operator-console-hk.png`   | `2b37ad69b74f662b9c8a282a0a0ccc9ec86cd51b403d6647bc395122828aec50` |
| `alta-operator-console-zh.png`   | `db004af2b177f6c792a2b7425428e147d3327e7405c502e26d5bf1758afd3173` |
| `alta-opportunity-detail-en.png` | `f41fdb76f7b6c88cd8aa855d21ce6ee67ee5b77ea31972adea14dc8c57b4a3fd` |
| `alta-opportunity-detail-hk.png` | `8c1af4141f4649fe090b0e83a189bebf5f57f59c2a4c1c366247f33dba67fe5b` |
| `alta-opportunity-detail-zh.png` | `1facbefa5225ec115516b0461c4ff669e7b332906ec7260af240722165711aa6` |

### Source and history scans

Gitleaks 8.30.1 found zero findings in the complete available history (24 commits
before this release) and source-only export. The existing narrowly reviewed
upstream test-fixture allowlist was retained; no broad vendor exclusion was added.
An independent exact-value comparison loaded 9 local credential values in memory
and scanned 6,298 source files plus 7,073 historical blobs (109,757,610 bytes),
with zero matches. Secret values were neither printed nor written to reports.

Generated state, databases, logs, virtual environments, dependency/build output,
external credentials, and the unrelated `output/` and `showcase/` website material
are outside the publication set. Only the canonical ALTA repository is in scope.
`LICENSE`, `NOTICE`, upstream headers and the vendored change record are retained;
the attribution file identifies separately licensed dependencies and API targets.

Scanner results are bounded evidence. They do not prove that an unknown secret
format, private remote reference, external account or future change is safe.

## Remaining limits and next priorities

1. Improve compact structured-output compliance and primary-source coverage:
   two Scouts still exhausted retries. Do not solve this by accepting stale or
   unbound evidence, inflating output caps indefinitely or suppressing failures.
2. Validate hypothesis quality with prospective, cost-adjusted outcomes and
   holdout evaluation. Neither record count nor eloquent reasoning proves Alpha.
3. Conduct measured multi-day endurance, network interruption, host reboot and
   realistic concurrent-user tests. Unit recovery tests are not institutional
   availability certification, and physical Safari/Firefox/mobile QA remains.
4. Finish separate broker account acceptance and runner integration before any
   broader execution claim. Five providers are pre-adapted; new live connectors
   and real-account execution are unaccepted. No such order was tested here.
5. Rebuild the pinned Rust harness on each target platform for distribution
   acceptance. This review exercised the existing local harness; it did not
   rebuild the unchanged vendor tree from scratch.

## Final release-candidate and shutdown checks

Release candidate `7cbe3ae` was cloned locally with `--no-hardlinks`. Frozen pnpm
and all three frozen Python installations passed; the clean clone's full
format/lint/TypeScript/production-build gate also passed. All 419 non-documentation
application files matched the separately tested source export byte for byte.
A second fresh clone, with no copied dependencies or runtime state and an empty
external credential directory, launched successfully with `npm run dashboard`.
The command prepared its dependencies and production build, served an authenticated
loopback console and exposed first-run controls. It did not start research or
connect a broker on its own. Both clone worktrees remained clean.

The exact staged source export passed Gitleaks before the candidate commit.
The post-candidate full-history scan covered 25 commits with zero findings.
Exact local-secret comparison covered 6,299 working files and 7,098 history blobs
with zero matches. Commit identities were public no-reply identities, including
GitHub's platform committer. Final publication adds verification documentation,
not an untested application change, and receives another full-history scan.

The operator's actual **Stop safely** action reported **Stop complete**. Independent
checks confirmed the host and scheduler stopped, port 8876 closed, and managed
PostgreSQL/Redis stopped. The dashboard retained a clearly labeled last snapshot
instead of presenting it as live. Its foreground process was then terminated,
closing port 8877. The isolated test Compose project was also stopped.
The temporary cold-start dashboard was terminated after verification.

No ALTA research, App Server, supervisor or dashboard process was intentionally
left running. Browser verification tabs were closed and viewport overrides reset.
Unrelated applications and containers were left alone. Durable research data and
external credentials were retained. Trading authorization remains **disabled**;
the temporary research/market-data test overrides were restored for the next
operator-initiated start. No broker order or new position was created by this review.

The model dialog remained inside 390×844, 768×1024 and 1440×1000 viewports after
layout settled. This is bounded Chromium coverage, not every browser/device test.

## Post-publication dependency follow-up

Both CI jobs passed for `147655a`. GitHub then reported five dependency alerts:
the initial production-only pnpm audit had missed packages introduced by the
shadcn and Markdown development tools. The gap was confirmed with a complete
dependency audit, not dismissed as irrelevant because the packages were indirect.

| Package     | Resolved patch  | Advisory                                                                                                                                                                                                  |
| ----------- | --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Hono        | 4.13.3 → 4.13.5 | [SSG traversal](https://github.com/advisories/GHSA-gqvv-2mrq-wpjv), [body parsing](https://github.com/advisories/GHSA-g6gw-c38x-mqfc), [query parsing](https://github.com/advisories/GHSA-crvj-82cr-hjcx) |
| js-yaml 4.x | 4.3.1 → 4.3.2   | [merge-source CPU exhaustion](https://github.com/advisories/GHSA-2883-xcg3-v3hh)                                                                                                                          |
| smol-toml   | 1.7.0 → 1.7.1   | [malformed-document denial of service](https://github.com/advisories/GHSA-7w5x-hrqm-74c2)                                                                                                                 |

The unaffected js-yaml 5.2.2 route was preserved. Narrow major-version overrides
and exact patch release-age exceptions leave the general seven-day quarantine,
integrity locks and publisher-trust policy enabled. The complete
`pnpm audit --audit-level=moderate` now returns no known vulnerabilities. CI and
the release contract run that full-graph gate; neither production-only filtering
nor audit-service error suppression is used.

The 302 Node and 33 dashboard tests passed again after patching, along with frozen
installation and the full format/lint/TypeScript/production-build gate. Research,
capital and broker application code and their lockfiles are unchanged from the
816-test verification. A fresh export of the exact staged source repeated the
frozen install, full advisory audit, 335 Node/dashboard tests and frontend build
successfully. Its 27 production output files match the screenshot build byte for
byte; these development-tool patches do not introduce an uncaptured UI version.
These are dated advisory results, not a guarantee that future vulnerability
reports or other ecosystems are clear.
