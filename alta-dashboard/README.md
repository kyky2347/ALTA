# ALTA operator console

This workspace contains the responsive local operator console for ALTA's
Shadow research runtime. It is built as static React assets and served through
the loopback control plane in `alta-src/operator-console.mjs`.

```shell
pnpm --dir alta-dashboard dev
pnpm dashboard:lint
pnpm dashboard:build
./alta dashboard
```

The development server is suitable only for visual work. Operational use must
go through `./alta dashboard`, which keeps the backend bearer token outside the
browser and protects lifecycle mutations with a local HttpOnly session,
same-origin validation, and CSRF.

See [the operator guide](../docs/operations/operator-console.md) for data
semantics, controls, safety boundaries, and troubleshooting.
