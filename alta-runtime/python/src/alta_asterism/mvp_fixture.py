import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .mind_worker import ModelTurn, ScoutDeadlineExceeded, ToolEvidenceDiscovery
from .scouts import ScoutRunSpec, ToolProvenance


class FixtureSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    raw_source: str
    territory: str
    summary: str
    default_posture: Literal["healthy", "disabled", "stale"]


class CandidateTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    why_now: str
    expectation: str
    variant_wedge: str
    falsifier: str
    confidence: float = Field(ge=0, le=1)


class FixturePrice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bid: str
    ask: str


class MvpFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_version: str
    universe: tuple[str, ...] = Field(min_length=1, max_length=50)
    symbol: str
    sources: tuple[FixtureSource, ...]
    candidate_templates: dict[str, CandidateTemplate]
    prices: dict[str, FixturePrice]

    @classmethod
    def default(cls) -> "MvpFixture":
        path = Path(__file__).with_name("fixtures") / "b6_demo.json"
        return cls.model_validate_json(path.read_text())


class FixtureMindClient:
    def __init__(
        self,
        fixture: MvpFixture,
        timed_out_scouts: tuple[str, ...] = (),
    ) -> None:
        self.fixture = fixture
        self.timed_out_scouts = frozenset(timed_out_scouts)
        self.calls: list[str] = []

    def run(self, spec: ScoutRunSpec, _prompt: str, _schema: dict) -> ModelTurn:
        scout_id = spec.scout.scout_id
        self.calls.append(scout_id)
        if scout_id in self.timed_out_scouts:
            raise ScoutDeadlineExceeded("fixture Scout timeout")
        evidence_ids = tuple(item.evidence_id for item in spec.frozen_input.evidence)
        if not evidence_ids:
            output = {
                "kind": "no_op",
                "reason": "No fresh enabled evidence in this Scout territory.",
                "evidence_ids": [],
            }
        else:
            template = self.fixture.candidate_templates[scout_id]
            output = {
                "kind": "candidate",
                "alpha_archetype": spec.scout.alpha_archetypes[0],
                **template.model_dump(mode="json"),
                "horizon": 10,
                "beneficiary_path": (
                    "The measured change reaches the listed issuer's cash-flow path."
                ),
                "disconfirming_evidence": (
                    "The next versioned primary update may reverse the change."
                ),
                "next_test": "Verify the next issuer operating update.",
                "thesis_pillars": [
                    {
                        "statement": template.variant_wedge,
                        "observable": template.why_now,
                        "confirmation_condition": template.expectation,
                        "invalidation_condition": template.falsifier,
                        "expected_by_days": 5,
                    }
                ],
                "evidence_ids": evidence_ids,
            }
        tools = ()
        discoveries = ()
        if output["kind"] == "candidate":
            tool_names = (
                "alta_web_search",
                "alta_web_batch_fetch",
                "alta_finance_data",
            )
            tools = tuple(
                ToolProvenance(
                    tool_call_id=f"fixture_tool_{scout_id}_{index}",
                    tool_name=tool_name,
                    status="completed",
                    arguments_hash=character * 64,
                )
                for index, (tool_name, character) in enumerate(
                    zip(tool_names, "abc", strict=True), start=1
                )
            )
            base_discoveries = tuple(
                ToolEvidenceDiscovery(
                    tool_call_id=tool.tool_call_id,
                    tool_name=tool.tool_name,
                    source_locator=(
                        f"https://fixture-source-{index}.example/{scout_id}"
                    ),
                    content={
                        "fixture": True,
                        "source": index,
                        "result_text": f"Fixture research result {index} for {scout_id}.",
                    },
                    content_hash=character * 64,
                )
                for index, (tool, character) in enumerate(
                    zip(tools, "def", strict=True), start=1
                )
            )
            counterevidence = ToolEvidenceDiscovery(
                tool_call_id=tools[0].tool_call_id,
                tool_name=tools[0].tool_name,
                source_locator=f"https://fixture-source-4.example/{scout_id}",
                content={
                    "fixture": True,
                    "source": 4,
                    "result_text": (
                        f"Independent fixture counterevidence for {scout_id}."
                    ),
                },
                content_hash="0" * 64,
            )
            discoveries = (*base_discoveries, counterevidence)
            evidence_roles = (
                "primary_fact",
                "mechanism",
                "market_context",
                "counterevidence",
            )
            output["tool_evidence_refs"] = [
                {
                    "tool_call_id": discovery.tool_call_id,
                    "evidence_role": evidence_role,
                    "source_locator": discovery.source_locator,
                }
                for discovery, evidence_role in zip(
                    discoveries, evidence_roles, strict=True
                )
            ]
        return ModelTurn(
            final_response=json.dumps(output, separators=(",", ":")),
            thread_id=f"fixture_thread_{scout_id}",
            turn_id=f"fixture_turn_{scout_id}",
            total_tokens=100,
            tools=tools,
            discovered_evidence=discoveries,
        )
