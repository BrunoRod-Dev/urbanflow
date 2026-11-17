import assert from "node:assert/strict";
import test from "node:test";
import { buildingHeight } from "../urbanflow-web/geography-heights.js";

const rule = { metersPerLevel: 3.1, provisionalMeters: 2.8 };

test("a numeric height is kept as a measurement", () => {
  assert.deepEqual(buildingHeight({ height: 18.5, levels: 4 }, rule), { meters: 18.5, source: "measured" });
});

test("levels become a labeled estimate and missing data stays provisional", () => {
  assert.deepEqual(buildingHeight({ height: null, levels: 16 }, rule), { meters: 49.6, source: "estimated" });
  assert.deepEqual(buildingHeight({ height: null, levels: null }, rule), { meters: null, source: "provisional" });
});
