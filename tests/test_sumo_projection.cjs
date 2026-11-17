"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.join(__dirname, "..", "urbanflow-web");
const context = { Math, Number, Array, Error, String, Object };
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root, "sumo-projection.js"), "utf8"), context);
vm.runInContext(fs.readFileSync(path.join(root, "scene-coordinates.js"), "utf8").replace(/^export /gm, ""), context);
vm.runInContext(fs.readFileSync(path.join(root, "lane-motion.js"), "utf8"), context);

const certified = {
  type: "utm",
  projParameter: "+proj=utm +zone=21 +ellps=WGS84 +datum=WGS84 +units=m +no_defs",
  netOffset: [-687641.22, 3870713.94],
  zone: 21,
  falseNorthing: 0,
};
const certifiedNode = { sumo: [319.83, 1909.53], geo: [-54.9417367, -34.9443359] };

function meters(actual, expected) {
  const lat = expected[1] * Math.PI / 180;
  return Math.hypot((actual[0] - expected[0]) * Math.cos(lat), actual[1] - expected[1]) * 111320;
}

test("la conversión del visor reproduce el cruce certificado a menos de 1 cm", () => {
  const converter = context.createSumoProjection(certified);
  const geo = converter.toGeo(...certifiedNode.sumo);
  assert.ok(meters(geo, certifiedNode.geo) < 0.01, `${meters(geo, certifiedNode.geo)} m`);
  const back = converter.toSumo(...certifiedNode.geo);
  assert.ok(Math.hypot(back[0] - certifiedNode.sumo[0], back[1] - certifiedNode.sumo[1]) < 0.01);
});

test("dos ventanas de una red de 30 km comparten el mismo punto", () => {
  const converter = context.createSumoProjection(certified);
  const west = context.createSceneCoordinates(certified, [-54.95, -34.96]);
  const east = context.createSceneCoordinates(certified, [-54.90, -34.94]);
  const point = [-54.93, -34.95];
  const other = [-54.92, -34.945];
  const left = west.fromGeo(point).map((value, axis) => other && value - west.fromGeo(other)[axis]);
  const right = east.fromGeo(point).map((value, axis) => value - east.fromGeo(other)[axis]);
  left.forEach((value, axis) => assert.ok(Math.abs(value - right[axis]) < 1e-6));
  const far = converter.toGeo(certifiedNode.sumo[0] + 30000, certifiedNode.sumo[1] + 30000);
  const round = converter.toSumo(...far);
  assert.ok(Math.hypot(round[0] - certifiedNode.sumo[0] - 30000, round[1] - certifiedNode.sumo[1] - 30000) < 0.01);
  assert.ok(Number.isFinite(west.bearing(-34.95, 0)));
});

test("la interpolación UTM ancla los extremos del FCD", () => {
  const lane = { edge: "A", length: 100, points: [[0, 0], [100, 0]] };
  const motion = context.createLaneMotion({
    lanes: { a: lane },
    links: {},
    projection: certified,
  });
  const start = [1, -54.9417, -34.9443, 90, 10, "", "a", 10, 5];
  const end = [1, -54.9416, -34.9443, 90, 10, "", "a", 40, 5];
  motion.beginFrame([start]);
  assert.deepEqual(motion.between(start, end, 0, 3), motion.sample(start));
  assert.deepEqual(motion.between(start, end, 1, 3), motion.sample(end));
});

test("una proyección ausente, mezclada o desconocida explica por qué no hay 3D", () => {
  const absent = context.describeProjection(null);
  const empty = context.describeProjection({ projection: null, projectionError: "La red no declara projParameter." });
  const mixed = context.describeProjection({
    projection: { type: "utm", east: [1, 0], north: [0, 1], origin: [0, 0], location: [0, 0],
      zone: 21, netOffset: [0, 0], falseNorthing: 0 },
  });
  const unknown = context.describeProjection({ projection: { type: "longlat" } });
  assert.equal(absent.ok, false);
  assert.match(absent.message, /geometría de carriles/);
  assert.match(empty.message, /projParameter/);
  assert.match(mixed.message, /no elige entre las dos/);
  assert.match(unknown.message, /no está soportada/);
  assert.equal(context.describeProjection({ projection: certified }).ok, true);
  assert.equal(context.describeProjection({
    projection: { origin: [0, 0], location: [-54.94, -34.95], east: [1e-5, 0], north: [0, 9e-6] },
  }).kind, "affine");
});
