# Optional Adanos sentiment research

Design proposal for [issue #24](https://github.com/kyky2347/ALTA/issues/24).
This is an optional source inside the existing bounded `alta_finance_data`
tool, not a new agent, execution capability, or price provider.

[Adanos](https://adanos.org/) is a commercial API with a free plan. The author
of this integration represents Adanos. Sources, history, and quotas depend on
the account plan; see the [API documentation](https://api.adanos.org/docs).

## Operator setup

Set `ADANOS_API_KEY` in the operator environment, or place the key in an
owner-only `adanos.key` file under the external
`~/.config/alta/credentials/resources/` directory. Never store the key inside
the project tree. Restart the gateway after changing credentials. No default
research workflow selects this source, and no key is sent to agent children.

Example tool arguments:

```json
{
  "source": "adanos",
  "dataset": "news_stocks",
  "symbol": "BRK",
  "from_date": "2026-10-01",
  "to_date": "2026-10-02"
}
```

Datasets: `reddit_stocks`, `reddit_crypto`, `x_stocks`, `news_stocks`, and
`polymarket_stocks`. Only Reddit supports crypto (`symbol`: `BTC`, for example).
News uses company keys: `BRK`, not share-class symbols such as `BRK.B`.
Dates are mandatory inclusive UTC dates, mapped to API `from`/`to`; no `days`.

## Evidence boundary

Use a sentiment response as a secondary research lead, not an independently
verified issuer claim, price, forecast, or buy/sell signal. Fetch time is the
observation time. A historical aggregate retrieved today does not prove that
the same data was available at a historical decision time. Do not use it to
backfill a frozen wake or replay evidence. Any durable evidence must still go
through ALTA's existing Raw-first, timestamped ingestion and audit boundary.

The adapter reuses ALTA's source pacing, capacity, cancellation, bounded
download, and authenticated transport. Responses are not cached by this adapter
and provider data is not included in commits. HTTP failures, missing credentials,
invalid dates, malformed JSON, and unsupported datasets refuse the request;
none produce neutral sentiment or grant capital authority. No automatic quota
retries are performed. The existing tool-result boundary limits agent output.

Rollback: remove `source=adanos` from research requests and unset the credential.
No database migrations, default research configuration, or broker changes.
