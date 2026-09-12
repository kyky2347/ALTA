# Research scope and non-goals

ALTA is an experimental research system for studying whether autonomous LLM
agents can discover, challenge, express, and monitor public-market
opportunities under point-in-time evidence constraints.

## In scope

- evidence-bound opportunity discovery;
- independent assessment, discussion, ranking, and expression auditing;
- replayable Shadow positions and cost-aware performance measurement;
- bounded, read-only public information and market-data adapters;
- a local authenticated observability and control dashboard;
- isolated six-provider connection profiles and read-only account verification;
- an operator-authorized, risk-sized Tiger Paper engineering mirror with
  explicit account/configuration binding and fail-closed startup.

## Explicitly out of scope

- investment advice, trade recommendations, or suitability assessment;
- live brokerage execution or management of real capital;
- promises of profitability, Alpha, accuracy, availability, or production SLA;
- automatic discovery of brokerage accounts or credentials;
- redistribution of third-party market data beyond its license.

The default capital mode is disabled. Tiger integration is limited to an
isolated Paper-only executor reached only after local operator authorization.
The stopped runtime must first prove the exact 17-digit Paper account, matching
configuration, an empty position book, and zero open orders. Once authorized,
the autonomous service can mirror only already-audited stock expressions
through the agent-requested, deterministically bounded whole-share DAY-limit
regular-hours boundary; Agents never receive a
broker tool or credential. The console exposes sanitized holdings and order
state but no manual order entry. Additional connector profiles may explicitly
target live accounts for read-only verification; that does not change the
autonomous research route or grant trading authority. Do not use ALTA as an OMS.
A successful Paper entry/exit is engineering evidence, not
investment or Alpha evidence.

Model output is untrusted research material. A Candidate or Opportunity is a
hypothesis, not a fact. `Wait` and `MVP_IDLE` are valid outcomes, and Alpha
remains unproven until supported by a sufficiently large forward Shadow sample.
