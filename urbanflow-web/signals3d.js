import * as THREE from "three";

const lampColors = [0xff443f, 0xffca40, 0x3aff8e];
const glyphs = { l: "←", L: "←", s: "↑", r: "→", R: "→", t: "↶", T: "↷" };
const directionOrder = { t: 0, T: 0, l: 1, L: 1, s: 2, r: 3, R: 3 };

export function signalAspect(code, time) {
  return {
    lamps: [code === "r" || code === "u", code === "y" || code === "Y" || code === "u"
      || (code === "o" && Math.floor(time * 2) % 2 === 0), ["G", "g", "s"].includes(code)],
    movement: { G: "priority", g: "yield", s: "after-stop" }[code] ?? null,
  };
}

const localPoint = ([x, y], height = 0) => new THREE.Vector3(x, height, -y);

function trackEnd(points, length, fromStart = false) {
  const ordered = fromStart ? points : [...points].reverse();
  const result = [ordered[0]];
  let remaining = length;
  for (let index = 1; index < ordered.length && remaining > 0; index++) {
    const start = ordered[index - 1];
    const end = ordered[index];
    const distance = Math.hypot(end[0] - start[0], end[1] - start[1]);
    if (distance < .001) continue;
    result.push(distance <= remaining ? end : start.map((value, axis) => value + (end[axis] - value) * remaining / distance));
    remaining -= distance;
  }
  return fromStart ? result : result.reverse();
}

function connectionPath(via, destination, links) {
  if (!via) return [];
  const queue = [[via]];
  const visited = new Set([via]);
  for (const path of queue) {
    for (const next of links[path.at(-1)] ?? []) {
      if (next === destination) return path;
      if (next.startsWith(":") && !visited.has(next)) {
        visited.add(next);
        queue.push([...path, next]);
      }
    }
  }
  return null;
}

function movementGeometry(points, height) {
  const vertices = [];
  let end;
  let heading;
  const triangle = (...points) => points.forEach(([x, y]) => vertices.push(x, height, -y));
  for (let index = 1; index < points.length; index++) {
    const [a, b] = [points[index - 1], points[index]];
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (length < .02) continue;
    const dx = (b[0] - a[0]) / length;
    const dy = (b[1] - a[1]) / length;
    const left = ([x, y]) => [x - dy * .31, y + dx * .31];
    const right = ([x, y]) => [x + dy * .31, y - dx * .31];
    triangle(left(a), right(a), left(b));
    triangle(right(a), right(b), left(b));
    end = b;
    heading = [dx, dy];
  }
  if (!end) return null;
  const [x, y] = end;
  const [dx, dy] = heading;
  triangle([x - dx * 1.05 - dy * .73, y - dy * 1.05 + dx * .73],
    [x - dx * 1.05 + dy * .73, y - dy * 1.05 - dx * .73], [x + dx * .3, y + dy * .3]);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
  return geometry;
}

function poleMatrix(start, end, radius) {
  const segment = end.clone().sub(start);
  const center = start.clone().lerp(end, .5);
  const scale = new THREE.Vector3(radius, segment.length(), radius);
  const rotation = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), segment.normalize());
  return new THREE.Matrix4().compose(center, rotation, scale);
}

function signalBatch(group, geometry, material, transforms) {
  const mesh = new THREE.InstancedMesh(geometry, material, transforms.length);
  transforms.forEach((matrix, index) => mesh.setMatrixAt(index, matrix));
  group.add(mesh);
  return mesh;
}

function makeArrowMaterial(glyph) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const context = canvas.getContext("2d");
  context.fillStyle = "#19232c";
  context.fillRect(0, 0, 64, 64);
  context.fillStyle = "#ffffff";
  context.font = "bold 52px system-ui";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(glyph, 32, 30);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return new THREE.MeshBasicMaterial({ map: texture });
}

export function addSignals3D(scene, data, links, controller, coordinates, roadHeight, onRoad) {
  const timeline = data.signalReplay?.states?.[controller];
  if (!timeline?.length) return null;
  const { lanes, links: laneLinks } = data.laneMotion;
  const lanePoints = id => lanes[id]?.points.map(coordinates.fromSumo) ?? [];
  const approaches = new Map();
  for (const link of links) {
    if (link.controller !== controller || lanePoints(link.fromLane).length < 2) continue;
    const edge = lanes[link.fromLane].edge;
    if (!approaches.has(edge)) approaches.set(edge, new Map());
    const lane = approaches.get(edge);
    if (!lane.has(link.fromLane)) lane.set(link.fromLane, []);
    lane.get(link.fromLane).push(link);
  }
  if (!approaches.size) return null;

  const heads = new THREE.Group();
  heads.name = "signal-heads";
  heads.userData.posts = [];
  const overlays = new THREE.Group();
  overlays.name = "signal-movement-overlay";
  overlays.visible = false;
  scene.add(heads, overlays);
  const steel = new THREE.MeshStandardMaterial({ color: 0x506070, roughness: .8 });
  const housing = new THREE.MeshStandardMaterial({ color: 0x17232c, roughness: .82 });
  const on = lampColors.map(color => new THREE.MeshBasicMaterial({ color, toneMapped: false }));
  const off = [0x522c2e, 0x544524, 0x224937].map(color => new THREE.MeshBasicMaterial({ color }));
  const signs = new Map();
  const boxes = [];
  const poles = [];
  const poleGeometry = new THREE.CylinderGeometry(1, 1, 1, 8);
  const box = new THREE.BoxGeometry(.52, 1.12, .24);
  const lens = new THREE.CircleGeometry(.16, 16);
  const plaque = new THREE.PlaneGeometry(.47, .47);
  const movements = [];
  const paint = Object.fromEntries(Object.entries({ priority: 0x0fd879, yield: 0x38c5e0, "after-stop": 0xffc04d })
    .map(([key, color]) => [key, new THREE.MeshBasicMaterial({ color, opacity: .85, transparent: true,
      side: THREE.DoubleSide, depthWrite: false, toneMapped: false })]));
  const height = 4.75;
  const laneNumber = id => Number(id.slice(id.lastIndexOf("_") + 1));

  function postFor(point, right) {
    for (let offset = 2.25; offset <= 9; offset += .5) {
      const candidate = point.clone().addScaledVector(right, offset);
      if ([[-.2, 0], [.2, 0], [0, -.2], [0, .2], [0, 0]]
        .every(([x, y]) => !onRoad(candidate.x + x, -candidate.z + y))) return candidate;
    }
    return null;
  }

  for (const approach of approaches.values()) {
    const placements = [];
    let post;
    let plannedPost = false;
    for (const [laneId, laneMovements] of [...approach].sort(([a], [b]) => laneNumber(a) - laneNumber(b))) {
      const points = lanePoints(laneId);
      const tail = trackEnd(points, 2.2);
      if (tail.length < 2) continue;
      const end = tail.at(-1);
      const forward = localPoint(end).sub(localPoint(tail[0])).normalize();
      const right = forward.clone().cross(new THREE.Vector3(0, 1, 0));
      const laneEnd = localPoint(end, height).addScaledVector(forward, -1.35);
      const external = laneMovements.filter(link => !link.insideJunction);
      if (external.length && !plannedPost) {
        plannedPost = true;
        post = postFor(laneEnd, right);
        if (post) heads.userData.posts.push({ lane: laneId, point: [post.x, -post.z],
          osmNode: external[0].osmSignalNode ?? null, estimated: true });
      }
      if (external.length && post) placements.push({ point: laneEnd, right });
      laneMovements.sort((a, b) => (directionOrder[a.direction] ?? 2) - (directionOrder[b.direction] ?? 2) || a.index - b.index);
      for (const link of laneMovements) {
        let head;
        let bulbs = [];
        if (post && !link.insideJunction) {
          head = new THREE.Group();
          head.name = `signal-head-${link.index}`;
          head.userData = { index: link.index, controller, lane: laneId, direction: link.direction, state: null,
            osmNode: link.osmSignalNode ?? null, estimated: true };
          const slot = external.indexOf(link);
          head.position.copy(laneEnd).addScaledVector(right, (slot - (external.length - 1) / 2) * .64);
          head.rotation.y = Math.atan2(-forward.x, -forward.z);
          head.updateMatrix();
          boxes.push(head.matrix);
          const at = y => head.matrix.clone().multiply(new THREE.Matrix4().makeTranslation(0, y, .124));
          bulbs = off.map((_, index) => at(.34 - index * .34));
          const glyph = glyphs[link.direction] ?? "↑";
          if (!signs.has(glyph)) signs.set(glyph, []);
          signs.get(glyph).push(at(-.78));
          heads.add(head);
        }
        const internal = connectionPath(link.via, link.toLane, laneLinks);
        const outgoing = lanePoints(link.toLane);
        let stripe = null;
        if (internal && outgoing.length >= 2) {
          const trace = [...trackEnd(points, 1.2), ...internal.flatMap(lanePoints), ...trackEnd(outgoing, 7, true)];
          const geometry = movementGeometry(trace, roadHeight + .043);
          if (geometry) {
            stripe = new THREE.Mesh(geometry, paint.priority);
            stripe.name = `signal-movement-${link.index}`;
            stripe.visible = false;
            stripe.userData.index = link.index;
            overlays.add(stripe);
          }
        }
        movements.push({ index: link.index, head, bulbs, stripe });
      }
    }
    if (placements.length) {
      const first = placements[0];
      const top = post;
      const base = top.clone().setY(roadHeight);
      top.y = height + .46;
      const tip = placements.at(-1).point.clone().addScaledVector(first.right, -.65).setY(top.y);
      poles.push(poleMatrix(base, top, .105));
      if (top.distanceToSquared(tip) > .001) poles.push(poleMatrix(top, tip, .073));
    }
  }

  signalBatch(heads, box, housing, boxes);
  signalBatch(heads, poleGeometry, steel, poles);
  for (const [glyph, matrices] of signs) signalBatch(heads, plaque, makeArrowMaterial(glyph), matrices);
  const lenses = [...off, ...on].map(material => {
    const mesh = new THREE.InstancedMesh(lens, material, movements.length);
    mesh.count = 0;
    mesh.frustumCulled = false;
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    heads.add(mesh);
    return mesh;
  });

  let renderedPhase;
  let renderedBlink;
  return {
    materials: [...on, ...off, ...Object.values(paint)],
    setOverlay(visible) {
      overlays.visible = visible;
    },
    update(time) {
      const phase = timeline.findLast(([start]) => start <= time)?.[1] ?? "";
      const blink = phase.includes("o") ? Math.floor(time * 2) % 2 : 0;
      if (phase === renderedPhase && blink === renderedBlink) return;
      renderedPhase = phase;
      renderedBlink = blink;
      for (const mesh of lenses) mesh.count = 0;
      for (const { index: movementIndex, head, bulbs, stripe } of movements) {
        const code = phase[movementIndex];
        const { lamps, movement } = signalAspect(code, time);
        if (head) head.userData.state = code ?? null;
        for (const [index, bulb] of bulbs.entries()) {
          const mesh = lenses[index + (lamps[index] ? 3 : 0)];
          mesh.setMatrixAt(mesh.count++, bulb);
        }
        if (stripe) {
          stripe.visible = Boolean(movement);
          if (movement) stripe.material = paint[movement];
          stripe.userData.aspect = movement;
        }
      }
      for (const mesh of lenses) mesh.instanceMatrix.needsUpdate = true;
    },
  };
}
