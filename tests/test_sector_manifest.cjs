"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const web = path.join(root, "urbanflow-web");
const context = { Math, Number, Array, Error, String, Object, JSON, Promise, WeakMap, Map, Set };
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(web, "sumo-projection.js"), "utf8"), context);
vm.runInContext(fs.readFileSync(path.join(web, "sector-config.js"), "utf8"), context);

const index = JSON.parse(fs.readFileSync(path.join(web, "sectors", "index.json"), "utf8"));
const sectors = index.sectors.map(name => {
  const sector = JSON.parse(fs.readFileSync(path.join(web, "sectors", name), "utf8"));
  context.validateSector(sector, name);
  return sector;
});

function study(extra = {}) {
  return {
    geographic: true,
    bounds: [-54.94415, -34.9608, -54.9364, -34.9437],
    location: [-54.9414873, -34.95144055],
    laneMotion: {
      projection: {
        origin: [0, 0],
        location: [-54.9414873, -34.95144055],
        east: [0.00001, 0],
        north: [0, 0.00001],
      },
      lanes: {},
    },
    ...extra,
  };
}

test("el índice declara los dos sectores existentes y una sola vía de lectura", () => {
  assert.deepEqual(index.sectors, ["sector01.json", "roosevelt-camacho.json"]);
  assert.deepEqual(sectors.map(sector => sector.id), ["sector01", "roosevelt-camacho"]);
  const replayViews = fs.readFileSync(path.join(web, "replay-views.js"), "utf8");
  const app = fs.readFileSync(path.join(web, "app.js"), "utf8");
  assert.match(replayViews, /prepareStudySector/);
  assert.match(app, /prepareStudySector/);
  for (const source of [replayViews, app, fs.readFileSync(path.join(web, "sector-config.js"), "utf8")]) {
    assert.doesNotMatch(source, /Williman|Roosevelt|r1161502532|sector01-williman|pilot-roosevelt|18 de Julio/);
  }
});

test("Sector 01 conserva el encuadre del estudio y la ambientación declarada", () => {
  const config = context.sceneForStudy(study(), sectors);
  assert.equal(config.sectorId, "sector01");
  assert.equal(config.pilot, false);
  assert.equal(config.signals, null);
  assert.deepEqual(config.bounds, [-54.94415, -34.9608, -54.9364, -34.9437]);
  assert.equal(config.cameras.initial, "oblique");
  assert.equal(config.cameras.followWithDressing, "oblique");
  assert.equal(config.cameras.signalsLabel, "Semáforos del cruce");
  assert.match(config.dressing.geography, /sector01-williman-geography\.json/);
  assert.equal(config.dressing.group, "geography");
  assert.equal(config.signalControllers.length, 23);
  assert.ok(config.signalControllers.every(item => item.program === "inferred"));
  assert.equal(context.signalProgramCaption(config.signalControllers), " · Semáforos estimados");
  assert.equal(config.projection, undefined);
});

test("Roosevelt conserva la cámara, las referencias y el semáforo declarado", () => {
  const config = context.sceneForStudy(study({
    junctionId: "r1161502532",
    bounds: [-54.97, -34.92, -54.95, -34.91],
    location: [-54.9595, -34.9159],
  }), sectors);
  assert.equal(config.sectorId, "roosevelt-camacho");
  assert.equal(config.pilot, true);
  assert.equal(config.streetLane, "783169882#0_0");
  assert.deepEqual(config.bounds, [-54.962, -34.91665, -54.95815, -34.91395]);
  assert.equal(config.signals.controller, "joinedS_1360014840_13966777057_13966777058_2375592994");
  assert.deepEqual(config.signals.center, [-54.9614, -34.91426]);
  assert.equal(config.signals.approach, "1532518649#0_0");
  assert.deepEqual(config.references.map(item => item.label), ["A", "B"]);
  assert.equal(config.references[0].title, "Incorporación a Roosevelt");
  assert.equal(config.dressing.buildings, "assets/pilot-roosevelt-buildings.geojson");
  assert.equal(config.dressing.curbSurvey, "assets/terminal-curb-survey.geojson");
  assert.equal(config.cameras.signalsLabel, "Roosevelt y Honduras");
  assert.equal(config.cameras.curb.origin, "18 de Julio");
  assert.match(context.signalProgramCaption(config.signalControllers), /captura de campo/);
  const crossing = context.sceneForStudy(study({
    pedestrianReplay: { crossing: { location: [-54.959, -34.915] } },
  }), sectors);
  assert.equal(crossing.sectorId, "roosevelt-camacho");
  assert.deepEqual(crossing.bounds, [-54.962, -34.91665, -54.95675, -34.91395]);
  assert.deepEqual(crossing.crossing, [-54.959, -34.915]);
});

test("un sector nuevo entra por la misma función, sin otra ruta de carga", () => {
  const added = {
    ...sectors[0],
    id: "sector-prueba",
    bounds: [-54.942, -34.952, -54.94, -34.95],
    dressing: { geography: "assets/sector-prueba.json", group: "geography" },
    signals: [{ id: "probado", program: "validated" }],
  };
  const config = context.sceneForStudy(study(), sectors.concat(added));
  assert.equal(config.sectorId, "sector-prueba");
  assert.equal(config.dressing.geography, "assets/sector-prueba.json");
  assert.equal(context.signalProgramCaption(config.signalControllers), " · Programa contrastado en campo");
  const tied = context.sceneForStudy(study(), sectors.concat(added, { ...added, id: "sector-empate" }));
  assert.match(tied.sectorError, /cubren la misma zona/);
  const duplicated = context.sceneForStudy(study({ junctionId: "r1161502532" }), sectors.concat({
    id: "otro-cruce", match: { junctionIds: ["r1161502532"] }, bounds: added.bounds, signals: [],
  }));
  assert.match(duplicated.sectorError, /Varios sectores reclaman el cruce/);
});

test("una proyección ausente se informa y un estudio fuera de los sectores sigue abriendo", () => {
  const missing = context.sceneForStudy(study({ laneMotion: { projection: null, lanes: {} } }), sectors);
  assert.match(missing.projectionError, /proyección/);
  assert.equal(missing.sectorId, undefined);
  const outside = context.sceneForStudy(study({
    bounds: [-56.2, -34.95, -56.1, -34.9],
    location: [-56.15, -34.92],
  }), sectors);
  assert.equal(outside.sectorId, null);
  assert.equal(JSON.stringify(outside.dressing), "{}");
  assert.equal(outside.pilot, false);
  const utm = context.sceneForStudy(study({
    laneMotion: {
      projection: {
        type: "utm",
        projParameter: "+proj=utm +zone=21 +ellps=WGS84 +datum=WGS84 +units=m +no_defs",
        netOffset: [-687641.22, 3870713.94],
        zone: 21,
        falseNorthing: 0,
      },
      lanes: {},
    },
  }), sectors);
  assert.equal(utm.sectorId, "sector01");
  assert.equal(utm.projParameter, undefined);
});
