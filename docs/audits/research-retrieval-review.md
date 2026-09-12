# Research retrieval review

September 12, 2026. This review distinguishes retrieval defects from a legitimate
decision not to advance weak evidence. It is not a profitability assessment.

## What the saved runs showed

The baseline window was September 10, 14:00 UTC through September 12, 14:00 UTC,
restricted to production Shadow Scout runs, not fixture or replay runs.

| Observation                        | Count |
| ---------------------------------- | ----: |
| Scout runs                         |   344 |
| Successful candidate outputs       |     1 |
| Successful abstentions             |   335 |
| Failed runs                        |     6 |
| Cancelled runs                     |     2 |
| Standalone web-search calls        |   164 |
| Failed standalone web-search calls |   125 |

These are observations, not proof that every abstention was wrong. Saved reasons
included unavailable market expectations, unrelated search results, inaccessible
primary documents, missing issuer-level exposure and expired causal events.

## Defects and repairs

| Problem                                                                            | Repair                                                                                                                                         | Boundary retained                                                              |
| ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| A current-metrics request also returned decades of nested historical series.       | Finnhub `metrics` now returns the metric snapshot rather than unsolicited series.                                                              | No invented estimates, timestamps or values.                                   |
| A raw byte cut could remove trailing provenance and leave invalid JSON.            | Bounded structured previews preserve source identity before reducing text and record counts. Truncation stays explicit.                        | A partial source is never presented as a complete document.                    |
| Long filings exposed only opening boilerplate.                                     | Page retrieval accepts a literal `focus` or extracted-text `offset`, with match and offset metadata.                                           | Excerpts remain exact source substrings; a missing phrase is not evidence.     |
| Date-only matches could qualify irrelevant search pages.                           | Deep-research relevance ignores pure numbers and month names.                                                                                  | No fabricated source substitutions.                                            |
| A valid search with zero domain-matching results was treated as a provider outage. | Empty results no longer open the outage circuit; automatic routing still tries alternatives.                                                   | Transport, parser and authentication errors remain errors.                     |
| Missing provider credentials were still advertised as selectable search backends.  | The runtime tool catalog only advertises configured authenticated routes.                                                                      | Configuration is not represented as health or entitlement.                     |
| Five calls often ended before finance context and counterevidence.                 | Eight calls by default, configurable with `ALTA_SCOUT_MAX_TOOL_CALLS` from 1 to 12; prompt asks Scouts to reserve evidence-verification calls. | Existing token, deadline, freshness and trading gates remain.                  |
| Repeated wakes revisited the same obvious securities.                              | Deterministic, replayable starting symbols rotate within the existing universe.                                                                | Exact follow-ups and attention exclusions take precedence; no candidate quota. |

The prompt distinguishes a falsifiable research candidate from a decision-grade
opportunity. This clarifies the existing screen-grade path; it does not weaken
the independent audit or advance an unsupported trade.

## Verification and outcome

A real Finnhub request that previously produced approximately 582 KB of tool
output returned approximately 5 KB after the repair, with 126 metric fields and
its credential-free provenance URL intact. No API credential was included in
the result inspected for this review.

A bounded local cycle from 14:12 to 14:19 UTC completed all four Scouts and saved
one additional candidate plus its forming Opportunity. The seven-day registry
therefore contained two distinct opportunity records. Three Scouts abstained.
The new record remained `screen_grade` with `limited` investability; it was not
promoted to an approved order. An initial stale-event proposal was rejected by
the unchanged freshness gate before the permitted retry found a different lead.
The runtime finished `MVP_IDLE` with zero consecutive cycle failures and no open
Shadow positions. This is evidence of one working retrieval-to-registry path,
not a statistically established improvement in opportunity quality or Alpha.

Final first-party checks: 225 Node tests, 391 research-runtime tests, 38 existing
Tiger Paper tests, 44 isolated broker-connector tests and 33 dashboard tests.
Regression coverage includes citation survival, bounded Unicode results,
independent source records, focused page/cache behavior, query relevance,
empty-result circuit behavior, deterministic exploration and hard budget caps.

## Still unresolved

- This installation has no configured Brave or Jina search credential. Public
  search routes can be noisy or unavailable. A separate xAI native-search probe
  timed out; that single probe does not establish permanent unavailability.
- Some company/regulatory pages remain inaccessible; search snippets are not a
  replacement for a retrieved primary document.
- Reliable consensus estimates and issuer-specific exposure are not universally
  available from the current data sources. Neither is invented by the Scouts.
- One bounded run cannot establish sustained candidate yield, investment merit,
  multi-day reliability or profitable execution. Measure those separately.

No live orders were sent. Research, dashboard and dependency services are stopped
after the bounded review; persistent research data is retained for inspection.

## Follow-up: source reach and recovery

The next local engineering pass addresses additional retrieval failures, not
an opportunity-count target. Existing freshness, independent audit, research
budgets and capital boundaries are unchanged.

- **Recovery:** cancelled half-open search/source probes now release their own
  request lease. A late completion from an older request cannot release or reset
  a newer recovery probe. Cancellation is not counted as provider failure.
- **Breadth:** federated search round-robins unique results across successful
  engines instead of allowing the first engine to consume every slot. Deep
  research uses distinct source hosts before additional pages from the same host.
  Multiple engines or hosts do not establish independent evidence on their own.
- **Source access:** `alta_web_crawl` accepts an optional `query` to prioritize
  links already retrieved from the same origin. Depth, request and character
  bounds stay intact; exact fetched text and publication metadata remain visible.
- **Company context:** Finnhub `company_profile` supplies a company/site locator;
  `earnings_surprises` returns bounded historical actual/estimated EPS records.
  Fiscal periods are not publication timestamps, and historical estimates are
  not current consensus or a point-in-time historical estimate series. Missing
  estimates remain null. Endpoint mappings follow the
  [provider documentation](https://finnhub.io/docs/api).
- **Evidence diagnostics:** stale-cache, truncation and excerpt-offset fields
  survive research, crawl and Finnhub projections. MCP text shortening marks the
  affected page truncated and adjusts its text end, rather than leaving a local
  `truncated: false` next to shortened text. Source text stays an exact prefix.
- **Maintainability:** Finnhub handling now lives in a focused adapter module.
  Invalid datasets no longer silently request company news; malformed/error
  responses cannot masquerade as valid historical earnings.

### Native read-only verification

Six authenticated tool calls covered AMZN, UNH and JPM through both new Finnhub
datasets. Each company profile and each four-period earnings response succeeded;
public provenance was present, estimates were available, and no stale-cache flag
was set. Measured call times were 113–561 ms; this small sample is not an SLA.
Raw financial responses and credentials were not copied into this report.

A public, domain-scoped JPMorgan search completed two queries and fetched three
pages in about 37 seconds without a reported failure. The pages were primarily
company/index pages, demonstrating that transport success is not research success.
With query-directed crawling, four fetches in about 2.4 seconds reached the issuer
homepage, quarterly earnings page, investor relations page and a 2Q26 earnings
press-release PDF. Those observations test navigation, not investment merit or
event freshness. A quarterly document is not relabeled as today's opportunity.

Regression verification totals **754 tests**: 248 Node, 391 research-runtime,
38 Tiger Paper, 44 broker-connector and 33 dashboard tests, plus Ruff, formatting,
lint and the production dashboard build. The new checks cover recovery ownership,
fair federation, source diversity, exact crawl limits, malformed finance responses,
null estimates and source-status preservation.

This follow-up did not run an autonomous investment cycle or create new
Opportunity records. It establishes working retrieval paths, not increased
candidate yield or Alpha. Public search availability, provider-specific recency
filter support, paid consensus access and multi-day yield remain limitations.
Only temporary isolated test databases were started; production services and
trading authority were not enabled, and test resources were stopped afterwards.

## Follow-up: usable research budget and tool routing

This pass raises default Scout capacity from 8 to 10 calls, from 88,000 to
96,000 chargeable tokens, and from 180 to 240 seconds per attempt. Existing
operator overrides take precedence. Call and token hard ceilings remain 12
and 100,000; reviewer budgets, freshness, independent evidence and capital
admission are unchanged. Cached input remains in recorded provider usage but
is excluded from the Scout token charge; this is not a provider billing cap.

Search windows now normalize `day/week/month/year`, the Brave aliases and valid
explicit date ranges. Brave receives its documented `pd/pw/pm/py` values.
SearXNG supports native day/month/year filters; other routes receive date hints
without being described as strict filters. The returned freshness provenance
states the actual mode and explicitly leaves event-time verification false.
See the official [Brave context contract](https://api-dashboard.search.brave.com/documentation/services/llm-context),
[SearXNG parameters](https://docs.searxng.org/dev/search_api.html) and
[xAI web-search parameters](https://docs.x.ai/developers/tools/web-search).

Small same-source bursts now wait in a bounded FIFO instead of immediately
failing local pacing. Each gateway allows 8 queued calls per source and at most
15 seconds of admission wait; provider intervals remain intact. Circuit leases
are acquired only at dispatch. Cancelled or circuit-rejected work does not use
a dispatch slot. Gateway shutdown cancels pending queues, including callers
without an explicit cancellation signal, and leaves no pacing timers behind.
These are per-gateway controls, not an account-wide quota coordinator.

### Actual cycle, not a yield promise

Cycle `live-20260912-145907-572118` ran from 14:59:07 to 15:02:52 UTC with
four DeepSeek v4 Flash Scouts. All completed on their first attempt. One new
AVGO relative-dislocation candidate and its forming Opportunity were saved;
three Scouts abstained, including two follow-ups that found no new proof for
the existing HyperPod thesis. The seven-day registry increased from two to
three distinct Opportunity records. The new record is still `screen_grade`:
its mechanism and independent counterevidence are not bound. Its market claims
are research hypotheses, not findings endorsed by this engineering review.

The cycle completed `MVP_IDLE`, with no new Expression and no open Shadow
position. Brokerage execution and new Massive requests were disabled for this
run; existing frozen data remained available as labeled historical context.
There was no order or demonstrated Alpha. Recorded Scout latencies ranged
from about 88 to 224 seconds. Nineteen completed tool calls are recorded;
completed calls alone understate failed routing attempts.

The real run exposed 46 App Server tool-router rejections. Some provider
responses split an advertised flat MCP tool name into a namespace and short
name, leading to `unsupported call` before the request reached the tool.
This explains part of the reported inability to fetch sources; it does not
explain or excuse unrelated public search results. Request-scoped identity
repair now only matches an actually advertised, unambiguous tool and leaves
unknown or foreign namespaces rejected. Arguments and source text must remain
untouched. Literal `namespace::name` responses are also handled through the
same exact request-scoped mapping. The vendored harness was not modified.

A real three-tool check initially exposed a malformed identifier in the local
probe itself; the budget-header guard rejected it correctly. The probe was
corrected to use a valid Run ID, without changing the guard. At 15:12:35 UTC,
DeepSeek v4 Flash successfully called `alta_web_fetch`, `alta_web_crawl` and
Finnhub `company_profile` through the actual App Server/MCP boundary. Each
returned source provenance. The turn took 10.75 seconds and 3,265 chargeable
tokens; its log window had zero unsupported-tool router errors. This verifies
three retrieval routes, not every possible future model response.

The real local read API returned HTTP 200 for liveness, readiness, runtime,
summary, MVP status and the new Opportunity detail. Unauthenticated runtime
access returned 401. Measured local response times were 0–42 ms for this tiny
sample. The isolated API child was stopped and its socket was confirmed closed.

### Retry defects exposed by the follow-up cycles

| Cycle (UTC start)                        | Final Scout outcomes     | Registry change         | Cycle terminal state |
| ---------------------------------------- | ------------------------ | ----------------------- | -------------------- |
| `live-20260912-145907-572118` (14:59:07) | 1 Candidate, 3 no-ops    | New AVGO forming record | `MVP_IDLE`, exit 0   |
| `live-20260912-151313-432150` (15:13:13) | 3 no-ops, 1 failed Scout | None                    | `MVP_IDLE`, exit 0   |
| `live-20260912-152223-865867` (15:22:23) | 1 Candidate, 3 no-ops    | New UNH forming record  | `MVP_IDLE`, exit 0   |

The second cycle ended at 15:20:41 UTC. Its router log window contained zero
unsupported-tool errors, but seven failed-attempt artifacts remained visible.
Several proposals exceeded the 8,000-byte output ceiling; the old retry feedback
only said `semantic_contract_invalid`. Scout prompt v24 now requests compact
UTF-8 output, and a bounded `output_bytes_exceeded` correction explains how to
shorten prose while preserving exact citations, required fields and lineage.
Neither the byte ceiling nor the evidence gates were increased.

The third cycle ended at 15:30:36 UTC. Its UNH capital-allocation candidate has
September 11 freshness and `limited` investability. Diligence remains
`screen_grade`, with `mechanism_not_bound` and
`counterevidence_source_not_distinct`; three nominal source domains did not
override the missing independent evidence. Two causal-Scout deadlines and two
expectation-Scout validation failures were recorded before their no-op outcomes.
This was not an error-free cycle even though all four final Scout statuses were
successful. `MVP_IDLE` and zero consecutive cycle failures are not substitutes
for inspecting per-role attempts, no-op reasons and evidence quality.

The saved no-op reasons exposed another defect: a fresh research retry inherited
the same gateway's depleted Run-level call counter. A new thread therefore had
no usable research calls despite a new worker deadline. Tool admission now uses
an operator-generated Run/deadline attempt identity. Reconnection within the
same attempt does not reset its allowance; each Run permits at most three
distinct attempts, with an immutable per-attempt call cap. Recent counters are
not evicted to admit new work; a full registry rejects admission and day-old
entries can expire. These gateway counters are in-memory and per process,
not a cross-process billing ledger or durable account-level quota service.

The attempt fix landed after the third cycle had started; that cycle did not
hot-reload it. Its separate real App Server verification ran from 15:27:32 to
15:27:42 UTC: two attempts shared one Run ID and the same gateway, each with a
one-call allowance. Both completed their Finnhub company-profile call with
source provenance, taking 5.21 and 4.81 seconds (2,073 and 834 chargeable tokens).
Contract tests separately cover exhausted reconnects, a rejected fourth attempt,
malformed headers, mid-Run cap changes and registry saturation. No full autonomous
cycle was run after this last fix; the real two-attempt probe and complete
regression gate are its present verification boundary.

Across these three cycles, two additional forming Opportunity records were
saved, increasing the seven-day registry from two to four distinct records.
Both are research leads, not approved investments. No new Expression or open
Shadow position was created; no brokerage order was sent. The two new records
were independently readable through the authenticated detail API. The final
seven-endpoint API check returned HTTP 200 throughout, with 401 for an
unauthenticated runtime read; its child server then closed. No unsupported-tool
router errors were observed in the third cycle's log window.

### Final checks and remaining limits

- **788 tests passed:** 279 Node, 394 research-runtime, 38 Tiger Paper,
  44 broker-connector and 33 dashboard tests. Ruff, formatting, Markdown lint,
  frontend lint, TypeScript checking and the production dashboard build passed.
- Exact-value comparison against six configured secrets found no matches in
  414 first-party source, test and documentation files. This is a scoped local
  check, not a complete Git-history or unknown-secret audit. No repository-host
  operations or publication were performed.
- Research clients and temporary API servers exited. Managed service/dashboard
  remained stopped, with no ALTA-owned child or listener on 8876/8877 found.
  ALTA PostgreSQL/Redis and disposable test containers were stopped; production
  research volumes were retained. Unrelated applications were left untouched.
- Public search quality, source access, primary-document coverage, current
  consensus access and occasional model schema/deadline failures remain real
  limitations. The observed increase is a small engineering sample, not proof of
  better hit rate, decision-grade Alpha, profitable execution or multi-day uptime.

## Follow-up: tool deadlines and wider Scout access

The September 12 follow-up keeps the four distinct Trader Minds and their
evidence gates, while giving each access to 13 bounded read-only research tools.
Sitemaps, feeds, archives, academic sources and social-page reading are available
alongside search, issuer crawling and structured finance. Default capacity is
11 calls, 98,000 chargeable tokens and 300 seconds per attempt. One call and
2,000 tokens remain below the existing ceilings for earned research incentives.
Explicit operator settings and reviewer budgets remain unchanged. More calls
are a research allowance, not a required number of candidates or orders.

### Network and source handling

- A shared deadline helper covers cancellation, late responses and synchronous
  self-cancellation without unhandled rejections. Search engines have a default
  20-second deadline; federation keeps successful peers and labels partial results.
- HTTP requests have a 45-second end-to-end bound covering DNS, queue admission,
  redirects, retries, `Retry-After` delays and streamed bodies. A 90-second
  whole-tool bound also covers discovery preflight outside an HTTP request.
  Operator configuration is passed to the trusted gateway, not the Agent process.
- Cancellation releases capacity and closes response readers. Redirect bodies
  are cancelled before continuing; custom headers stay within their origin and
  cross-origin request bodies are rejected. HTTP error bodies are never echoed
  into model output. Ordinary HTTP refusal still permits the bounded reader
  fallback; site-policy refusals and cancellation do not.
  Cancelled reads cannot return a warm cache hit, and service shutdown cannot
  convert an in-flight failure into a stale-cache success.
- Feed query/date filters run before the output limit, over at most 500 entries.
  HTML returned instead of a feed is an explicit failure, not an empty success.
  Unknown dates cannot satisfy a date window. SEC submissions filter filing
  dates before limiting and preserve acceptance time and report date separately.
  This follows the [SEC submissions API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces);
  none of these timestamps independently proves a current market catalyst.

The focused tests include stalled DNS, ignored aborts, stalled body streams,
long retry delays, cross-origin credential isolation, provider failover and
150 successive cancellation/recovery operations without accumulating capacity
or abort listeners. These are fault-injection tests, not a multi-day soak.

### Real retrieval and autonomous results

From 15:54:06 to 15:54:34 UTC, 14 bounded read-only requests exercised all
13 Scout tool families. Feed filtering returned two recent Federal Reserve
items; SEC returned three date-scoped filings; Finnhub returned a company
profile; academic federation returned three records; public social search
returned three results; a company sitemap returned five URLs. Page retrieval,
batch retrieval, scoped research, crawling, social reading and historical
capture lookup also returned. Archive lookup took 24.5 seconds; other requests
took about 0.14–1.38 seconds in this sample. The selected general search and
news queries had zero matching results: reachable tools are not proof of useful
recall. Capacity was zero and the tool service was closed after the probe.

Among optional external tool credentials, only Finnhub was available to this
standalone probe. Public endpoints were used for the other requests; the test
does not validate unconfigured Brave, Jina, OpenAlex or SearXNG accounts.

Cycle `live-20260912-155306-212949` ran from 15:53:06 to 16:03:10 UTC using
four DeepSeek v4 Flash Scouts with the increased budget. It completed `MVP_IDLE`
and exit 0, with two Candidates, one no-op and one failed Scout. Five failed
attempts were retained: three change-event, one expectation-gap and one
market-dislocation attempt. All five exceeded the output byte ceiling.
Zero unsupported-tool router errors were observed in the cycle's log window.

| New research hypothesis                                  | Record                                         | Evidence state                                          | Downstream outcome                                         |
| -------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------- |
| SXT: natural-color capacity versus regulatory transition | `opportunity_cec577fdd6874aa678d61fff14a5a662` | `screen_grade`; independent counterevidence not bound   | Forming, limited investability                             |
| UNH: earnings expectations versus observed repricing     | `opportunity_56059a51f1d8fe44739ea50209ab8313` | `cross_checked`; five cited records across four domains | Thesis assessor: hold/wait; disconfirming assessor: reject |

These are Agent-generated hypotheses, not independently established investment
conclusions. Both stayed forming. No new rank or Expression was created; there
were no open Shadow positions and no order execution. The seven-day Opportunity
registry grew from four to six, which is not proof of increased decision-grade
yield. The UNH assessments used DeepSeek v4 Pro and Grok 4.6. Their disagreement
was retained rather than overruling rejection to produce a transaction.

Across ten recorded model attempts, including failures and both assessments,
provider usage totaled 1,795,167 tokens, including 1,475,840 cached-input tokens
and 141,437 output tokens. This is recorded usage, not a currency bill or a
per-cycle spending guarantee. Retry overhead remains material.

### Output repair and its verification boundary

The cycle used prompt v25. Repeated long narrative fields exhausted its unchanged
8,000-byte response ceiling. New generation guidance caps each main prose field
at 320 characters and pillar fields at 160, reserving space for exact citations.
Returned content is never truncated or silently rewritten to pass validation;
historical parsing contracts and the byte/evidence gates remain unchanged.

A separate v26 change-event turn produced 5,709 bytes in 95.24 seconds, but the
existing validator correctly rejected invented frozen-evidence IDs. Prompt v27
and its generated schema now distinguish frozen IDs from newly retrieved tool
references explicitly, including an empty ID list when frozen evidence is empty.

The final v27 real turn (`run_b940175cbe92408a91850707304780a9`) ran from
16:06:12 to 16:07:35 UTC. It completed on its first attempt with 11 chargeable
tool calls, 29,972 chargeable tokens and a 5,162-byte Candidate. Budget, allowed
tool territory, exact source binding and output validation passed. Some news
queries still returned no sources. This was a standalone contract probe: it
did not persist another Opportunity or run downstream assessment. There was
no second full autonomous cycle after the final prompt repair.

### Verification and remaining limitations

The complete first-party gate passed **812 tests**: 302 Node, 395 research-runtime,
38 Tiger Paper, 44 broker-connector and 33 dashboard tests, with Ruff, formatting,
Markdown/frontend lint, TypeScript checking and the production frontend build.
The local API returned 200 for health, runtime, summary, MVP status and both new
Opportunity detail routes; an unauthenticated runtime read returned 401. These
small read samples do not certify browser behavior under every fault.

Real-source availability, public-search precision, schema adherence, independent
counterevidence, multi-day opportunity follow-up and profitable execution remain
unproven or incomplete. In-memory gateway counters and source queues are not an
account-wide durable quota service. No claim of zero future faults, guaranteed
24x7 uptime, Alpha or commercial production certification follows from this pass.

All research and temporary API clients were closed. Managed service and scheduler
were confirmed stopped; no matching ALTA research/App Server process or listener
on 8876/8877 remained. ALTA PostgreSQL/Redis and the isolated test containers were
stopped; production data volumes were retained and unrelated applications were
left running. An exact-value scan of 422 first-party files against six configured
secrets found no matches; this is not a complete history or unknown-secret audit.
No repository-host operation, publication, market-data execution request or
brokerage order was performed.
