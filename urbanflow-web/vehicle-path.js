function sampleBetween(track, column, value) {
  let low = 0;
  let high = track.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (track[middle][column] < value) low = middle + 1;
    else high = middle;
  }
  const first = track[Math.max(0, low - 1)];
  const last = track[low];
  const range = last[column] - first[column];
  const fraction = range ? Math.max(0, Math.min(1, (value - first[column]) / range)) : 0;
  return first.map((coordinate, axis) => coordinate + fraction * (last[axis] - coordinate));
}

export function terminalBusPaths(data, createMotion, coordinates) {
  const paths = new Map();
  data.vehicleIndex?.forEach(({ type }, id) => {
    if (type === "terminal-bus") paths.set(id, []);
  });
  if (!paths.size) return paths;
  const motion = createMotion(data.laneMotion);
  for (const [index, [time, cars]] of data.frames.entries()) {
    const following = data.frames[index + 1];
    motion.beginFrame(cars);
    for (const car of cars) {
      const track = paths.get(car[0]);
      if (!track) continue;
      const next = following?.[1].find(candidate => candidate[0] === car[0]);
      const seconds = next ? following[0] - time : 0;
      const samples = next ? Math.max(1, Math.ceil(Math.max(car[4], next[4]) * seconds / .55)) : 1;
      for (let step = 0; step < samples; step++) {
        const ratio = step / samples;
        const sample = step ? motion.between(car, next, ratio, seconds) : motion.sample(car);
        const [, lng, lat, heading] = sample;
        const [x, y] = coordinates.fromGeo([lng, lat]);
        const yaw = coordinates.bearing(lat, heading);
        const halfLength = data.vehicleTypes["terminal-bus"].length / 2;
        const front = [x - Math.sin(yaw) * halfLength, y + Math.cos(yaw) * halfLength];
        const previous = track.at(-1);
        const distance = previous ? previous[3] + Math.hypot(front[0] - previous[1], front[1] - previous[2]) : 0;
        track.push([time + ratio * seconds, ...front, distance]);
      }
    }
  }
  return paths;
}

export function busPose(track, time, length, axleRatios) {
  const frontOffset = axleRatios[0] * length;
  const wheelbase = (axleRatios[0] - axleRatios[1]) * length;
  const frontDistance = sampleBetween(track, 0, time)[3] - (length / 2 - frontOffset);
  if (frontDistance < wheelbase) return null;
  const [, frontX, frontY] = sampleBetween(track, 3, frontDistance);
  let near = frontDistance - wheelbase;
  let far = Math.max(0, frontDistance - wheelbase * 2);
  let [, rearX, rearY] = sampleBetween(track, 3, far);
  if (Math.hypot(frontX - rearX, frontY - rearY) < wheelbase) return null;
  for (let step = 0; step < 9; step++) {
    const middle = (far + near) / 2;
    [, rearX, rearY] = sampleBetween(track, 3, middle);
    if (Math.hypot(frontX - rearX, frontY - rearY) >= wheelbase) far = middle;
    else near = middle;
  }
  const dx = frontX - rearX;
  const dy = frontY - rearY;
  const span = Math.hypot(dx, dy);
  return [frontX - frontOffset * dx / span, frontY - frontOffset * dy / span, -Math.atan2(dx, dy)];
}
