"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../urbanflow-web/lane-motion.js"), "utf8");
const createLaneMotion = vm.runInNewContext(`${source}\ncreateLaneMotion`);
const fixture = require("./fixtures/lane_motion_sector01.json");
const metersPerDegree = 111320;
const radians = Math.PI / 180;
const angleError = (a, b) => Math.abs((a - b + 540) % 360 - 180);
const near = (actual, expected, tolerance = 1e-6) => assert.ok(
  Math.abs(actual - expected) <= tolerance, `${actual} vs ${expected}`);

function meterOffset(first, last) {
  return [(last[1] - first[1]) * metersPerDegree * Math.cos((first[2] + last[2]) / 2 * radians),
    (last[2] - first[2]) * metersPerDegree];
}

function recordedCenter(car) {
  const [, lng, lat, angle, , , , , length] = car;
  return [car[0], lng - Math.sin(angle * radians) * length / 2 / (metersPerDegree * Math.cos(lat * radians)),
    lat - Math.cos(angle * radians) * length / 2 / metersPerDegree, angle];
}

function verifyInterval(motion, first, last, seconds) {
  motion.beginFrame([first]);
  const startsAt = motion.sample(first);
  const endsAt = motion.sample(last);
  for (const [fraction, endpoint, sample] of [[0, first, startsAt], [1, last, endsAt]]) {
    const interpolated = motion.between(first, last, fraction, seconds);
    assert.deepEqual(interpolated, sample);
    near(Math.hypot(...meterOffset(recordedCenter(endpoint), sample)), 0);
    near(angleError(sample[3], endpoint[3]), 0);
  }
  const chord = meterOffset(startsAt, endsAt);
  const length = Math.hypot(...chord);
  const samples = [startsAt];
  for (let step = 1; step <= 20; step++) {
    const fraction = step / 20;
    const sample = motion.between(first, last, fraction, seconds);
    const forward = meterOffset(startsAt, sample).reduce((total, value, axis) => total + value * chord[axis], 0);
    near(forward, fraction * length * length, .0001);
    near(angleError(sample[3], samples.at(-1)[3]), angleError(first[3], last[3]) / 20);
    samples.push(sample);
  }
  return samples;
}

for (const { vehicleId, frames, motion: geometry } of fixture.cases) {
  test(`${vehicleId} mantiene los anclajes FCD antes y después de la conexión interna`, () => {
    const motion = createLaneMotion(geometry);
    const [[enterTime, entry], [internalTime, internal], [exitTime, exit]] = frames;
    verifyInterval(motion, entry, internal, internalTime - enterTime);
    verifyInterval(motion, internal, exit, exitTime - internalTime);
    const heading = vehicleId === "mansa-1" ? [-.05244770578754219, .9986236719393463]
      : [.8481387353233535, .5297741836330857];
    const projected = (first, last) => meterOffset(motion.sample(first), motion.sample(last))
      .reduce((total, value, axis) => total + value * heading[axis], 0);
    near(projected(entry, internal), vehicleId === "mansa-1" ? -.591 : -1.893, .002);
    near(projected(internal, exit), vehicleId === "mansa-1" ? 1.805 : 4.264, .002);
  });
}

const projection = { origin: [0, 0], location: [0, 0], east: [1 / metersPerDegree, 0],
  north: [0, 1 / metersPerDegree] };
const car = (x, y, angle, lane, pos, length = 5, speed = 8) =>
  [1, x / metersPerDegree, y / metersPerDegree, angle, speed, "", lane, pos, length];
const lane = (edge, length, points) => ({ edge, length, points });
const anchored = (lanes, links = {}) => createLaneMotion({ lanes, links, projection });

test("recta, rumbo 359° → 1° y vehículo largo conservan su referencia", () => {
  const motion = anchored({ a: lane("A", 25, [[0, 0], [0, 25]]) });
  const samples = verifyInterval(motion, car(0, 8, 359, "a", 8, 12), car(0, 12, 1, "a", 12, 12), .5);
  near(angleError(samples[10][3], 0), 0);
  near(samples[10][2] * metersPerDegree, 10 - 6 * Math.cos(radians));
});

test("giro conserva curvatura lateral y rumbo de referencia", () => {
  const motion = anchored({ a: lane("A", 5, [[0, 0], [0, 5]]),
    internal: lane(":J", 3, [[0, 5], [1, 6.5], [3, 7]]), b: lane("B", 7, [[3, 7], [10, 7]]) },
  { a: ["internal"], internal: ["b"] });
  const start = car(0, 3, 0, "a", 3, 2);
  const end = car(6, 7, 90, "b", 3, 2);
  const samples = verifyInterval(motion, start, end, .5);
  near(samples[10][3], 45);
  const midpoint = samples[10].slice(1, 3);
  assert.ok(midpoint[1] > (samples[0][2] + samples[20][2]) / 2);
});

test("cambio de carril termina en el carril nuevo sin rotación artificial", () => {
  const motion = anchored({ a: lane("A", 30, [[0, 0], [0, 30]]), b: lane("A", 30, [[3.2, 0], [3.2, 30]]) });
  const samples = verifyInterval(motion, car(0, 8, 0, "a", 8), car(3.2, 12, 0, "b", 12), .5);
  near(samples[10][1] * metersPerDegree, 1.6);
  near(samples[10][3], 0);
});

test("muestras detenidas y sin carril utilizable siguen ancladas a FCD", () => {
  const motion = anchored({});
  const first = car(0, 0, 10, "missing", 0, 5, 0);
  const last = car(0, 0, 10, "missing", 0, 5, 0);
  assert.deepEqual(motion.sample(first), motion.between(first, last, .5, .5));
  verifyInterval(motion, first, last, .5);
});
