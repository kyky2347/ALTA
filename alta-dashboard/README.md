# ALTA operator console

This workspace contains the responsive local operator console for ALTA's
Shadow research runtime. It is built as static React assets and served through
the loopback control plane in `alta-src/operator-console.mjs`.

```shell
./alta dashboard
```

That is the complete normal startup command. It performs a locked dependency
install and production build when needed, serves the UI on loopback, and opens
the default browser automatically. From outside the repository, use
`npm --loglevel=error --prefix "/absolute/path/to/ALTA" run dashboard`; this
avoids depending on the shell's current directory. The
first **Start ALTA** click on a new clone prepares the isolated environment,
installs the current user's research service, and waits for backend readiness.
The operator console keeps the backend bearer token outside the browser and
protects lifecycle and credential mutations with a local HttpOnly session,
same-origin validation, and CSRF.

Production UI work is split by operator view: heavy views, record detail, and
global search load on demand and prefetch on navigation intent. Live reads are
single-flight, parallel after bootstrap, render-suppressed when unchanged, and
cadence-aware (foreground, active operation, and hidden tab). Operational use
also benefits from the Python service's pooled event-invalidated projections and
the console's in-memory immutable asset cache; none of these caches store raw
credentials.

The Credentials view reports only safe provider metadata and supports
write-only replacement while the research runtime is stopped. Secrets are
stored outside the repository with owner-only permissions and are never read
back into the browser. Tiger uses a separate Paper-only authorization and
reconciliation boundary. Model and credential settings cannot grant brokerage
authority, and there is no live-account mode.

For frontend contributors:

```shell
pnpm --dir alta-dashboard dev
pnpm dashboard:lint
pnpm dashboard:build
```

The Vite development server is suitable only for visual work. Operational use
must go through `./alta dashboard`.

The interface ships with English, Simplified Chinese and Hong Kong Traditional
Chinese operator copy. The three-option language menu persists the locale in local
browser storage and updates document language, dates, relative time, numbers,
domain statuses, accessibility labels, recovery states, and responsive copy.
Saved Agent and research artifacts are deliberately shown verbatim so changing
the display locale cannot alter the auditable record.

Localized catalogs live in `src/lib/locales/`; shared message keys and interpolation
parameters are checked by tests. Hong Kong copy uses local financial and interface
wording, not a runtime character-conversion overlay. The Silment wordmark and ALTA
name are composed as a responsive lockup; the source wordmark is unchanged.

The Agent desk's **Agent models** dialog configures seven role routes and four
optional Scout overrides through the authenticated operator API. Saving is
revision-fenced and allowed only while research is stopped. Independent challenge
and audit models remain distinct from the roles they review. There is no silent
fallback, credential input, or research-accessible configuration writer in this dialog.

The Agent desk separates research minds from review and delivery roles. Counts
reflect the loaded snapshot, not a timer. Research cards retain saved summaries;
review rows label static responsibilities separately from recorded model, usage
and time fields. The three latest recorded events link to their detail records.
Unavailable usage is never shown as zero. Documentation screenshots use the
running local console and its saved research records; model labels and activity
counts come from those records, not from the configuration defaults.

See [the operator guide](../docs/operations/operator-console.md) for data
semantics, controls, safety boundaries, and troubleshooting.
