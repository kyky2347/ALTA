# ALTA changes to the Codex source substrate

ALTA modifies exactly these upstream Rust files relative to the pinned commit:

- `app-server/src/lib.rs`
- `app-server/src/main.rs`
- `cloud-tasks/src/lib.rs`
- `core-plugins/src/manager.rs`
- `core-plugins/src/manager_tests.rs`
- `core/src/tools/handlers/multi_agents_v2.rs`
- `core/src/tools/spec_plan.rs`
- `core/src/tools/spec_plan_tests.rs`
- `core/tests/suite/subagent_notifications.rs`
- `exec/src/event_processor_with_human_output.rs`
- `tui/src/history_cell/session.rs`
- `tui/src/status/card.rs`
- `tui/src/version.rs`

The changes provide:

1. provider-neutral plaintext collaboration aliases for explicitly configured
   ALTA cross-provider roles;
2. project-local ALTA identity when launched with `ALTA_DISTRIBUTION=3.5`;
3. release-build hygiene and tests for those behaviors.

They do not change Codex authentication, sandbox network flags, approval
semantics, or the App Server wire protocol.
