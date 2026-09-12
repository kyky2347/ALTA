# Local operator console

The ALTA operator console is a loopback-only control and observability surface
for the Shadow research runtime. It combines a live opportunity topology with a
chronological decision ledger so an operator can see both what the system is
doing and how it reached the present state.

It is research infrastructure. It is not an order-management system, a broker
terminal, an Alpha claim, or a way to expose private model chain-of-thought.

## Open with one command

```shell
./alta dashboard
```

This is the normal path on both an existing workspace and a fresh clone. It
performs a frozen-lockfile frontend install/build only when output is missing or
stale, binds to `127.0.0.1:8877`, and opens its one-time launch URL in the
default browser. If that port is occupied and no explicit `--port` was supplied,
it selects a free loopback port. The hand-off creates an HttpOnly,
`SameSite=Strict` local session and redirects to a clean address. Keep the
command running; `Control-C` stops only the control plane and does not
implicitly stop an autonomous research service.

`./alta` is a file in the repository, so a shell can resolve that short form
only from the repository root. From any other directory, use the portable
path-qualified command:

```shell
npm --loglevel=error --prefix "/absolute/path/to/ALTA" run dashboard
```

For a new checkout and first launch, one line is sufficient:

```shell
git clone https://github.com/kyky2347/ALTA.git ALTA && npm --loglevel=error --prefix ALTA run dashboard
```

Node.js 22+ with npm, `uv`, and a running Docker Compose-compatible engine
remain host prerequisites. The command never installs those system
dependencies silently. It uses Corepack when present and otherwise bootstraps
the lockfile's pinned pnpm version through npm.

An optional managed console can instead start after user login and recover
through the host service manager:

```shell
corepack pnpm install --frozen-lockfile
pnpm dashboard:build
./alta dashboard install
./alta dashboard open
```

The managed `open` command opens its one-time launch URL in the default browser
(or prints it when no graphical launcher exists). That URL is stored
only in an owner-only atomic host-state file, is never printed by the background
process or written to its logs, and is removed from that file after it is
claimed.

Use the managed lifecycle commands for routine operation:

```shell
./alta dashboard status
./alta dashboard logs
./alta dashboard restart
./alta dashboard stop
./alta dashboard uninstall
```

An already authorized browser reconnects after a managed-process restart. If a
new browser needs access after the one-time link was claimed, restart the
dashboard and run `./alta dashboard open` for a fresh link.

Alternate loopback ports are supported by foreground mode:

```shell
./alta dashboard --host 127.0.0.1 --port 8890
```

Non-loopback bindings are rejected. Use `--no-open` only for headless or
automated operation.

## What each view shows

The sidebar uses **API Trading**. Its current operational adapter is Tiger Paper;
five additional providers are pre-adapted, not live-account accepted. The two
autonomous execution modes remain internal Shadow and authorized Tiger Paper.

**API Trading** separates **Execution & account** from **Broker connections**.
The latter is also available inside **API connections**, alongside—not mixed
into—the research/data provider inventory. Both entrances use the same form and
validation.

Select a broker, explicitly select the account environment, and enter its exact
account binding plus the fields required by that provider. Gateway-backed brokers
need gateway configuration; OAuth brokers need current OAuth tokens; RSA
credentials use a multiline secret field. A generic key is not a substitute for
these protocols. Saved credentials are write-only. Switching broker clears
unsaved secrets, and running research locks credential replacement.

**Save connection** stores the profile without enabling trading. **Verify
connection** is a separate, explicit read-only account request. The experimental
six-provider boundary does not expose order submission or live authorization in
this console. Tiger Paper execution remains separately account-bound and audited.
Selecting a different execution mode displays its confirmation; an already-saved
mode does not ask the operator to apply it again.

Opening broker configuration prepares the isolated SDK environment from its
lockfile using `uv`, even before the research backend has started. The first
opening needs package-network access and may take longer. A bounded timeout or
offline error keeps editing disabled and offers a reload; it does not silently
discard profiles. A damaged provider profile is isolated so the other five
remain inspectable, but replacing the damaged file is deliberately blocked.

**Research radar** shows separate Opportunity and Candidate records with a
seven-day or full-snapshot scope, search, pagination, timestamps and evidence
inspection. The snapshot is bounded; use Activity & history for earlier events.
No record is promoted or made fresh by changing a view.

Local builds retain content-hashed frontend assets so open tabs can still load
their lazy modules after an update. Stop the console and close old tabs before
manually cleaning build output. Vite and TypeScript configuration changes also
invalidate the startup build check.

- **Live field** — Candidates, deduplicated Opportunities, active Agent roles,
  committee state, expression, audit, and Shadow observation in one flow.
- **Decision ledger** — Cursor-ordered durable events with their aggregate,
  timestamp, public summary, selected-record hand-off, in-view filtering, and
  backward pagination to older history.
- **System overview** — Current source posture, object counts, Trader Mind
  memory summaries, append-only event cursor, and a bounded Research Operations
  audit. The audit shows recent saved retrieval counts, independently frozen
  evidence records, independent domains, four-role evidence coverage,
  cross-checked runs, source-role reuse, and failed routes per Mind;
  it never exposes credentials, query arguments, source text, hidden prompts,
  or private reasoning.
- **Agent desk** — Latest Run per role, actual model route, durable mind summary,
  turn count, context usage, latency, and Run details.
- **Shadow book** — Research-only open and closed Shadow positions plus the
  forward evidence ledger: comparable-sample maturity, confidence interval,
  forecast error, directional calibration, downside-only forecast reserve, and
  the tightest evidence-driven capital posture. An observed-lifecycle panel
  separately shows favorable/adverse excursion, drawdown, exit capture, and
  missed positive paths using only prices captured while positions were open.
  A separate execution-quality panel shows realized versus estimated round-trip
  cost, budget variance, budget hit rate, open-fill reliability, and the current
  same-carrier empirical Alpha reserve. Both panels are explicitly separated
  from brokerage, cannot auto-tune execution, and never label Shadow evidence
  as proven performance.
- **Capital desk** — The durable Tiger Paper authorization gate, exact-account
  and configuration fingerprints, explicit broker snapshot refresh, sanitized
  assets, positions, recent orders, and the bounded authorization audit. It has
  no manual order-entry surface and no live-account path.
- **Credentials** — Safe configuration state for every supported external
  token slot, grouped by model, market data, news, and research. Secret values
  are write-only and replacement is available only while the complete research
  runtime is stopped. Tiger credentials remain external and owner-only; the
  browser shows only safe configuration and authorization posture.
- **Inspector** — Opportunity packets, independent assessments, committee
  arguments, frozen Run inputs, tool provenance, artifacts, implementation
  plans, hashes, and normalized JSON records.
- **Replay ribbon** — A draggable event playhead with play, pause, timestamp,
  cursor, replay state, and a direct return to the live edge.

Use `Command-K` (or `Control-K`) to search across loaded Candidates,
Opportunities, Agent Runs, assessments, committee exchanges, expressions,
Shadow positions, and events.

Use the language button in the global action bar to switch the entire operator
shell between English, Simplified Chinese and Traditional Chinese
(**繁體中文**). The preference is stored only in
local browser storage and survives reloads. Static copy, dates, relative time,
numbers, status codes, accessibility labels, controls, failures, and empty
states follow the selected locale. Durable Opportunity titles, Agent summaries,
committee arguments, recommendations, and artifacts remain in their original
saved language; the console does not mutate or invent a translated audit
record.

## Assign Agent models

Open **Agent desk → Agent models**. The seven routes cover the default Scout,
thesis, independent challenge, moderator, expression, audit and position review.
Each of the four Scout minds can override the default route independently.
Select OpenAI, DeepSeek, xAI / Grok or Moonshot / Kimi and enter an exact,
provider-compatible model ID available to your account. Configure its credentials
separately in the API view. Saving does not probe model availability or spend tokens.

- Stop research before saving. Running or recovering processes, lifecycle actions,
  credential verification and capital changes block conflicting model edits.
- `GET /control/agent-models` returns the safe settings and a revision;
  `PUT /control/agent-models` requires the session, same origin, CSRF and that revision.
- The operator stores versioned settings in its owner-only
  `config/agent-models.json` state file using atomic replacement and a write lease.
  Concurrent edits return a conflict, not last-writer-wins data loss.
- The next research-service start loads the selected routes. Each Run retains its
  provider and model before dispatch. Unconfigured Scout overrides inherit the
  default; unavailable routes are never silently redirected.
- Thesis and challenge must differ, as must expression and audit. Broker permissions,
  capital isolation, research budgets and evidence requirements are unchanged.
- A corrupt or unsafe settings file blocks startup rather than reverting to defaults.
  Preserve the file for diagnosis and restore a known-good owner-only copy while
  research is stopped. A failed save keeps the browser draft; reload and compare
  before retrying an uncertain result.

## Data flow, freshness, and recovery

The browser calls only the operator-console origin. The Node console proxies
bounded read requests to the bearer-protected Python service and keeps the
Opportunity API token server-side. Foreground steady state is refreshed every
2.5 seconds, an active lifecycle operation temporarily tightens that to one
second, and a hidden tab downshifts to 15 seconds. After the initial cursor is
established, status, runtime detail, and new events are requested concurrently
rather than serially.
The event cursor advances through `/api/v1/events`, deduplicates by event ID,
and retains a bounded live window in the browser. Once the operator requests
older pages, the ledger preserves that explicitly expanded range and can keep
paging backward with the `before` cursor without disturbing the live cursor.
Full detail is loaded only when the operator selects a record.

The browser suppresses state updates when the durable event cursor or runtime
payload is unchanged, so a healthy poll does not imply a full React render.
Feature views, the detail inspector, and global search are separate production
chunks loaded on demand; navigation intent prefetches a view before selection.
Record detail uses a small bounded stale-while-revalidate cache and aborts
obsolete selection requests. Long ledger rows use browser rendering containment
without changing their accessible DOM order.

Polling is single-flight: a slow response cannot stack duplicate refreshes.
Requests have bounded timeouts, transient failures use capped exponential
backoff with jitter, and the browser retries immediately when network access or
window focus returns. A partial API failure keeps the healthy portions of the
response. The console preserves the last synchronized in-memory snapshot during
a temporary outage or safe stop, labels it as stale, and disables lifecycle
controls until the control channel is trustworthy again. A browser reload after
PostgreSQL has been stopped has no cached database snapshot and therefore shows
the stopped state.

Provider-health and Paper-capital summaries use a separate 30-second refresh
cadence with a five-second deadline. A failed auxiliary read advances its next
eligible poll before returning, so an unavailable optional panel cannot create
a request storm or delay the main runtime/event recovery loop. Successful reads
continue to refresh instead of leaving a once-loaded status stale indefinitely.

Lifecycle operations are serialized by an owner-only host lease and saved by
atomic replace, file synchronization, and directory synchronization with their
phase and outcome. Repeated Start and Stop requests are idempotent against the
observed service state. If the console process is interrupted, a later console
reconciles the saved operation with the actual runtime instead of presenting an
endless spinner. An owner-only session secret survives a console-process
restart, while CSRF material and the console instance ID rotate. An open browser
detects that instance change, obtains fresh CSRF material, and continues without
exposing the session secret. The HttpOnly browser session uses a 30-day sliding
window renewed by the normal control-state poll, so an actively used 24x7 console
does not expire after a fixed half-day while an abandoned browser still ages out.
Dependency status probes are coalesced and briefly cached so several browser
refreshes cannot create a Docker command storm.

The Python read service keeps upstream HTTP/1.1 connections reusable and uses a
bounded PostgreSQL connection pool. Current-status projections are cached with
stampede protection and keyed by the append-only event cursor: idle reads avoid
rebuilding the same multi-table snapshot, while the next committed event changes
the key immediately. Runtime-only database projections use a short bounded TTL;
the in-process scheduler heartbeat and current-cycle state are merged fresh on
every response. Cache age and hit posture are exposed in response metadata.
Recent-history and environment/cursor access paths have dedicated database
indexes. The Node static server retains built assets in memory and supports
immutable ETag revalidation; `index.html` remains `no-store` so a restarted
console advertises the current build.

The frontend and Node console also share an explicit protocol version. A stale
or mismatched build is blocked with a rebuild instruction before controls become
available. Upstream response size, request time, migration time, Compose
startup, Compose shutdown, service verification, and log reads are bounded so a
wedged dependency cannot occupy a control operation indefinitely.

Credential inventory is deliberately separate from Python API polling, so a
new clone can be configured while the backend and containers are stopped. It
returns provider label, purpose, required/optional posture, configured state,
source kind, editability, and a short one-way fingerprint—never a raw value or
filesystem path. Jina and OpenAlex remain explicitly available in their no-key
modes; Finnhub is an optional authenticated company-intelligence source. The
inventory also lists built-in no-key public providers and can detect only safe
metadata for an owner-only external Tiger Paper file. A token replacement is
bounded to 8 KiB, validated for its selected provider, atomically written to the
external owner-only credential directory, and rolled back if local verification
fails. Environment-provided values are locked instead of silently shadowed. The
browser password field is cleared after either success or failure.

The credential page automatically requests a bounded provider verification
when its owner-only result is missing or older than 15 minutes. The operator can
also force a new check with **Verify APIs**. Each configured slot uses a fixed
read-only endpoint and a ten-second deadline. Status is normalized to
`healthy`, `auth_rejected`, `rate_limited`, `unavailable`, or `unverified`;
missing and no-key modes remain distinct. HTTP 401/403 supports the UI wording
“expired or rejected” but is not presented as provider-supplied expiration
metadata. Only status, HTTP code, latency, and check time are retained. Response
bodies, headers, credential-bearing URLs, provider error text, and secrets are
discarded before the inventory crosses into the browser process. Replacing a
credential changes the revision and invalidates the previous health snapshot.

If the autonomous service is stopped, the console shows a truthful offline
state instead of stale research data. A synthetic layout preview exists only at
`?preview=1`, is visibly labeled, and disables all controls; it is intended for
responsive visual QA, not operations.

## Control boundary

The control surface can:

- prepare the locked local environment and install the current user's research
  service on the first Start from a fresh clone;
- start an installed Shadow research service and wait for real readiness;
- restart it and wait for readiness; and
- safely stop the service, supervisor, PostgreSQL, and Redis; and
- inspect and replace supported external provider tokens while the complete
  research runtime is stopped;
- verify configured provider availability through bounded, sanitized read-only
  probes without stopping the runtime;
- explicitly refresh a sanitized Tiger Paper account snapshot; and
- enable or revoke the isolated Paper authorization while preserving its
  account/configuration binding and audit record.

Every mutation requires the HttpOnly session, exact same origin, and a per-run
CSRF token. Only one lifecycle operation may run at a time. Operation status and
failure text are visible without exposing credentials.

The control surface cannot:

- reveal a stored API key, accept repository-local secrets, or replace an
  environment-supplied value;
- install Node, `uv`, Docker, or operating-system prerequisites;
- discover brokerage accounts, accept broker credentials, or expose raw broker
  identifiers;
- manually submit, cancel, or replace an order;
- enable a live environment or live-account route; or
- bind beyond the local machine.

Enabling Tiger Paper is fail-closed. The complete runtime must be stopped, the
operator must confirm the protected action, and a fresh broker preflight must
prove Paper mode, the configured 17-digit account, an empty position book, and
zero open orders. The resulting authorization is stored outside source files
with owner-only permissions and is invalidated by any account or configuration
change. On the next runtime start, only audited stock expressions can reach the
isolated risk-sized DAY-limit, regular-hours Paper mirror. Agent-requested size
is still bounded by deterministic portfolio/notional policy, a fresh dispatch
quote, Tiger tradable quantity, and order preview. Every mutation first
persists an intent and revalidates the current authorization generation while
holding the account-global lease. Disabling an empty account fully revokes
mutation. If managed positions remain, revocation enters a close-only,
recovery-required generation: it blocks new buys but lets the durable exit
drain before the operator disables it again. Restart reconciliation uses the
stable ALTA `user_mark` in recent Tiger order history; an absent, duplicate,
partial, non-terminal, or mismatched record becomes `manual_review` and never
causes an automatic repeat order. Research Agents never receive the credentials
or executor, and the console deliberately has no general brokerage-order
endpoint.

The dashboard process intentionally remains alive after a safe stop so the
operator can inspect the stopped state and start the system later. Dashboard
service lifecycle and research-service lifecycle are independent.

## Power and network interruption model

The dashboard is a control client, not the owner of autonomous execution. The
installed launchd or systemd-user service owns the Node host process; the Python
supervisor owns `opportunityd`; PostgreSQL owns durable research records in a
named volume; and Redis uses append-only persistence for disposable coordination
state. Host and Python supervisors restart with bounded backoff, an autonomous
database advisory lock prevents duplicate schedulers, and incomplete research
cycles resume from frozen Scout inputs and append-only records. On process
startup the scheduler reconciles durable cycle bindings before it may mint a
new cycle ID: it resumes the oldest valid frozen wake, fail-closes a binding
that never reached an immutable snapshot or whose evaluation contract changed,
and isolates any later duplicate. This prevents a watchdog restart from
silently running two interpretations of the same interrupted research window.

After a machine restart, both managed user services recover after login. The
dashboard can start even while the research service or container engine is
offline and will show the stopped or reconnecting state truthfully. On macOS
these are user LaunchAgents, so they start after login rather than before login.
The dashboard remains only a control client: its failure cannot stop autonomous
research. An already authorized browser cookie remains valid for its bounded
lifetime, while a new browser must use an unclaimed one-time URL.
If the container engine or network remains unavailable, the supervisors back off
instead of launching overlapping work. No design can make in-flight external
HTTP responses durable; ALTA records only completed, validated stage artifacts
and retries from its durable boundary.

This is production-style recovery for one workstation, not a claim of
multi-host high availability. A deployment that requires an availability SLO
also needs off-host encrypted backups, redundant database and service hosts,
external alert delivery, restore drills, and independent monitoring.

## Troubleshooting

| Symptom                       | Check                                                                                                                                                   |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `console_unauthorized`        | Run `./alta dashboard restart`, then claim the URL from `./alta dashboard open`.                                                                        |
| Dashboard update required     | Stop the foreground console, run `./alta dashboard` again, and reload the page.                                                                         |
| First Start fails             | Verify Node/npm, `uv`, Docker Compose, and free loopback ports, then retry; the operation reports its exact failed phase.                               |
| Credential cannot be changed  | Safely stop ALTA first; an environment-supplied value must be unset outside the browser.                                                                |
| Paper authorization is locked | Stop ALTA, verify the external Tiger Paper file, then enable from **Capital desk**. The preflight rejects non-Paper, non-empty, or mismatched accounts. |
| Paper verification fails      | Authorization remains off. Use the error fingerprint with local Tiger SDK diagnostics; never substitute a live account.                                 |
| Runtime stays stopped         | Check the persisted operation phase, then `./alta service logs`.                                                                                        |
| Runtime is live but not ready | Inspect heartbeat and dependency posture; do not force a research cycle.                                                                                |
| No events appear              | Verify `/health/ready`, PostgreSQL health, and the current event cursor. An idle system may validly emit no new opportunity.                            |
| Port is in use                | Stop the conflicting process; use foreground mode with `--port` only for development.                                                                   |
| Console says reconnecting     | Wait for automatic backoff or use **Retry**; controls stay locked until the control channel recovers.                                                   |
| Power was interrupted         | After login, check both `./alta dashboard status` and `./alta service status`; inspect their separate logs if either is down.                           |

Use `./alta dashboard stop` to stop the managed console. In foreground mode,
use `Control-C`. Neither action implicitly stops an already running autonomous
service; use the console's **Stop safely** action or `./alta service stop`
followed by `./alta env down` when that is the intended operational outcome.
