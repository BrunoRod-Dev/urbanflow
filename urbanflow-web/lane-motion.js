"use strict";

function createLaneMotion({ lanes, links, projection }) {
  const shapes = new Map();
  const transitions = new Map();
  let frame;
  const radians = Math.PI / 180;
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const mix = (a, b, fraction) => a + (b - a) * fraction;

  function shape(id) {
    if (shapes.has(id)) return shapes.get(id);
    const lane = lanes[id];
    if (!lane || lane.points.length < 2 || lane.length <= 0) return null;
    const distances = [0];
    for (let i = 1; i < lane.points.length; i++) {
      const [x, y] = lane.points[i];
      const [px, py] = lane.points[i - 1];
      distances.push(distances[i - 1] + Math.hypot(x - px, y - py));
    }
    const measured = distances.at(-1);
    if (!measured) return null;
    const result = { ...lane, distances, measured };
    shapes.set(id, result);
    return result;
  }

  function pointOn(lane, position) {
    const meters = clamp(position / lane.length, 0, 1) * lane.measured;
    const last = lane.distances.findIndex(distance => distance > meters);
    if (last < 0) return lane.points.at(-1);
    const progress = (meters - lane.distances[last - 1]) / (lane.distances[last] - lane.distances[last - 1]);
    const first = lane.points[last - 1];
    return first.map((coordinate, axis) => mix(coordinate, lane.points[last][axis], progress));
  }

  const utm = projection?.type === "utm" ? createSumoProjection(projection) : null;

  function toGeo([x, y]) {
    if (utm) return utm.toGeo(x, y);
    const [ox, oy] = projection.origin;
    return projection.location.map((coordinate, axis) =>
      coordinate + (x - ox) * projection.east[axis] + (y - oy) * projection.north[axis]);
  }

  function centered(car, front, angle) {
    const [lng, lat] = front;
    const halfLength = (car[8] ?? 5) / 2;
    const east = halfLength * Math.sin(angle * radians);
    const north = halfLength * Math.cos(angle * radians);
    return [car[0], lng - east / (111320 * Math.cos(lat * radians)), lat - north / 111320,
      (angle + 360) % 360, car[4], car[5]];
  }

  function recordedCenter(car) {
    return centered(car, [car[1], car[2]], car[3]);
  }

  function connectedPath(first, last, limit) {
    const queue = [{ path: [first], length: 0 }];
    const visited = new Set();
    while (queue.length && visited.size < 100) {
      queue.sort((a, b) => b.length - a.length);
      const { path, length } = queue.pop();
      const lane = path.at(-1);
      if (visited.has(lane)) continue;
      if (lane === last) return path;
      visited.add(lane);
      for (const next of links[lane] ?? []) {
        const geometry = shape(next);
        if (!geometry || visited.has(next)) continue;
        const distance = length + (next === last ? 0 : geometry.length);
        if (distance <= limit) queue.push({ path: [...path, next], length: distance });
      }
    }
    return null;
  }

  function pathFor(car, next, seconds) {
    const start = shape(car[6]);
    const end = shape(next[6]);
    if (!start || !end || !Number.isFinite(car[7]) || !Number.isFinite(next[7])) return null;
    const from = clamp(car[7], 0, start.length);
    const to = clamp(next[7], 0, end.length);
    if (car[6] === next[6]) {
      if (to < from) return null;
      return { length: to - from, pointAt: distance => pointOn(start, from + distance) };
    }
    if (start.edge === end.edge) {
      const length = Math.max(1, Math.abs(to - from), 3.2);
      return { length, pointAt(distance) {
        const progress = clamp(distance / length, 0, 1);
        const fraction = mix(from / start.length, to / end.length, progress);
        const a = pointOn(start, fraction * start.length);
        const b = pointOn(end, fraction * end.length);
        const sideways = progress * progress * (3 - 2 * progress);
        return a.map((coordinate, axis) => mix(coordinate, b[axis], sideways));
      } };
    }
    const maxDistance = Math.max(car[4], next[4]) * seconds + 8;
    const path = connectedPath(car[6], next[6], maxDistance - (start.length - from) - to);
    if (!path) return null;
    let length = 0;
    const parts = path.map((id, index) => {
      const lane = shape(id);
      const startAt = index === 0 ? from : 0;
      const offset = length;
      length += (index === path.length - 1 ? to : lane.length) - startAt;
      return { lane, startAt, offset };
    });
    if (length > maxDistance) return null;
    return { length, pointAt(distance) {
      const position = clamp(distance, 0, length);
      const part = parts.findLast(piece => piece.offset <= position);
      return pointOn(part.lane, part.startAt + position - part.offset);
    } };
  }

  function anchoredPath(car, next, seconds) {
    const first = recordedCenter(car);
    const last = recordedCenter(next);
    const turn = ((last[3] - first[3] + 540) % 360) - 180;
    const path = pathFor(car, next, seconds);
    const longitudeScale = Math.cos((first[2] + last[2]) / 2 * radians);
    const east = (last[1] - first[1]) * longitudeScale;
    const north = last[2] - first[2];
    const chord = Math.hypot(east, north);
    let lateral = [0, 0];
    if (path && path.length >= .01 && chord > 0 && longitudeScale > 0) {
      const start = toGeo(path.pointAt(0));
      const middle = toGeo(path.pointAt(path.length / 2));
      const end = toGeo(path.pointAt(path.length));
      const normal = [-north / chord, east / chord];
      const bow = normal[0] * (middle[0] - (start[0] + end[0]) / 2) * longitudeScale
        + normal[1] * (middle[1] - (start[1] + end[1]) / 2);
      // Use the lane's curvature sideways, with forward progress set by the FCD endpoints.
      const offset = clamp(bow, -chord / 4, chord / 4);
      lateral = [normal[0] * offset / longitudeScale, normal[1] * offset];
    }
    return fraction => {
      if (fraction <= 0) return first;
      if (fraction >= 1) return last;
      const weight = 4 * fraction * (1 - fraction);
      return [car[0], mix(first[1], last[1], fraction) + weight * lateral[0],
        mix(first[2], last[2], fraction) + weight * lateral[1],
        (first[3] + turn * fraction + 360) % 360, car[4], car[5]];
    };
  }

  function between(car, next, fraction, seconds) {
    if (!transitions.has(car)) transitions.set(car, anchoredPath(car, next, seconds));
    return transitions.get(car)(fraction);
  }

  return { sample: recordedCenter, between, beginFrame(cars) {
    if (frame !== cars) {
      transitions.clear();
      frame = cars;
    }
  } };
}
