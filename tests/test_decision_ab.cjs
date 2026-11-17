"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const web = path.join(__dirname, "..", "urbanflow-web");

test("la comparación experimental se abre desde la demostración", () => {
  const page = fs.readFileSync(path.join(web, "index.html"), "utf8");
  const app = fs.readFileSync(path.join(web, "app.js"), "utf8");
  const view = fs.readFileSync(path.join(web, "decision-ab.js"), "utf8");
  assert.match(page, /id="decision-demo-link" href="#decision-ab"/);
  assert.match(page, /href="#decision-ab">Comparación experimental de Roosevelt y Honduras/);
  assert.match(page, /id="decision-rows"/);
  assert.match(page, /id="decision-demand-rows"/);
  assert.match(page, /id="decision-clearance-rows"/);
  assert.match(view, /assets\/decision-demand.json/);
  assert.match(view, /assets\/decision-clearance.json/);
  assert.match(app, /hash === "#decision-ab"/);
  assert.match(app, /showDecision\(version\)/);
  assert.match(view, /data\.experimental !== true \|\| data\.calibrated !== false/);
  assert.doesNotMatch(app, /Williman|Roosevelt|r1161502532|sector01-williman|pilot-roosevelt|18 de Julio/);
});

test("el resultado publicado sigue marcado como experimental", () => {
  const report = JSON.parse(fs.readFileSync(path.join(web, "assets", "decision-roosevelt.json"), "utf8"));
  assert.equal(report.experimental, true);
  assert.equal(report.calibrated, false);
  assert.equal(report.queues.measured, false);
  for (const id of ["meanTravel", "meanWait", "completed"]) {
    const metric = report.metrics[id];
    assert.equal(typeof metric.a, "number");
    assert.equal(typeof metric.b, "number");
    assert.equal(typeof metric.absolute, "number");
    assert.ok(metric.percent === null || typeof metric.percent === "number");
  }
  assert.match(report.notice, /experimental/);
  assert.match(report.notice, /Intendencia/);
  assert.match(report.method.join(" "), /No es un plan de la Intendencia/);
});
