# Research scope and non-goals

ALTA is an experimental research system for studying whether autonomous LLM
agents can discover, challenge, express, and monitor public-market
opportunities under point-in-time evidence constraints.

## In scope

- evidence-bound opportunity discovery;
- independent assessment, discussion, ranking, and expression auditing;
- replayable Shadow positions and cost-aware performance measurement;
- bounded, read-only public information and market-data adapters;
- observability artifacts for future research dashboards;
- one explicitly invoked, one-share Tiger Paper engineering acceptance cycle.

## Explicitly out of scope

- investment advice, trade recommendations, or suitability assessment;
- live brokerage execution or management of real capital;
- promises of profitability, Alpha, accuracy, availability, or production SLA;
- automatic discovery of brokerage accounts or credentials;
- redistribution of third-party market data beyond its license.

The default capital mode is disabled. Tiger integration is limited to an
isolated Paper-only executor that can be reached only by the explicit bounded
acceptance command. It is not available to Agents, the read API, or the normal
autonomous service. Do not connect live brokerage credentials or use ALTA as an
OMS. A successful Paper entry/exit is engineering evidence, not investment or
Alpha evidence.

Model output is untrusted research material. A Candidate or Opportunity is a
hypothesis, not a fact. `Wait` and `MVP_IDLE` are valid outcomes, and Alpha
remains unproven until supported by a sufficiently large forward Shadow sample.
