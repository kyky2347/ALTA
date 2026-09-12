"""Bounded TLS transport: no redirect, credential-bearing error, or POST retry."""

import httpx

from .contracts import BrokerError


class Transport:
    def __init__(self, base: str, headers: dict[str, str], client=None):
        self.base = base
        self.client = client or httpx.Client(
            base_url=base,
            headers=headers,
            timeout=httpx.Timeout(15, connect=5),
            follow_redirects=False,
            trust_env=False,
        )

    def request(self, method, path, **kwargs):
        try:
            with self.client.stream(method, path, **kwargs) as response:
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 2 * 1024 * 1024:
                        raise BrokerError("broker_response_too_large")
                if response.status_code == 404 and method == "GET":
                    return None, {}
                if response.status_code in (401, 403):
                    raise BrokerError("broker_authentication_required")
                if response.status_code == 429:
                    raise BrokerError("broker_rate_limited")
                if not 200 <= response.status_code < 300:
                    raise BrokerError("broker_request_failed")
                import json

                return json.loads(content) if content else None, dict(response.headers)
        except BrokerError:
            raise
        except Exception:
            raise BrokerError("broker_transport_unavailable") from None

    def close(self):
        self.client.close()
