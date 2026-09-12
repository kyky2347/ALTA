# Model routing and three-language console review

Local verification: September 12, 2026. This is a bounded engineering review,
not an availability certification, security guarantee or investment result.

This records an earlier verification on the same date. The current nine-image
publication set and expanded gate supersede its capture count; see the
[September 12 release review](release-readiness-2026-09-12.md).

## Changes and boundaries

- A responsive Silment / ALTA lockup uses the existing wordmark unchanged.
- English, Simplified Chinese and Hong Kong Traditional Chinese share 604
  message keys. Catalog and interpolation parity are tested. Dates, numbers,
  statuses, accessibility labels and the document language follow the choice;
  original Agent artifacts remain unchanged.
- Seven operator-owned role routes and four optional Scout overrides persist
  atomically. Writes require a local session, same origin, CSRF, a matching
  revision and a stopped research host. The shared host lease prevents a
  concurrent process from starting research during a configuration write.
- Debate and audit independence remain enforced. Each Scout's provider/model
  is frozen in its run specification before dispatch, including saved metadata.
  Unconfigured routes fail explicitly; they do not silently choose another model.
- Model settings cannot change brokerage authority or introduce live trading.

## Verification

| Check                                                       | Result                                                                                                           |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| First-party Node gate                                       | 206 passed                                                                                                       |
| Python research runtime, isolated PostgreSQL                | 389 passed                                                                                                       |
| Isolated Paper package                                      | 38 passed                                                                                                        |
| Dashboard tests                                             | 25 passed                                                                                                        |
| TypeScript, lint, formatting, Markdown and production build | Passed                                                                                                           |
| Browser model save and full-page reload                     | Position and individual Scout choices persisted through the real operator API in a temporary configuration store |
| Validation and concurrency                                  | Same-model challenge blocked; stale revision returned 409 and retained the draft                                 |
| Uncertain network write                                     | Browser retained the draft and did not claim success or retry the mutation                                       |
| Responsive settings                                         | Dialog remained within 320, 390, 768, 1024 and 1600 px viewports in Chromium                                     |
| Language selection                                          | Exactly three choices; English, Simplified and Traditional selection and reload verified                         |

The first Python run lacked a test database and encountered setup errors.
The successful complete run used a separately created PostgreSQL container,
not the running research database. Browser mutation tests used a temporary
operator and configuration directory; no real service configuration was changed.

The documentation captures show the current console reading the existing
research service and its durable history. All 15 images use the corresponding
interface language. Wait, historical and failed states remain visible where
recorded. Screenshots are not evidence of profitable trading.

## Security and deployment checks

Offline Gitleaks 8.30.1 scans found no secrets in a snapshot of 6,239 tracked
and first-party untracked files, or in all 24 locally available Git commits.
The snapshot excluded private ignored runtime state, local output and showcase
directories. Scans used the repository's existing reviewed upstream-fixture
allowlist, no network access and redacted output. Screenshot review checked
visible content for credentials and account information; no API or brokerage
credential pages were captured. This is a bounded scan, not proof that any
arbitrary external file or unobserved remote reference is free of secrets.

Only the managed dashboard was refreshed to load the new operator route.
The pre-existing research host and scheduler stayed running, and their Paper
authority was not changed. Temporary browser contexts, the verification
operators and their configuration directories, and the isolated PostgreSQL
container were cleaned up after verification. No GitHub operation was performed.

## Remaining limits

- Saving validates route structure and independence, not provider entitlement.
  A valid model ID still needs an accessible provider account. No new paid
  model route or brokerage order was invoked to make this review pass.
- Existing running research retains its startup configuration. Changes are
  intentionally applied only on the next research-service start.
- Hong Kong written-Chinese copy was editorially reviewed, but native-speaker
  usability research and physical Safari/iOS/Firefox testing remain useful.
- Unit tests and a bounded browser session do not establish multi-day
  availability, every power-loss scenario, or institutional certification.
- Historical role records can predate the current research cycle. They must
  not be interpreted as current-cycle approvals or active trades.
