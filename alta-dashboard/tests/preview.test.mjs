import assert from "node:assert/strict";
import test from "node:test";
import { previewStatus } from "../src/lib/preview.ts";
import { latestRankLeader } from "../src/lib/opportunity-selection.ts";

test("synthetic preview follows the same complete ranking and freshness contract", () => {
  assert.equal(latestRankLeader(previewStatus)?.id, "opp-118");
  assert.ok(
    previewStatus.opportunities.every(
      (opportunity) =>
        opportunity.actionableNow &&
        opportunity.freshnessAt &&
        ["live", "current"].includes(opportunity.freshnessState),
    ),
  );
});
