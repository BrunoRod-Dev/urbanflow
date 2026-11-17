"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const web = path.join(__dirname, "..", "urbanflow-web");

test("el caso geométrico se abre sin mezclarlo con el visor certificado", () => {
  const page = fs.readFileSync(path.join(web, "index.html"), "utf8");
  const app = fs.readFileSync(path.join(web, "app.js"), "utf8");
  const view = fs.readFileSync(path.join(web, "novillo.js"), "utf8");
  const geo = JSON.parse(fs.readFileSync(path.join(web, "assets", "novillo-alegre.geojson"), "utf8"));
  const report = JSON.parse(fs.readFileSync(path.join(web, "assets", "novillo-alegre.json"), "utf8"));
  assert.match(page, /href="#novillo"/);
  assert.match(page, /id="novillo-map"/);
  assert.match(app, /hash === "#novillo"/);
  assert.match(app, /showNovillo\(\)/);
  assert.doesNotMatch(app, /Williman|Roosevelt|r1161502532|sector01-williman|pilot-roosevelt|18 de Julio/);
  assert.match(view, /report\.experimental !== true \|\| report\.calibrated !== false/);
  assert.match(view, /report\.comparison !== null/);
  assert.equal(report.experimental, true);
  assert.equal(report.calibrated, false);
  assert.equal(report.seasonal, false);
  assert.equal(report.comparison, null);
  const labels = new Set(geo.features.map(feature => feature.properties.label).filter(Boolean));
  for (const label of ["Roosevelt", "Artigas", "Parada 5", "Francia", "Pedragosa", "Avenida del Mar"]) {
    assert.equal(labels.has(label), true);
  }
  assert.equal(geo.features.some(feature => feature.properties.verified === false), true);
});
