"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const web = path.join(__dirname, "..", "urbanflow-web");

test("el experimento se muestra como bloqueo y no como tabla de resultados", () => {
  const page = fs.readFileSync(path.join(web, "index.html"), "utf8");
  const app = fs.readFileSync(path.join(web, "app.js"), "utf8");
  const view = fs.readFileSync(path.join(web, "novillo.js"), "utf8");
  const report = JSON.parse(fs.readFileSync(path.join(web, "assets", "novillo-experimento.json"), "utf8"));
  assert.match(page, /id="novillo-experiment"/);
  assert.match(view, /showNovilloExperiment/);
  assert.match(view, /report\.comparison !== null \|\| report\.simulated !== null/);
  assert.doesNotMatch(app, /Williman|Roosevelt|r1161502532|sector01-williman|pilot-roosevelt|18 de Julio/);
  assert.equal(report.comparison, null);
  assert.equal(report.simulated, null);
  assert.equal(report.experimental, true);
  assert.equal(report.calibrated, false);
  assert.equal(report.seasonal, false);
  assert.equal(report.routes.sharedDestinationEdges.length, 0);
  assert.equal(report.speedAssumption.signage, false);
  assert.equal(report.speedAssumption.kmh, 30);
});
