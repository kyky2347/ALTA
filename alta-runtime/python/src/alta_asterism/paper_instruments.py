from decimal import Decimal

PAPER_INVERSE_ETFS = {
    "TSLS": {
        "underlying_symbol": "TSLA",
        "aliases": ("TSLA", "TESLA"),
        "daily_target": "-1x",
        "issuer_source": "https://www.direxion.com/product/daily-tsla-bull-and-bear-leveraged-single-stock-etfs",
    },
    "SH": {
        "underlying_symbol": "SPY",
        "aliases": ("SPY", "S&P 500", "S&P500"),
        "daily_target": "-1x",
        "issuer_source": "https://www.proshares.com/our-etfs/leveraged-and-inverse/sh",
    },
    "PSQ": {
        "underlying_symbol": "QQQ",
        "aliases": ("QQQ", "NASDAQ-100", "NASDAQ 100"),
        "daily_target": "-1x",
        "issuer_source": "https://www.proshares.com/our-etfs/leveraged-and-inverse/psq",
    },
    "RWM": {
        "underlying_symbol": "IWM",
        "aliases": ("IWM", "RUSSELL 2000", "RUSSELL2000"),
        "daily_target": "-1x",
        "issuer_source": "https://www.proshares.com/our-etfs/leveraged-and-inverse/rwm",
    },
    "DOG": {
        "underlying_symbol": "DIA",
        "aliases": ("DIA", "DOW 30", "DOW JONES"),
        "daily_target": "-1x",
        "issuer_source": "https://www.proshares.com/our-etfs/leveraged-and-inverse/dog",
    },
}

MAX_POST_AUDIT_DRIFT_BPS = Decimal("100")
