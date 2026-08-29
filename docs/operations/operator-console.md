# Local operator console

The ALTA operator console is a loopback-only control and observability surface
for the Shadow research runtime. It combines a live opportunity topology with a
chronological decision ledger so an operator can see both what the system is
doing and how it reached the present state.

It is research infrastructure. It is not an order-management system, a broker
terminal, an Alpha claim, or a way to expose private model chain-of-thought.

## Build and open

```shell
corepack pnpm install --frozen-lockfile
pnpm dashboard:build
./alta dashboard install
./alta dashboard open
```

By default the managed console binds to `127.0.0.1:8877`. It starts after user
login and the host service manager restarts it after an unexpected exit. The
`open` command prints a one-time launch URL. Opening it creates an HttpOnly,
`SameSite=Strict` local session and redirects to a clean URL. The launch URL is
stored only in an owner-only atomic host-state file, is never printed by the
background process or written to its logs, and is removed from that file after
it is claimed.

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

Running `./alta dashboard` without an action is a foreground development mode.
Keep that terminal process alive while using it. Alternate loopback ports are
supported only by this foreground mode:

Alternate loopback ports are supported:

```shell
./alta dashboard --host 127.0.0.1 --port 8890
```

Non-loopback bindings are rejected.

## What each view shows

- **Live field** — Candidates, deduplicated Opportunities, active Agent roles,
  committee state, expression, audit, and Shadow observation in one flow.
- **Decision ledger** — Cursor-ordered durable events with their aggregate,
  timestamp, public summary, selected-record hand-off, in-view filtering, and
  backward pagination to older history.
- **System overview** — Current source posture, object counts, Trader Mind
  memory summaries, and append-only event cursor.
- **Agent desk** — Latest Run per role, actual model route, durable mind summary,
  turn count, context usage, latency, and Run details.
- **Shadow book** — Research-only open and closed Shadow positions plus the
  forward evidence ledger: comparable-sample maturity, confidence interval,
  forecast error, directional calibration, downside-only forecast reserve, and
  the tightest evidence-driven capital posture. An observed-lifecycle panel
  separately shows favorable/adverse excursion, drawdown, exit capture, and
  missed positive paths using only prices captured while positions were open.
  It is explicitly separated from brokerage, cannot auto-tune exits, and never
  labels Shadow evidence as proven performance.
- **Inspector** — Opportunity packets, independent assessments, committee
  arguments, frozen Run inputs, tool provenance, artifacts, implementation
  plans, hashes, and normalized JSON records.
- **Replay ribbon** — A draggable event playhead with play, pause, timestamp,
  cursor, replay state, and a direct return to the live edge.

Use `Command-K` (or `Control-K`) to search across loaded Candidates,
Opportunities, Agent Runs, assessments, committee exchanges, expressions,
Shadow positions, and events.

## Data flow, freshness, and recovery

The browser calls only the operator-console origin. The Node console proxies
bounded read requests to the bearer-protected Python service and keeps the
Opportunity API token server-side. Current state is refreshed every 2.5 seconds.
The event cursor advances through `/api/v1/events`, deduplicates by event ID,
and retains a bounded live window in the browser. Once the operator requests
older pages, the ledger preserves that explicitly expanded range and can keep
paging backward with the `before` cursor without disturbing the live cursor.
Full detail is loaded only when the operator selects a record.

Polling is single-flight: a slow response cannot stack duplicate refreshes.
Requests have bounded timeouts, transient failures use capped exponential
backoff with jitter, and the browser retries immediately when network access or
window focus returns. A partial API failure keeps the healthy portions of the
response. The console preserves the last synchronized in-memory snapshot during
a temporary outage or safe stop, labels it as stale, and disables lifecycle
controls until the control channel is trustworthy again. A browser reload after
PostgreSQL has been stopped has no cached database snapshot and therefore shows
the stopped state.

Lifecycle operations are serialized by an owner-only host lease and saved by
atomic replace, file synchronization, and directory synchronization with their
phase and outcome. Repeated Start and Stop requests are idempotent against the
observed service state. If the console process is interrupted, a later console
reconciles the saved operation with the actual runtime instead of presenting an
endless spinner. An owner-only session secret survives a console-process
restart, while CSRF material and the console instance ID rotate. An open browser
detects that instance change, obtains fresh CSRF material, and continues without
exposing the session secret. Dependency status probes are coalesced and briefly
cached so several browser refreshes cannot create a Docker command storm.

The frontend and Node console also share an explicit protocol version. A stale
or mismatched build is blocked with a rebuild instruction before controls become
available. Upstream response size, request time, migration time, Compose
startup, Compose shutdown, service verification, and log reads are bounded so a
wedged dependency cannot occupy a control operation indefinitely.

If the autonomous service is stopped, the console shows a truthful offline
state instead of stale research data. A synthetic layout preview exists only at
`?preview=1`, is visibly labeled, and disables all controls; it is intended for
responsive visual QA, not operations.

## Control boundary

The control surface can:

- start an already installed Shadow research service;
- restart it and wait for readiness; and
- safely stop the service, supervisor, PostgreSQL, and Redis.

Every mutation requires the HttpOnly session, exact same origin, and a per-run
CSRF token. Only one lifecycle operation may run at a time. Operation status and
failure text are visible without exposing credentials.

The control surface cannot:

- install, uninstall, or reconfigure the host service;
- read or change API keys;
- enable Tiger Paper or any other broker;
- submit, cancel, or replace an order;
- enable capital or a live environment; or
- bind beyond the local machine.

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
cycles resume from frozen Scout inputs and append-only records.

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

| Symptom                       | Check                                                                                                                         |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `console_unauthorized`        | Run `./alta dashboard restart`, then claim the URL from `./alta dashboard open`.                                              |
| Dashboard update required     | Run `pnpm dashboard:build`, `./alta dashboard restart`, and reload the page.                                                  |
| Start is disabled             | Run `./alta service status`; the service must already be installed.                                                           |
| Runtime stays stopped         | Check the persisted operation phase, then `./alta service logs`.                                                              |
| Runtime is live but not ready | Inspect heartbeat and dependency posture; do not force a research cycle.                                                      |
| No events appear              | Verify `/health/ready`, PostgreSQL health, and the current event cursor. An idle system may validly emit no new opportunity.  |
| Port is in use                | Stop the conflicting process; use foreground mode with `--port` only for development.                                         |
| Console says reconnecting     | Wait for automatic backoff or use **Retry**; controls stay locked until the control channel recovers.                         |
| Power was interrupted         | After login, check both `./alta dashboard status` and `./alta service status`; inspect their separate logs if either is down. |

Use `./alta dashboard stop` to stop the managed console. In foreground mode,
use `Control-C`. Neither action implicitly stops an already running autonomous
service; use the console's **Stop safely** action or `./alta service stop`
followed by `./alta env down` when that is the intended operational outcome.
