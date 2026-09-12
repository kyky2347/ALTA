from secrets import token_hex

import pytest

from alta_brokers.__main__ import handle
from alta_brokers.contracts import BrokerError
from alta_brokers.storage import Profiles


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
    for action in ("submit", "authorize", "cancel", "delete"):
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
