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

  function toGeo([x, y]) {
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

  function place(car, point, before, after) {
    const front = toGeo(point);
    const [lng0, lat0] = toGeo(before);
    const [lng1, lat1] = toGeo(after);
    const east = (lng1 - lng0) * Math.cos(front[1] * radians);
    const north = lat1 - lat0;
    const angle = Math.hypot(east, north) > 1e-8 ? Math.atan2(east, north) / radians : car[3];
    return centered(car, front, angle);
  }

  function sample(car) {
    const lane = shape(car[6]);
    if (!lane || !Number.isFinite(car[7]) || car[4] < .1) return centered(car, [car[1], car[2]], car[3]);
    const position = car[7];
    return place(car, pointOn(lane, position), pointOn(lane, position - .65), pointOn(lane, position + .65));
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

  function between(car, next, fraction, seconds) {
    if (car[4] < .1 && next[4] < .1 && car[6] === next[6] && Math.abs(car[7] - next[7]) < .1) {
      return sample(car);
    }
    if (!transitions.has(car)) transitions.set(car, pathFor(car, next, seconds));
    const path = transitions.get(car);
    if (!path || path.length < .01) {
      const turn = ((next[3] - car[3] + 540) % 360) - 180;
      return centered(car, [mix(car[1], next[1], fraction), mix(car[2], next[2], fraction)], car[3] + turn * fraction);
    }
    const distance = path.length * fraction;
    return place(car, path.pointAt(distance), path.pointAt(Math.max(0, distance - .65)),
      path.pointAt(Math.min(path.length, distance + .65)));
  }

  return { sample, between, beginFrame(cars) {
    if (frame !== cars) {
      transitions.clear();
      frame = cars;
    }
  } };
}
