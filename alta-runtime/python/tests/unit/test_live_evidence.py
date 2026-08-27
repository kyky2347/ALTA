from alta_asterism.live_source_flow import _balanced_rows, _market_summary


def test_market_summary_exposes_prices_without_raw_payload_noise() -> None:
    body = {
        "payload": {
            "symbol": "SPY",
            "aggregate": {
                "open": 500,
                "high": 505,
                "low": 499,
                "close": 504,
                "volume": 123456,
            },
        }
    }

    assert _market_summary(body) == (
        "SPY adjusted daily market bar: open=500, high=505, low=499, "
        "close=504, volume=123456."
    )


def test_balanced_rows_prevents_one_source_from_drowning_out_another() -> None:
    rows = [
        ("m1", None, "massive"),
        ("m2", None, "massive"),
        ("m3", None, "massive"),
        ("f1", None, "finlight"),
        ("f2", None, "finlight"),
    ]

    selected = _balanced_rows(rows, 4)

    assert [row[2] for row in selected] == [
        "finlight",
        "massive",
        "finlight",
        "massive",
    ]
