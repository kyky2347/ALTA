"""Provider SDKs are imported lazily; installing ALTA never opens a broker session."""

from ..contracts import BrokerError, Profile


def connect(profile: Profile):
    try:
        if profile.provider == "alpaca":
            from .alpaca import Alpaca

            return Alpaca(profile)
        if profile.provider == "schwab":
            from .schwab import Schwab

            return Schwab(profile)
        if profile.provider == "tiger":
            from .tiger import Tiger

            return Tiger(profile)
        if profile.provider == "ibkr":
            from .ibkr import InteractiveBrokers

            return InteractiveBrokers(profile)
        if profile.provider == "futu":
            from .futu import Futu

            return Futu(profile)
        if profile.provider == "longport":
            from .longport import Longport

            return Longport(profile)
    except ImportError:
        raise BrokerError("broker_dependency_missing") from None
    except BrokerError:
        raise
    except Exception:
        raise BrokerError("broker_connection_failed") from None
    raise BrokerError("broker_not_supported")
