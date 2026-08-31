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
back into the browser. Tiger is a visible Paper-only boundary, not a credential
form or order path in this capital-disabled build.

For frontend contributors:

```shell
pnpm --dir alta-dashboard dev
pnpm dashboard:lint
pnpm dashboard:build
```

The Vite development server is suitable only for visual work. Operational use
must go through `./alta dashboard`.

The interface ships with complete English and Simplified Chinese operator
copy. The language button in the global action bar persists the locale in local
browser storage and updates document language, dates, relative time, numbers,
domain statuses, accessibility labels, recovery states, and responsive copy.
Saved Agent and research artifacts are deliberately shown verbatim so changing
the display locale cannot alter the auditable record.

See [the operator guide](../docs/operations/operator-console.md) for data
semantics, controls, safety boundaries, and troubleshooting.
