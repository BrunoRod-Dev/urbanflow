"use strict";

// Compare FCD and the existing 2D interpolation at the same recorded crossings.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { createHash } = require("node:crypto");

const [replayPath, eventsPath, outputPath, baselinePath] = process.argv.slice(2);
const replayBytes = fs.readFileSync(replayPath);
const replay = JSON.parse(replayBytes);
const audit = JSON.parse(fs.readFileSync(eventsPath, "utf8"));
const engine = fs.readFileSync(baselinePath ?? path.join(__dirname, "../urbanflow-web/lane-motion.js"), "utf8");
const createLaneMotion = vm.runInNewContext(`${engine}\ncreateLaneMotion`);
const motion = createLaneMotion(replay.laneMotion, baselinePath ? undefined : { fcdAnchored: true });
const frames = new Map(replay.frames);
const vehicleIds = new Map(replay.vehicleIndex.map((vehicle, id) => [vehicle.sumoId, id]));
const events = [];

function delta(first, last, heading) {
  const east = (last[1] - first[1]) * 111320 * Math.cos((first[2] + last[2]) * Math.PI / 360);
  const north = (last[2] - first[2]) * 111320;
  return Math.round((east * heading[0] + north * heading[1]) * 1000) / 1000;
}

function minimumForward(samples, heading) {
  // Compare each point with the furthest-forward point already reached in this interval.
  return Math.min(0, ...samples.flatMap((point, i) => samples.slice(0, i).map(before => delta(before, point, heading))));
}

function recordedCenter(car) {
  const angle = car[3] * Math.PI / 180;
  const half = (car[8] ?? 5) / 2;
  return [car[0], car[1] - half * Math.sin(angle) / (111320 * Math.cos(car[2] * Math.PI / 180)),
    car[2] - half * Math.cos(angle) / 111320];
}

function angleDifference(a, b) {
  return Math.abs(((b - a + 540) % 360) - 180);
}

function centerError(a, b) {
  return Math.hypot(delta(a, b, [1, 0]), delta(a, b, [0, 1]));
}

const connections = audit.geometryInvestigation.map(item => {
  const windows = [];
  if (!item.heading) return { geometryEventId: item.eventId, via: item.via, windows };
  for (const { vehicleId, samples } of item.windows) {
    const vehicle = vehicleIds.get(vehicleId);
    for (let i = 1; i < samples.length; i++) {
      const [before, after] = [samples[i - 1], samples[i]];
      if (before.lane !== item.via && after.lane !== item.via) continue;
      const frame = frames.get(before.time);
      const first = frame.find(car => car[0] === vehicle);
      const last = frames.get(after.time).find(car => car[0] === vehicle);
      const matches = (car, sample) => car && sample.coordinates
        && car[1] === sample.coordinates[0] && car[2] === sample.coordinates[1]
        && car[3] === sample.angleDegrees && car[4] === sample.speedMetersPerSecond
        && car[6] === sample.lane && car[7] === sample.positionMeters;
      if (!matches(first, before) || !matches(last, after)) {
        throw new Error(`FCD y replay no coinciden para ${vehicleId} en ${before.time}`);
      }
      motion.beginFrame(frame);
      const drawn = [motion.sample(first)];
      const seconds = after.time - before.time;
      for (let part = 1; part < 20; part++) drawn.push(motion.between(first, last, part / 20, seconds));
      drawn.push(motion.sample(last));
      const detail = { vehicleId, time: [before.time, after.time], lanes: [before.lane, after.lane],
        rawFrontDisplacementMeters: delta(first, last, item.heading),
        rawCenterDisplacementMeters: delta(recordedCenter(first), recordedCenter(last), item.heading),
        renderedCenterDisplacementMeters: delta(drawn[0], drawn.at(-1), item.heading),
        renderedMaxReverseMeters: -minimumForward(drawn, item.heading),
        endpointCorrectionMeters: [delta(recordedCenter(first), drawn[0], item.heading),
          delta(recordedCenter(last), drawn.at(-1), item.heading)],
        endpointCenterErrorMeters: [centerError(recordedCenter(first), drawn[0]),
          centerError(recordedCenter(last), drawn.at(-1))],
        endpointHeadingErrorDegrees: [angleDifference(first[3], drawn[0][3]),
          angleDifference(last[3], drawn.at(-1)[3])],
        maxHeadingStepDegrees: Math.max(...drawn.slice(1).map((point, j) => angleDifference(drawn[j][3], point[3]))),
        maxCenterStepMeters: Math.max(...drawn.slice(1).map((point, j) => centerError(drawn[j], point))),
        sampledRender: drawn.map(([id, x, y, angle], i) => [i / 20, x, y, angle]),
      };
      windows.push(detail);
      if (detail.rawCenterDisplacementMeters > .35 && detail.renderedCenterDisplacementMeters <= -.35) {
        events.push({ id: `render-${String(events.length + 1).padStart(4, "0")}`,
          kind: "replay_position_reverse", severity: "warning", validation: "replay_algorithm",
          label: "Retroceso adicional en el cálculo del reproductor 2D", vehicleId, time: after.time,
          coordinates: after.coordinates, edge: replay.laneMotion.lanes[after.lane].edge,
          lane: after.lane, node: item.junction,
          evidence: { source: "qa-replay-geometry.json", geometryEventId: item.eventId,
            signedMeters: detail.renderedCenterDisplacementMeters, rawCenterMeters: detail.rawCenterDisplacementMeters,
            rawFrontMeters: detail.rawFrontDisplacementMeters, interval: detail.time } });
      }
    }
  }
  return { geometryEventId: item.eventId, via: item.via, windows };
});
fs.writeFileSync(outputPath, JSON.stringify({ schemaVersion: 1, studyId: audit.studyId,
  playerMode: baselinePath ? "baseline" : "fcd-anchored-2d",
  playerSha256: createHash("sha256").update(engine).digest("hex"),
  trajectoriesSha256: audit.sourceHashes["trajectories.xml"],
  replaySha256: createHash("sha256").update(replayBytes).digest("hex"),
  method: "createLaneMotion en Node, 20 subdivisiones por intervalo de FCD; sin render del navegador",
  connections, events }, null, 2), { flag: "wx" });
