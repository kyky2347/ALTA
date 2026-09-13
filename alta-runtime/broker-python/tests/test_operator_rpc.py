from secrets import token_hex

import pytest

from alta_brokers.__main__ import handle
from alta_brokers.contracts import BrokerError
from alta_brokers.storage import Profiles


@pytest.mark.parametrize(
    "provider", ["tiger", "alpaca", "ibkr", "futu", "longport", "schwab"]
)
def test_each_broker_can_save_and_reload_without_connection_or_authority(
    provider, tmp_path, monkeypatch
):
    from alta_brokers.catalog import credential_fields

    monkeypatch.setattr(
        "alta_brokers.__main__.connect", lambda _: pytest.fail("save must not connect")
    )
    profiles = Profiles(
        tmp_path / "credentials", tmp_path / "state", tmp_path / "project"
    )
    secret = token_hex(24)
    environment = "LIVE" if provider == "schwab" else "PAPER"
    account = {"tiger": "1" * 17, "ibkr": "DU1001", "futu": "1001"}.get(
        provider, "test-account-binding"
    )
    credentials = dict.fromkeys(credential_fields(provider, environment), secret)
    if provider in ("ibkr", "futu"):
        credentials["port"] = "11111"
    if provider == "ibkr":
        credentials["client_id"] = "71"
    if provider == "futu":
        credentials["security_firm"] = "FUTUSECURITIES"
    if provider == "tiger":
        from Crypto.PublicKey import RSA

        credentials = {
            "tiger_id": "1001",
            "private_key": RSA.generate(2048).export_key().decode(),
        }
    request = {
        "action": "save",
        "revision": "new",
        "profile": {
            "provider": provider,
            "environment": environment,
            "account": account,
            "credentials": credentials,
        },
    }
    result = handle(request, profiles)
    assert result["saved"]
    stored = profiles.load(provider)
    assert stored.account.get_secret_value() == account
    assert all(stored.secret(key) == value for key, value in credentials.items())
    catalog = handle({"action": "catalog"}, profiles)
    assert secret not in str(catalog) and account not in str(catalog)
    assert not any(row["autonomous_execution"] for row in catalog["brokers"])
    assert not list((tmp_path / "state").rglob("authority.json"))
    with pytest.raises(BrokerError, match="conflict"):
        handle(request, profiles)


def test_catalog_and_write_only_save_do_not_connect_or_authorize(tmp_path, monkeypatch):
    profiles = Profiles(
        tmp_path / "credentials", tmp_path / "state", tmp_path / "project"
    )
    monkeypatch.setattr(
        "alta_brokers.__main__.connect", lambda _: pytest.fail("must not connect")
    )
    catalog = handle({"action": "catalog"}, profiles)
    assert len(catalog["brokers"]) == 6
    assert all(
        not p["configured"] and not p["autonomous_execution"]
        for p in catalog["brokers"]
    )
    secret = token_hex(30)
    result = handle(
        {
            "action": "save",
            "revision": "new",
            "profile": {
                "provider": "alpaca",
                "environment": "LIVE",
                "account": "test-account",
                "credentials": {"api_key": secret, "api_secret": secret},
            },
        },
        profiles,
    )
    assert result["saved"]
    assert secret not in str(result)
    catalog = handle({"action": "catalog"}, profiles)
    assert secret not in str(catalog) and "test-account" not in str(catalog)
    assert not list((tmp_path / "state").glob("*/authority.json"))
    for action in ("submit", "cancel", "delete", "stage", "tick"):
        with pytest.raises(BrokerError, match="action_unavailable"):
            handle({"action": action}, profiles)


def test_futu_paper_does_not_request_a_live_unlock_password(tmp_path):
    profiles = Profiles(
        tmp_path / "credentials", tmp_path / "state", tmp_path / "project"
    )
    request = {
        "action": "save",
        "revision": "new",
        "profile": {
            "provider": "futu",
            "environment": "PAPER",
            "account": "1000",
            "credentials": {"port": "11111", "security_firm": "FUTUSECURITIES"},
        },
    }
    assert handle(request, profiles)["saved"]
    request["profile"]["environment"] = "LIVE"
    with pytest.raises(BrokerError, match="credentials_invalid"):
        handle(request, profiles)


def test_one_corrupt_profile_does_not_hide_other_brokers_or_leak_input(tmp_path):
    profiles = Profiles(
        tmp_path / "credentials", tmp_path / "state", tmp_path / "project"
    )
    file = profiles.file("alpaca")
    file.parent.mkdir(parents=True, mode=0o700)
    file.write_text('{"private-field":"must-not-escape"}')
    file.chmod(0o600)
    result = handle({"action": "catalog"}, profiles)
    assert len(result["brokers"]) == 6
    bad = next(row for row in result["brokers"] if row["provider"] == "alpaca")
    assert bad["profile_error"] == "broker_profile_unreadable"
    assert bad["revision"] == "unavailable"
    assert "must-not-escape" not in str(result)
    assert all(not row["autonomous_execution"] for row in result["brokers"])
    assert "must-not-escape" in file.read_text()


def test_invalid_sdk_configuration_never_creates_a_credential_file(tmp_path):
    profiles = Profiles(
        tmp_path / "credentials", tmp_path / "state", tmp_path / "project"
    )
    bad_profiles = [
        {
            "provider": "tiger",
            "environment": "PAPER",
            "account": "0" * 17,
            "credentials": {"tiger_id": "123", "private_key": "invalid"},
        },
        {
            "provider": "ibkr",
            "environment": "LIVE",
            "account": "DU1000",
            "credentials": {"port": "7497", "client_id": "71"},
        },
        {
            "provider": "futu",
            "environment": "PAPER",
            "account": "1000",
            "credentials": {"port": "bad-port", "security_firm": "FUTUSECURITIES"},
        },
    ]
    for profile in bad_profiles:
        with pytest.raises(BrokerError):
            handle({"action": "save", "profile": profile, "revision": "new"}, profiles)
        assert not profiles.file(profile["provider"]).exists()
