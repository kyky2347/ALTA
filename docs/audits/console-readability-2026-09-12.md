# Console readability and publication review — September 12, 2026

This is a bounded UI and documentation acceptance. It does not certify all
browsers, uninterrupted operation, broker execution or investment performance.
Research scheduling and capital execution were disabled during this review;
no research cycle or order was started for screenshots.

## Reproduced defects and repairs

| Finding                                                                           | Repair                                                                        | Verification                                                          |
| --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| At 320 × 480, the model editor left only 39 px for its fields                     | Put notices, fields and guidance in one scrollable body; keep actions outside | 256 px available, two reachable 44 px actions                         |
| At 320 px wide, the detail header began at y=130 under navigation ending at y=160 | Account for the narrow two-row header when scrolling to a record              | Detail header at y=174; close action visible                          |
| A long opportunity title consumed the fixed part of the inspector                 | Scroll the title with its record, keeping navigation tabs outside             | Full title remains available without crowding out the record viewport |
| Selecting another record retained the old tab and scroll position                 | Key the detail tabs by the entity endpoint                                    | Record → select another opportunity returns to Brief                  |
| Long record IDs clipped without a useful ellipsis                                 | Allow the badge to shrink and truncate its inner text                         | Full ID remains in the title and saved record                         |
| Closing the model editor silently lost unsaved changes                            | Confirm close and reload in an accessible in-app alert dialog                 | Keep editing preserves the draft; discard reloads saved settings      |
| Native confirmation blocked the embedded-browser test                             | Replace native confirm for both model-editor actions                          | No browser-native confirmation needed in the repaired flow            |
| A malformed settings response could break rendering                               | Validate transport shape before installing editor state                       | Missing roles, malformed overrides and invalid envelopes rejected     |

Semantic model errors remain editable but cannot be saved. Provider access is
not inferred from a syntactically valid model ID. Existing independent-review,
credential and broker-authorization boundaries are unchanged.

## Verification

| Check                                          | Result                            |
| ---------------------------------------------- | --------------------------------- |
| Node application                               | 303 passed                        |
| Research service, with managed PostgreSQL      | 423 passed                        |
| Isolated Tiger Paper                           | 38 passed                         |
| Isolated broker contracts                      | 51 passed                         |
| Dashboard contracts                            | 41 passed                         |
| Total                                          | **856 passed**                    |
| Research Ruff lint and format                  | Passed                            |
| Frontend lint, TypeScript and production build | Passed                            |
| Markdown and first-party formatting            | Passed                            |
| Locked dependency vulnerability audit          | No known vulnerabilities reported |

The browser pass covered the seven main sections on desktop and phone layouts,
all three language choices, long opportunity records, short-window forms,
record switching and unsaved model edits. Tested viewport sizes included
1440 × 960, 390 × 844, 320 × 480 and 844 × 390. No document-wide horizontal
overflow was found in the inspected sections. This is not a Safari or Firefox
compatibility claim. The final model-discard check used a temporary local draft
and did not save or change the operator's model assignments.

## README and screenshot scope

All three introductions now explain the four research specialisms, how a thesis
differs from its trade expression, where to inspect decisions, system ownership
and first-session expectations. Diagrams carry the workflow and architecture;
technical parameters and longer procedures remain linked rather than duplicated.
Approximate narrative-character growth, excluding diagrams and links, is 58%
for English, 53% for Simplified Chinese and 54% for Traditional Chinese.
The obsolete 816-test summary was replaced with links to the dated acceptances.

The fifteen publication images were recaptured from the production console.
Research views show real saved records from the September 12 session, not newly
running Agents. In particular, 41 library rows include both candidates and
follow-up hypotheses; they are not 41 independent approved opportunities.
The detail images inspect `opportunity_0d76f0c2b5e4c1b24aba4b327edd7766` from
`live-20260912-183120-925065`. Its hypothesis is not a verified investment fact
or an approved trade. Agent-authored text keeps its original language.

Broker forms show empty fields, never balances, account bindings, API secrets
or provider response bodies. The Traditional Chinese broker view was captured
after safe research shutdown, with the stopped-state notice visible. Earlier
views show a connected research API with autonomous scheduling disabled.
No record, failure state or account information was altered for a capture.

The image hashes below identify this UI revision. Historical hashes in the
[earlier review](operator-scout-reliability-2026-09-12.md) refer to its earlier
release, not the images replaced in this update.

## Release boundary

| File in `docs/assets/`           | SHA-256                                                            |
| -------------------------------- | ------------------------------------------------------------------ |
| `alta-agent-desk-en.jpg`         | `40ede95bd165edbdea43b3be6a195c2f64025505be9dd65d9e92ec666273e9b2` |
| `alta-agent-desk-hk.jpg`         | `fb83a0ad6740229f4e874a5bc66316f84cd6fde6b19992369a8f8c2c41cde699` |
| `alta-agent-desk-zh.jpg`         | `f953d25142a3295ad35cba1b0b1c88c0b132d36139dd3c26971d94049e32d330` |
| `alta-broker-connections-en.jpg` | `ddc977b72b246cd228283e405d9434bc5747bdf89982b7cac11cb8abcb782b14` |
| `alta-broker-connections-hk.jpg` | `1a10eba2732f82e0e8553d5edb72fa9808ba713c726f0b135e8ea3deae09cfb5` |
| `alta-broker-connections-zh.jpg` | `23390d7a2e39288c8e5a565800ba2e3641173d39a647081dea0065cf29274264` |
| `alta-model-settings-en.jpg`     | `c2271d98a1f2e61894d2cb35fc21b86e2900248d237c29a55679746594f77412` |
| `alta-model-settings-hk.jpg`     | `a27a345694eec82af07ab6d2bf23532d8452a1798f2c0279686dc1349da43435` |
| `alta-model-settings-zh.jpg`     | `5c6656877abca427c7fbfc1b4cb406babd4667fbb16918243c94610176444bf6` |
| `alta-operator-console-en.jpg`   | `9b09f65c7badd38bafbdad520ded9639f4a1870ba8765cd16ddddefbe6399b40` |
| `alta-operator-console-hk.jpg`   | `7f80acb22afe7c0bac0c033d54099682816ff3e76e02d5c6a7ecb425543b9334` |
| `alta-operator-console-zh.jpg`   | `097dc22b97e04c5f7d0fc89f60d2511f01762534b24157e3c88d34a0001a958b` |
| `alta-opportunity-detail-en.jpg` | `96bfd188f02d1b4c2eaad3513ba29f8d2079da81370d71ffecc3d870164edc7f` |
| `alta-opportunity-detail-hk.jpg` | `4ae96f0eee961378cf2ad23e3500bd2262b670d14fba7e546e0c81cf53879313` |
| `alta-opportunity-detail-zh.jpg` | `8936e8e2d935d2740342a54fedf52e3c2ffabd21ec38a8410a0274afb505fc9f` |

No EXIF or XMP payload was found in these captures.

Only first-party console changes, tests, documentation and the fifteen reviewed
images are in scope. The sole first-party HTML is the dashboard entry point.
No unrelated website HTML, hosting configuration, local runtime state or
credentials belong in this release. Third-party source and license notices
are unchanged. Secret scanners reduce risk; they cannot prove absolute absence.

The research service and dashboard were stopped, with their host and scheduler
processes gone and no listeners on ports 8876 or 8877. Managed PostgreSQL and
Redis were stopped and removed without deleting persistent volumes. Unrelated
applications were left alone. Temporary scheduling overrides were restored only
after shutdown; no service was restarted afterward.
