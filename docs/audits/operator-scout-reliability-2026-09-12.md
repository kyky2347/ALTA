# Scout and operator-console reliability — September 12, 2026

This review covers the changes after the [earlier same-day release review](release-readiness-2026-09-12.md).
It is a bounded engineering acceptance, not a zero-defect guarantee, a 24×7
uptime certification, brokerage order acceptance or evidence of profitable Alpha.

## Defects addressed

| Finding                                                        | Change                                                                                     | Boundary preserved                                                                |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| Valid intraday timestamps were reduced to midnight             | Normalize only date-only legacy input; preserve RFC3339 time and offset                    | No future event is backdated into eligibility                                     |
| Explore responses invented follow-up lineage                   | Bind generation to the frozen research mode, parent and question                           | Historical parsing and exact assignment validation remain                         |
| Contract failures concealed their actionable cause             | Bounded, allowlisted feedback identifies lineage, horizon, freshness and citation failures | No raw exception or secret is inserted into retry prompts                         |
| A malformed final response restarted research unnecessarily    | At most one same-thread correction with exact retrieved citation choices and a draft hash  | Original deadline, token and outer-attempt caps still apply                       |
| Cumulative App Server usage was summed again across turns      | Use the final monotone cumulative snapshot from the fresh thread                           | Missing or regressing usage fails closed; cached and total usage remain auditable |
| “Current” was underspecified in Scout prompts                  | Prompt v30 receives the exact inclusive four-day event window from the validator           | Refetching an old source does not make its event current                          |
| Language menu could be obscured by fixed UI                    | Shared portalled menu with collision handling, keyboard radio items and bounded height     | All three languages use the same interaction                                      |
| Broker settings mixed execution authority and credentials      | Separate execution/account and connection tabs; one shared six-provider form               | Save does not connect, authorize or submit orders                                 |
| First broker access depended on a preinstalled SDK environment | Locked lazy `uv` setup, desktop PATH fallback and bounded subprocess lifetime              | Credentials pass only through a local pipe                                        |
| One corrupt profile could hide the entire catalogue            | Isolate the damaged profile; keep other providers readable                                 | Do not overwrite the damaged file or expose its contents                          |

Scout defaults are **196,000 chargeable tokens, 420 seconds and 11 research
calls per attempt**, with a 200,000-token / 12-call ceiling. Final structured
output has a 12,000-byte allowance below the durable artifact bound. A correction
needs at least 30 seconds and 20,000 tokens of remaining allowance. Existing
operator overrides remain explicit. Spending is checked at completed-turn
boundaries; this is not a provider-side billing cap or a guarantee of valid output.

## Test acceptance

| Suite                                              | Result         |
| -------------------------------------------------- | -------------- |
| Node gateway, controls, launch and tool contracts  | 303 passed     |
| Research, PostgreSQL integration and SDK contracts | 423 passed     |
| Isolated Tiger Paper                               | 38 passed      |
| Experimental broker package, all extras            | 51 passed      |
| Dashboard contracts and locale parity              | 37 passed      |
| Total                                              | **852 passed** |

The broker tests include all six providers' write-only configuration round trips,
no network call or authority on save, conflict rejection, and corrupt-profile
isolation. These are software tests, not six funded-account trading acceptance.

Research and broker Ruff lint/format, frontend static checks and production build,
Markdown and formatting are publication gates. The source-copy gate uses frozen
Node/Python installs, its own PostgreSQL/Redis ports and no operator credentials.
The same **852 tests passed in the isolated source copy**. Locked installations
and the complete frontend check/build passed there. With its broker virtual
environment removed and PATH restricted, first catalogue access recreated the
locked SDK environment and returned six unconfigured providers in 705 ms using
the local package cache. No account was contacted. The fresh-copy dashboard
returned HTTP 200; its unauthenticated broker endpoint returned 401.

Credential-free demo and replay produced the same hash:
`a60c6c36dd53dff2ba41b6950f4f05e79eac76d5a08e00a42aca1d067ad2527d`.
The deterministic soak passed 14 cycles without manual database repair. Its
23,400 seconds are event time, not a wall-clock uptime claim. The isolated
dashboard, PostgreSQL and Redis were stopped after these checks.

## Real provider verification

Trading was disabled throughout. Massive quote access and discovery were disabled
for the research tests. DeepSeek v4 Flash Scouts used the configured bounded
read-only research tools. Neither the internal test fixtures nor rewritten
research rows are used to populate publication captures.

| Cycle (UTC)                                      | Observed outcome                                                                                                                                  |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `live-20260912-175319-982653`, 17:53:19–18:04:48 | Completed `MVP_IDLE`; Expectation Gap exhausted three attempts before the same-thread and accounting changes. Failures remain recorded.           |
| `live-20260912-180521-435104`, 18:05:21–18:13:47 | Completed `MVP_IDLE`; Change Event hit the old token allowance during finalization. Other three Scouts completed.                                 |
| `live-20260912-181804-192027`, 18:18:04–18:30:30 | All four Scouts succeeded: three Candidates on attempt one, Change Event an explicit no-op on attempt three. No exhausted Scout or cycle failure. |

The last listed cycle still found two stale Change Event drafts. This led to
prompt v30's explicit validator window; it did not justify relaxing freshness or
rewriting the failed attempts. Model output can remain invalid, and insufficient
evidence must still result in an explicit no-op or a recorded rejection.

**Final v30 cycle:** `live-20260912-183120-925065`, 18:31:20–18:43:46 UTC,
completed `MVP_IDLE` with exit 0 and zero consecutive cycle failures. All four
Scouts produced Candidates on their first attempts; none needed an in-context
repair. Four forming Opportunities were persisted. Two reached independent
assessment pairs, each receiving thesis `hold` and countercase `reject`.
One countercase Run completed on its second attempt; this was not a completely
retry-free system run. No new expression or open Shadow position resulted.

| Scout              | Wall latency | Recorded total tokens | Cached input | Chargeable tokens |
| ------------------ | ------------ | --------------------- | ------------ | ----------------- |
| Change Event       | 166.8 s      | 192,726               | 159,360      | 33,366            |
| Market Dislocation | 195.8 s      | 238,388               | 198,016      | 40,372            |
| Causal Policy      | 173.5 s      | 360,646               | 316,800      | 43,846            |
| Expectation Gap    | 140.4 s      | 308,100               | 274,176      | 33,924            |

Recorded token counts include cached context and are not a dollar invoice.
The Candidate event anchors lie between September 8 and 9, inside the exact
four-day policy at the frozen wake. They are **current-policy research**, not
tick-real-time signals or independently proven profitable opportunities.

## Operator workflow and browser scope

- Tested English, Simplified Chinese and Traditional Chinese language switching,
  menu dismissal, provider selection, provider-specific field types, live/Paper
  selection as an unsaved draft, and the model-settings dialog.
- Disabled scheduling is now a distinct operator state, not reported as missing
  telemetry. Running, scheduled, offline snapshots and missing responses remain
  distinct; three additional regression tests cover their precedence.
- Inspected desktop and narrow layouts down to 320px. The smallest header uses
  two rows so branding and controls cannot overlap; 390px keeps the compact row.
- Account identifiers, tokens and RSA keys are write-only. Futu Paper does not
  ask for a live trade-unlock password; Schwab does not offer an invented Paper
  environment. Local gateway ports are not mislabeled API tokens.
- The running research service locks credential changes. Reconnect reloads the
  profile revision before allowing edits. Repeated actions, stale requests and
  late responses cannot silently overwrite a selected provider's form.
- The six-provider operator RPC remains read-only for brokerage operations.
  The current autonomous broker executor is still the separate Tiger Paper
  boundary. No live orders were sent or accepted as part of this review.

## Screenshot provenance

Each README adds broker-connection and model-settings views in its own UI language.
Publication captures use the current production UI and actual local records.
Agent-authored titles remain research hypotheses, not verified investment facts.
Candidate counts and Opportunity counts must not be added as independent trades.

The five views in each language were captured on September 12 after the final
v30 cycle. The overview shows the recent saved library, including repeated
follow-up hypotheses; 41 library rows do not mean 41 distinct opportunities.
The Agent desk shows six latest role snapshots, all completed, rather than
inventing concurrent activity after the cycle ended. The detail view selects
`opportunity_0d76f0c2b5e4c1b24aba4b327edd7766` from
`live-20260912-183120-925065`. That record has no approved expression.
The research API remained connected for inspection with autonomous scheduling
disabled. Model configuration describes the next launch, not the models that
authored existing records. Configuration fields are locked while research is up.

Configuration captures have empty credential fields and do not show account
balances, account bindings, private URLs, tokens or raw provider responses. Failed
research attempts are preserved in history even when a screenshot focuses on
another view. A screenshot hash establishes file identity, not investment merit.

| File in `docs/assets/`           | SHA-256                                                            |
| -------------------------------- | ------------------------------------------------------------------ |
| `alta-agent-desk-en.jpg`         | `00d6545c7e3efde615a830afba870baca9451ab586a9c4a94d89e518c3a6b270` |
| `alta-agent-desk-hk.jpg`         | `b10a1ace42fa6346c0ae36d7428962b3b7903662b0c4ecc711944a8b1dfe1053` |
| `alta-agent-desk-zh.jpg`         | `4ea258f4598aa9aca16d549ee38cd05bf177fe879b719e20483115f9b226726f` |
| `alta-broker-connections-en.jpg` | `c551318f879d6d7955421e5bd6a808c7f1e3f9ffabc126a827419dcfe6bec43c` |
| `alta-broker-connections-hk.jpg` | `7f6ac4bbc658119ef1caf65a9ebde557e67ed95b96336b573b7b4c43fc60c24a` |
| `alta-broker-connections-zh.jpg` | `f06ca04fa8f94250c961b5b798f4252d3f1cbf2ef907083eea7e8a5ce5e171f0` |
| `alta-model-settings-en.jpg`     | `12cda8e94c2c056b9c98ff72a7cf875527b18e424a010d6a57f4fa1514bfdc86` |
| `alta-model-settings-hk.jpg`     | `97a4b98417060ca5884bd130d8db71daec4d7e7d5907261810f62110ef56d9a7` |
| `alta-model-settings-zh.jpg`     | `c8fd8c88d43888c1f5de08d037a747b7974b13dcdc9b92df64ae14ca73888da0` |
| `alta-operator-console-en.jpg`   | `c30054a33799f7cc5c7e3b83556994b3349fc49fc0fe4c30f4f78fbf52799c18` |
| `alta-operator-console-hk.jpg`   | `8eb2625d80a0cd9d2fcbfb4e449c817da69319fce2f74090f71c5a9acd1df070` |
| `alta-operator-console-zh.jpg`   | `eb3dff1b5005fd0ec823e53659f7a365ead04e9a8a8f37e72975e0ecae59e339` |
| `alta-opportunity-detail-en.jpg` | `ab26eed068a16d32e5a80b4cad63f9d1513bb0330b47ff5b1bca78cb53858acf` |
| `alta-opportunity-detail-hk.jpg` | `7d78bbeaa334102326d24cf887518330c5050ac2b793a64a3edf7442989d7355` |
| `alta-opportunity-detail-zh.jpg` | `15c911ecc105f848df6e5b6f35c50981fbc2264432acf13680a0a35578e665b7` |

## Publication and shutdown

- Gitleaks 8.30.1 found no leaks in the complete staged source export or the
  existing 27-commit history. Exact-value comparison against locally configured
  credentials found zero matches across 6,314 source files and 7,088 historical
  blobs. Scanners report findings, not a mathematical guarantee of absence.
- All 15 image hashes and language pairings were checked. Captures were visually
  reviewed and contain no EXIF/XMP payload. No account bindings, balances, API
  secrets or raw provider payloads appear in the publication images.
- The only first-party HTML in the release is the dashboard entry point.
  Private configuration, runtime state and unrelated website material are not
  included. Third-party notices and license files are unchanged.
- The final research service and dashboard were stopped. Their managed host and
  scheduler processes exited; ports 8876, 8877 and the isolated-test port 8897
  had no listeners. The project's PostgreSQL and Redis containers were stopped
  and removed without deleting their persistent volumes. Unrelated applications
  were left running.
- Temporary research-test disables were restored in private configuration only
  after shutdown. The new 420-second deadline and 196,000-token Scout allowance
  remain the local defaults. No service was restarted after restoration.

## Remaining acceptance boundaries

- A short local test cannot establish month-long uptime or all-browser reliability.
- Six connector implementations and profile forms do not prove six real accounts
  can trade. Independent account, permission, order and reconciliation acceptance
  plus research-runner integration remain required before exposing live mutation.
- Provider outages, rate limits and model contract violations can still occur;
  bounded recovery and truthful refusal are the intended behavior.
- No profit, excess-return or Alpha claim is established by this release.
