from datetime import UTC, datetime
from pathlib import Path

import pytest

from alta_capitald import (
    READ_CAPABILITIES,
    CapitalMode,
    FakeReadTransport,
    PaperBoundary,
    PaperBoundaryConfig,
    PaperBoundaryError,
    PaperSnapshot,
)


def enabled_config(tmp_path: Path, mode: CapitalMode = CapitalMode.FAKE):
    config_path = tmp_path / "explicit-paper.properties"
    config_path.write_text("paper-fixture=true\n")
    config_path.chmod(0o600)
    return PaperBoundaryConfig(
        mode=mode,
        config_path=config_path,
        config_root=tmp_path,
        approved_account_id="paper-account-fixture",
        approved_account_type="PAPER",
        owner_id="capitald-owner-one",
        owner_lease_path=tmp_path / "capitald.owner",
    )


def snapshot(
    environment: str = "PAPER",
    account_id: str = "paper-account-fixture",
    account_type: str = "PAPER",
):
    return PaperSnapshot(
        environment=environment,
        account_id=account_id,
        account_type=account_type,
        known_at=datetime(2026, 8, 23, 14, tzinfo=UTC),
        cash="100000.00",
        positions=(("DEMO", "1"),),
    )


def test_default_is_disabled_and_mutation_cannot_be_enabled() -> None:
    config = PaperBoundaryConfig()
    boundary = PaperBoundary(config)

    assert (config.mode, config.paper_mutation_enabled, READ_CAPABILITIES) == (
        CapitalMode.DISABLED,
        False,
        ("snapshot.read",),
    )
    boundary.start()
    with pytest.raises(PaperBoundaryError, match="disabled"):
        boundary.read_snapshot()
    with pytest.raises(PaperBoundaryError, match="unavailable"):
        PaperBoundaryConfig(paper_mutation_enabled=True)
    with pytest.raises(PaperBoundaryError, match="mode is not allowed"):
        PaperBoundaryConfig(mode="paper")  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", [CapitalMode.FAKE, CapitalMode.READ_ONLY])
def test_explicit_path_exact_account_and_unique_owner(
    tmp_path: Path, mode: CapitalMode
) -> None:
    config = enabled_config(tmp_path, mode)
    transport = FakeReadTransport(snapshot())
    first = PaperBoundary(config, transport)
    second = PaperBoundary(
        PaperBoundaryConfig(
            **{
                **config.__dict__,
                "owner_id": "capitald-owner-two",
            }
        ),
        transport,
    )

    first.start()
    try:
        with pytest.raises(PaperBoundaryError, match="already has an owner"):
            second.start()
        assert first.read_snapshot() == snapshot()
        assert transport.calls == [("paper-account-fixture", str(config.config_path))]
    finally:
        first.stop()


@pytest.mark.parametrize(
    "update",
    [
        {"config_path": Path("relative.properties")},
        {"approved_account_id": "paper-*"},
        {"approved_account_id": ""},
        {"owner_lease_path": Path("relative.owner")},
        {"config_root": Path("relative-root")},
    ],
)
def test_enabled_boundary_rejects_discovery_and_non_exact_config(
    tmp_path: Path, update: dict
) -> None:
    values = enabled_config(tmp_path).__dict__ | update
    with pytest.raises(PaperBoundaryError):
        PaperBoundaryConfig(**values)


@pytest.mark.parametrize(
    ("bad_snapshot", "message"),
    [
        (snapshot(environment="STANDARD"), "non-Paper"),
        (snapshot(account_id="different-paper-account"), "exact approved"),
        (snapshot(account_type="STANDARD"), "account type"),
    ],
)
def test_non_paper_or_different_account_response_fails_closed(
    tmp_path: Path, bad_snapshot: PaperSnapshot, message: str
) -> None:
    boundary = PaperBoundary(enabled_config(tmp_path), FakeReadTransport(bad_snapshot))
    boundary.start()
    try:
        with pytest.raises(PaperBoundaryError, match=message):
            boundary.read_snapshot()
    finally:
        boundary.stop()


@pytest.mark.parametrize(
    "cash,positions",
    [
        ("NaN", ()),
        ("-1", ()),
        ("1", (("DEMO", "Infinity"),)),
        ("1", (("DEMO", "1"), ("DEMO", "2"))),
    ],
)
def test_snapshot_rejects_invalid_numbers_and_duplicate_positions(
    cash: str, positions: tuple[tuple[str, str], ...]
) -> None:
    with pytest.raises(PaperBoundaryError):
        PaperSnapshot(
            environment="PAPER",
            account_id="paper-account-fixture",
            account_type="PAPER",
            known_at=datetime(2026, 8, 23, 14, tzinfo=UTC),
            cash=cash,
            positions=positions,
        )


def test_enabled_boundary_rejects_symlink_and_broad_permissions(tmp_path: Path) -> None:
    target = tmp_path / "target.properties"
    target.write_text("paper=true\n")
    target.chmod(0o600)
    link = tmp_path / "link.properties"
    link.symlink_to(target)
    with pytest.raises(PaperBoundaryError, match="symlink"):
        PaperBoundaryConfig(
            **{
                **enabled_config(tmp_path).__dict__,
                "config_path": link,
            }
        )

    target.chmod(0o644)
    with pytest.raises(PaperBoundaryError, match="owner-only"):
        PaperBoundaryConfig(
            **{
                **enabled_config(tmp_path).__dict__,
                "config_path": target,
            }
        )


def test_package_has_no_external_client_or_generic_agent_bridge() -> None:
    package = Path(__file__).parents[1] / "src" / "alta_capitald"
    source = (package / "boundary.py").read_text().casefold()
    forbidden = (
        "tiger" + "open",
        "quote" + "client",
        "tiger" + "mcp",
        "account" + "enumerat",
        "get" + "_accounts",
        "submit" + "_order",
        "cancel" + "_order",
        "modify" + "_order",
    )
    assert all(term not in source for term in forbidden)
