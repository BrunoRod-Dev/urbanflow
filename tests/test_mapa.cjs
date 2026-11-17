"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const web = path.join(__dirname, "..", "urbanflow-web");
const page = fs.readFileSync(path.join(web, "index.html"), "utf8");
const app = fs.readFileSync(path.join(web, "app.js"), "utf8");
const map = fs.readFileSync(path.join(web, "mapa.js"), "utf8");
const forbidden = /Williman|Roosevelt|r1161502532|sector01-williman|pilot-roosevelt|18 de Julio/;

test("el mapa es la entrada y la ayuda no lleva a otras secciones", () => {
  assert.match(page, /href="#mapa" data-view="mapa"/);
  assert.match(page, /data-view="estudios"/);
  assert.match(page, /data-view="comparaciones"/);
  assert.match(page, /id="mapa"/);
  assert.match(page, /id="territory-zones"/);
  assert.match(page, /El resto del territorio no tiene simulación disponible/);
  const help = page.slice(page.indexOf('id="help-menu"'), page.indexOf("</details>"));
  assert.doesNotMatch(help, /href="/);
  assert.match(page, /href="#decision-ab">Comparación experimental de Roosevelt y Honduras/);
  assert.match(page, /href="#novillo"/);
  assert.match(page, /href="#ejemplos"/);
  assert.match(app, /location\.replace\("#mapa"\)/);
  assert.match(app, /hash === "#mapa"/);
  assert.match(app, /showTerritory\(geographicMap/);
  assert.match(app, /view === "mapa" \|\| view === "novillo" \? "mapa"/);
  assert.match(app, /view === "decision" \|\| view === "comparacion" \? "comparaciones"/);
  assert.doesNotMatch(app, forbidden);
  assert.doesNotMatch(app, /examples-link/);
});

test("las zonas salen de los manifiestos y de los casos publicados", () => {
  assert.match(map, /loadSectorCatalog/);
  assert.match(map, /assets\/novillo-alegre\.geojson/);
  assert.match(map, /assets\/novillo-experimento\.json/);
  assert.match(map, /osmWay === "100089298"/);
  assert.match(map, /fieldValidated !== false/);
  assert.match(map, /report\.comparison !== null \|\| report\.simulated !== null/);
  assert.match(map, /Simulación validada técnicamente, sin calibración municipal/);
  assert.match(map, /Solo geometría\. Comparación detenida/);
  assert.match(map, /Sin simulación disponible/);
  assert.match(map, /Permite observar la circulación en 2D y 3D/);
  assert.match(map, /La comparación está detenida\. No hay resultados publicados/);
  assert.match(map, /\/api\/studies\/\$\{zone\.replayId\}\/replay/);
  assert.match(map, /properties\?\.used !== true/);
  assert.match(map, /geographic === true/);
  assert.doesNotMatch(map, /-34\.|-54\./);
});
