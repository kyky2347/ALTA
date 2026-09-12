"""Capabilities describe implemented code, never an account acceptance claim."""

from .contracts import require

CATALOG = (
    {
        "provider": "tiger",
        "name": "Tiger",
        "environments": ["PAPER", "LIVE"],
        "fields": ["tiger_id", "private_key"],
        "authentication": "rsa",
        "proof": "account_bound",
        "docs": "https://docs-en.itigerup.com/docs/prepare",
    },
    {
        "provider": "alpaca",
        "name": "Alpaca",
        "environments": ["PAPER", "LIVE"],
        "fields": ["api_key", "api_secret"],
        "authentication": "key_pair",
        "proof": "account_bound",
        "docs": "https://docs.alpaca.markets/us/docs/getting-started-with-trading-api",
    },
    {
        "provider": "ibkr",
        "name": "Interactive Brokers",
        "environments": ["PAPER", "LIVE"],
        "fields": ["port", "client_id"],
        "authentication": "tws_gateway",
        "proof": "account_bound",
        "docs": "https://www.interactivebrokers.com/docs/tws-api/doc/introduction",
    },
    {
        "provider": "futu",
        "name": "Futu / moomoo",
        "environments": ["PAPER", "LIVE"],
        "fields": ["port", "security_firm", "trade_password"],
        "authentication": "opend",
        "proof": "account_bound",
        "docs": "https://openapi.futunn.com/futu-api-doc/en/trade/place-order.html",
    },
    {
        "provider": "longport",
        "name": "Longbridge / Longport",
        "environments": ["PAPER", "LIVE"],
        "fields": ["app_key", "app_secret", "access_token"],
        "authentication": "account_token",
        "proof": "identity_unavailable",
        "docs": "https://open.longbridge.com/docs/getting-started",
    },
    {
        "provider": "schwab",
        "name": "Charles Schwab",
        "environments": ["LIVE"],
        "fields": ["account_hash", "access_token"],
        "authentication": "oauth",
        "proof": "permission_unverified",
        "docs": "https://developer.schwab.com/products/trader-api--individual",
    },
)


def credential_fields(provider, environment):
    fields = next(entry["fields"] for entry in CATALOG if entry["provider"] == provider)
    # OpenD does not unlock a simulated account. Do not ask operators to supply
    # a real trading password for Paper configuration or read-only verification.
    return [
        field
        for field in fields
        if not (
            provider == "futu" and environment == "PAPER" and field == "trade_password"
        )
    ]


def validate_credentials(profile):
    """Reject malformed input locally; syntax is never account verification."""
    import re

    require(
        set(profile.credentials)
        == set(credential_fields(profile.provider, profile.environment)),
        "broker_credentials_invalid",
    )
    account = profile.account.get_secret_value()
    if profile.provider in ("futu", "ibkr"):
        port = profile.secret("port")
        require(port.isdigit() and 1024 <= int(port) <= 65535, "gateway_port_invalid")
    if profile.provider == "ibkr":
        client = profile.secret("client_id")
        require(
            client.isdigit() and 1 <= int(client) <= 2147483647,
            "gateway_client_id_invalid",
        )
        prefix = "DU" if profile.environment == "PAPER" else "U"
        require(
            re.fullmatch(prefix + r"\d+", account) is not None,
            "account_environment_mismatch",
        )
    if profile.provider == "futu":
        require(
            account.isdigit() and 0 < int(account) < 2**63, "broker_account_invalid"
        )
        require(
            profile.secret("security_firm")
            in (
                "FUTUSECURITIES",
                "FUTUINC",
                "FUTUSG",
                "FUTUAU",
                "FUTUCA",
                "FUTUJP",
            ),
            "security_firm_invalid",
        )
    if profile.provider == "tiger":
        from .adapters.tiger import private_key_pem

        require(
            account.isdigit()
            and ((len(account) == 17) == (profile.environment == "PAPER")),
            "account_environment_mismatch",
        )
        require(profile.secret("tiger_id").isdigit(), "tiger_id_invalid")
        try:
            private_key_pem(profile.secret("private_key"))
        except (ValueError, TypeError):
            require(False, "tiger_key_invalid")
