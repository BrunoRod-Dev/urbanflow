"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { pathToFileURL } = require("node:url");
const { createHash } = require("node:crypto");

const [original, candidate, beforeMotion, beforeChassis, camacho, honduras, out] = process.argv.slice(2);
const root = path.join(__dirname, "..");
const source = name => fs.readFileSync(path.join(root, "urbanflow-web", name), "utf8");
const load = file => {
  const bytes = fs.readFileSync(file);
  return { replay: JSON.parse(bytes), sha256: createHash("sha256").update(bytes).digest("hex") };
};
const engine = code => vm.runInNewContext(`${code}\ncreateLaneMotion`);
const oldMotion = engine(fs.readFileSync(beforeMotion, "utf8"));
const sharedMotion = engine(source("lane-motion.js"));
const app = source("app.js");
const interpolateSource = app.slice(app.indexOf("function interpolate("), app.indexOf("function updateMetrics("));
const player = vm.runInNewContext(`({ frames, laneMotion, replayViews }) => {
  ${interpolateSource}
  return interpolate;
}`);
const radians = Math.PI / 180;
const degrees = value => value / radians;
const angularError = (a, b) => Math.abs(degrees(Math.atan2(Math.sin(a - b), Math.cos(a - b))));
const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const bodyPoint = ([x, y, yaw], offset) => [x - Math.sin(yaw) * offset, y + Math.cos(yaw) * offset];
const axleRatios = [.2391, -.2189];

function fcdReference(car, coordinates) {
  const [, lon, lat, heading] = car;
  const half = (car[8] ?? 5) / 2;
  const front = coordinates.fromGeo([lon, lat]);
  const yaw = coordinates.bearing(lat, heading);
  return { front, yaw, center: bodyPoint([...front, yaw], -half) };
}

function errorStats() {
  return { center: 0, front: 0, yaw: 0, aboveHalfMeter: 0, aboveFiveDegrees: 0 };
}

function addError(stats, car, world, reference) {
  const center = distance(world, reference.center);
  const front = distance(bodyPoint(world, (car[8] ?? 5) / 2), reference.front);
  const yaw = angularError(world[2], reference.yaw);
  stats.center = Math.max(stats.center, center);
  stats.front = Math.max(stats.front, front);
  stats.yaw = Math.max(stats.yaw, yaw);
  stats.aboveHalfMeter += Number(center > .5);
  stats.aboveFiveDegrees += Number(yaw > 5);
  return { center, front, yaw };
}

async function main() {
  const { createSceneCoordinates, sceneBounds, vehicleScenePose } =
    await import(pathToFileURL(path.join(root, "urbanflow-web/scene-coordinates.js")));
  const { busPose, terminalBusPaths } = await import(pathToFileURL(path.resolve(beforeChassis)));
  function sector(file) {
    const { replay, sha256 } = load(file);
    const coordinates = createSceneCoordinates(replay.laneMotion.projection, replay.location);
    const bounds = sceneBounds(replay.bounds, coordinates);
    const laneMotion = sharedMotion(replay.laneMotion);
    const old = oldMotion(replay.laneMotion);
    const legacy = player({ frames: replay.frames, laneMotion: old });
    const flat = player({ frames: replay.frames, laneMotion, replayViews: { active: false } });
    const scene = player({ frames: replay.frames, laneMotion, replayViews: { active: true } });
    const before = errorStats(), after = errorStats();
    let samples = 0, between = 0, oldBoundsExcluded = 0, oldAdditionalReversals = 0, additionalReversals = 0;
    const named = [];
    for (const [index, [time, rows]] of replay.frames.entries()) {
      const following = replay.frames[index + 1];
      const draws = flat(index, time);
      assert.deepEqual(draws, scene(index, time));
      const previousDraw = legacy(index, time);
      for (const [row, car] of rows.entries()) {
        const expected = fcdReference(car, coordinates);
        addError(before, car, vehicleScenePose(previousDraw[row], coordinates), expected);
        const world = vehicleScenePose(draws[row], coordinates);
        addError(after, car, world, expected);
        oldBoundsExcluded += Number(bounds.some(([min, max], axis) => world[axis] < min || world[axis] > max));
        samples++;
      }
      if (!following || !rows.length) continue;
      const intervals = Array.from({ length: 19 }, (_, i) => {
        const t = time + (following[0] - time) * (i + 1) / 20;
        const poses = scene(index, t);
        assert.deepEqual(poses, flat(index, t));
        between += poses.length;
        return poses;
      });
      const next = new Map(following[1].map(car => [car[0], car]));
      rows.forEach((car, row) => {
        const last = next.get(car[0]);
        if (!last) return;
        const a = worldPoint(draws[row]), b = worldPoint(laneMotion.sample(last));
        const span = distance(a, b);
        if (span <= .35) return;
        const direction = [(b[0] - a[0]) / span, (b[1] - a[1]) / span];
        const signed = (first, final) => direction[0] * (final[0] - first[0]) + direction[1] * (final[1] - first[1]);
        const beforeEnd = signed(worldPoint(old.sample(car)), worldPoint(old.sample(last)));
        oldAdditionalReversals += Number(beforeEnd <= -.35);
        let maximum = 0;
        const min = Math.min(0, ...[...intervals.map(frame => worldPoint(frame[row])), b].map(point => {
          const displacement = signed(a, point);
          maximum = Math.max(maximum, displacement);
          return displacement - maximum;
        }));
        additionalReversals += Number(min <= -.35);
        const id = replay.vehicleIndex[car[0]].sumoId;
        if ((id === "mansa-1" && time === 110.5) || (id === "salida-servicio-1" && time === 202)) {
          const oldA = old.sample(car), oldB = old.sample(last);
          named.push({ id, time: [time, following[0]], rawFcd: [car, last],
            recordedCenterMeters: span, beforeProjectedMeters: beforeEnd, afterProjectedMeters: signed(a, b),
            oldTurn: angularError(oldA[3] * radians, oldB[3] * radians),
            newTurn: angularError(car[3] * radians, last[3] * radians),
            poses: [draws[row], ...intervals.map(frame => frame[row]), laneMotion.sample(last)] });
        }
      });
    }
    function worldPoint(car) { return coordinates.fromGeo([car[1], car[2]]); }
    assert.ok(after.center <= .1 && after.front <= .1 && after.yaw <= 1);
    assert.equal(additionalReversals, 0);
    return { sha256, samples, between, oldBoundsExcluded, before, after, oldAdditionalReversals, additionalReversals, named };
  }

  function bus(file) {
    const { replay, sha256 } = load(file);
    const coordinates = createSceneCoordinates(replay.laneMotion.projection, replay.sceneOrigin ?? replay.location);
    const laneMotion = sharedMotion(replay.laneMotion);
    const legacyTracks = terminalBusPaths(replay, oldMotion, coordinates);
    const sharedTracks = terminalBusPaths(replay, sharedMotion, coordinates);
    const legacy = oldMotion(replay.laneMotion);
    const before = errorStats(), sharedWithChassis = errorStats(), after = errorStats();
    const length = replay.vehicleTypes["terminal-bus"].length;
    let samples = 0, solved = 0, maxAxleSpacingError = 0, worst;
    for (const [time, cars] of replay.frames) {
      for (const raw of cars) {
        const oldTrack = legacyTracks.get(raw[0]);
        if (!oldTrack) continue;
        samples++;
        assert.equal(raw[8], length);
        const expected = fcdReference(raw, coordinates);
        const oldWorld = busPose(oldTrack, time, length, axleRatios) ?? vehicleScenePose(legacy.sample(raw), coordinates);
        const sharedCandidate = busPose(sharedTracks.get(raw[0]), time, length, axleRatios);
        const world = vehicleScenePose(laneMotion.sample(raw), coordinates);
        solved += Number(Boolean(sharedCandidate));
        const oldError = addError(before, raw, oldWorld, expected);
        addError(sharedWithChassis, raw, sharedCandidate ?? world, expected);
        const newError = addError(after, raw, world, expected);
        const axles = axleRatios.map(ratio => bodyPoint(world, ratio * length));
        const nominal = (axleRatios[0] - axleRatios[1]) * length;
        maxAxleSpacingError = Math.max(maxAxleSpacingError, Math.abs(distance(...axles) - nominal));
        if (!worst || oldError.front > worst.oldError.front) {
          worst = { time, raw, world, axles, oldWorld, oldError, newError };
        }
      }
    }
    assert.ok(samples > 0 && solved > 0);
    assert.ok(sharedWithChassis.center > .1 || sharedWithChassis.yaw > 1);
    assert.ok(after.center <= .1 && after.front <= .1 && after.yaw <= 1 && maxAxleSpacingError < 1e-9);
    return { sha256, samples, solved, length, axleSpacing: (axleRatios[0] - axleRatios[1]) * length,
      maxAxleSpacingError, before, sharedWithChassis, after, worst };
  }

  fs.writeFileSync(out, JSON.stringify({ original: sector(original), candidate: sector(candidate),
    busCamacho: bus(camacho), busHonduras: bus(honduras) }, null, 2), { flag: "wx" });
}

main().catch(error => { console.error(error); process.exitCode = 1; });
