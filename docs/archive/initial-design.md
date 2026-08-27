# Initial Trader Society design

This document preserves the intent of the design that preceded the current ALTA
Opportunity OS. It is a historical record, not current operating guidance.

## Original problem framing

The initial concept was a multi-Agent “trader society”: a standing group of
specialized analysts would repeatedly review markets, debate long and short
cases, and pass a decision to an execution layer. That framing borrowed useful
ideas from research-agent systems, including role specialization, adversarial
debate, explicit risk review, and structured hand-offs.

It also exposed a central weakness. Starting from a fixed roster and a supplied
ticker forces activity even when nothing changed. The system becomes good at
producing an analysis artifact, but not necessarily at discovering a novel,
time-sensitive opportunity.

## Shift to an Opportunity OS

The design evolved from Agent-centric to opportunity-centric:

| Earlier framing | Current framing |
| --- | --- |
| A fixed team analyzes a ticker | Several Scouts search for information changes |
| Every cycle should produce a view | A no-op or idle cycle is valid |
| Debate is the organizing object | The versioned Opportunity is the organizing object |
| Roles share a conversational context | Roles receive isolated frozen inputs |
| The model can implicitly rank ideas | Ranking gates and components are deterministic |
| Trade choice follows the debate | A separate Agent selects the payoff shape |
| Risk review is part of the same group | An independent Auditor reviews implementation |
| Monitoring is generic | A bounded Monitor checks only the frozen falsifier |
| Success means the workflow completed | Success is measured with forward Shadow outcomes |

The most important retained principle is that multiple skilled perspectives can
cover different information territories and causal styles. The most important
change is that those perspectives are now organized around durable evidence and
Opportunity objects instead of a theatrical committee.

## Ideas retained in the current architecture

### Specialized discovery

Different Agents should search different corners of the market rather than
duplicate a generic finance prompt. The current Scout pool covers recent factual
changes, market dislocations, causal policy effects, and expectation gaps.

### Independent challenge

A thesis should face a serious falsification attempt before implementation. The
current system locks a Thesis assessment and a Disconfirming assessment before
either is shared, which reduces anchoring.

### Bounded debate

Discussion is useful when it identifies a causal disagreement or a decisive
falsifier. It becomes harmful when it manufactures confidence from rhetoric.
The current Moderator is limited to two evidence-bound rounds, and discussion
never becomes Evidence.

### Expression as a separate problem

Being correct about an event does not automatically identify the best listed
instrument. The current Expression Agent separately compares Stock, ETF, Option,
and Wait, while deterministic code owns exact contract and quote truth.

### Independent implementation audit

The implementation should be reviewed without the psychological pressure of the
ranking score. The current Expression Auditor cannot see that score and can only
approve or require Wait.

### Outcome feedback

Every Candidate, rejection, forecast, expression, no-fill, hold, exit, and
benchmark should be retained so the system can learn which roles and sources
actually add value. This led to the current append-only artifacts and forward
Shadow measurement surface.

## Ideas deliberately rejected or deferred

- forcing a recommendation from every Agent cycle;
- giving Agents unrestricted shell, database, credential, or broker access;
- using debate length or consensus as a quality metric;
- allowing an LLM to invent current prices, liquidity, or option contracts;
- live trading before sustained forward Shadow evidence;
- a large permanent society before the vertical slice is measurable;
- self-adjusting role weights from a small sample;
- treating a working demo as proof of Alpha.

## External inspiration and ownership

The early design reviewed several public multi-Agent and trading-research
projects for architectural ideas. ALTA does not claim authorship of third-party
work. The implemented system uses its own Opportunity contracts, persistence,
safety boundaries, tests, and orchestration around a pinned and attributed Codex
App Server substrate.

Current provenance and licensing are defined in
[ATTRIBUTION.md](../../ATTRIBUTION.md), not in this historical record.

## Current source of truth

Use these documents instead of the original design notes:

- [Architecture overview](../architecture/overview.md)
- [Detailed Opportunity OS design](../architecture/opportunity-os.md)
- [Implementation roadmap](../implementation/roadmap.md)
- [Autonomous Shadow operations](../operations/autonomous-shadow.md)
- [Research scope and non-goals](../research-scope.md)

This consolidated record preserves the design changes that remain relevant to
the current system without treating obsolete working notes as active guidance.
