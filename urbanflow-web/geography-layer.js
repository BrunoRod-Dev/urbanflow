import * as THREE from "three";
import Clipper from "clipper-lib";
import { buildingHeight } from "./geography-heights.js?v=2";

const SCALE = 1000;
const { ClipType, EndType, JoinType, PolyFillType, PolyType } = Clipper;

const integerPoint = ([x, y]) => ({ X: Math.round(x * SCALE), Y: Math.round(y * SCALE) });
const meters = ({ X, Y }) => [X / SCALE, Y / SCALE];

function orient(points) {
  const path = Clipper.Clipper.CleanPolygon(points.map(integerPoint), 8);
  if (path.length < 3) return [];
  return Clipper.Clipper.Orientation(path) ? path : path.reverse();
}

function bufferOpen(line, width) {
  const operation = new Clipper.ClipperOffset(2, 45);
  const result = [];
  operation.AddPaths([line.map(integerPoint)], JoinType.jtRound, EndType.etOpenRound);
  operation.Execute(result, width * SCALE);
  return result;
}

function overlay(kind, subjects, clips = []) {
  if (!subjects.length) return [];
  const operation = new Clipper.Clipper();
  operation.AddPaths(subjects, PolyType.ptSubject, true);
  if (clips.length) operation.AddPaths(clips, PolyType.ptClip, true);
  const result = new Clipper.PolyTree();
  operation.Execute(kind, result, PolyFillType.pftNonZero, PolyFillType.pftNonZero);
  return Clipper.JS.PolyTreeToExPolygons(result).map(({ outer, holes }) => ({
    outer: outer.map(meters), holes: holes.map(path => path.map(meters)),
  }));
}

function geometryFrom(vertices) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
  const uv = [];
  for (let index = 0; index < vertices.length; index += 3) uv.push(vertices[index] / 4, vertices[index + 2] / 4);
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geometry.computeVertexNormals();
  return geometry;
}

function polygonSurface(polygons, height) {
  const vertices = [];
  for (const { outer, holes } of polygons) {
    if (outer.length < 3) continue;
    const contours = [outer, ...holes].map(ring => ring.map(([x, y]) => new THREE.Vector2(x, y)));
    let faces = [];
    try {
      faces = THREE.ShapeUtils.triangulateShape(contours[0], contours.slice(1));
    } catch {
      continue;
    }
    const points = contours.flat();
    for (const face of faces) {
      for (const index of face) vertices.push(points[index].x, height, -points[index].y);
    }
  }
  return vertices;
}

function polygonWalls(rings, bottom, top) {
  const vertices = [];
  for (const ring of rings) {
    for (const [index, [ax, ay]] of ring.entries()) {
      const [bx, by] = ring[(index + 1) % ring.length];
      vertices.push(ax, bottom, -ay, bx, bottom, -by, ax, top, -ay,
        bx, bottom, -by, bx, top, -by, ax, top, -ay);
    }
  }
  return vertices;
}

function outlineRibbon(ring, width, height) {
  const vertices = [];
  const count = ring.length;
  if (count < 3) return vertices;
  const inset = [];
  for (let index = 0; index < count; index += 1) {
    const previous = ring[(index + count - 1) % count];
    const current = ring[index];
    const next = ring[(index + 1) % count];
    let ax = current[0] - previous[0];
    let ay = current[1] - previous[1];
    let bx = next[0] - current[0];
    let by = next[1] - current[1];
    const aLength = Math.hypot(ax, ay) || 1;
    const bLength = Math.hypot(bx, by) || 1;
    ax /= aLength;
    ay /= aLength;
    bx /= bLength;
    by /= bLength;
    const leftX = -ay + -by;
    const leftY = ax + bx;
    const length = Math.hypot(leftX, leftY) || 1;
    const along = (-ay * leftX + ax * leftY) / length;
    const scale = Math.min(1.8, 1 / Math.max(0.35, along));
    inset.push([current[0] + leftX / length * width * scale, current[1] + leftY / length * width * scale]);
  }
  for (let index = 0; index < count; index += 1) {
    const next = (index + 1) % count;
    const [ax, ay] = ring[index];
    const [bx, by] = ring[next];
    const [cx, cy] = inset[index];
    const [dx, dy] = inset[next];
    vertices.push(ax, height, -ay, bx, height, -by, cx, height, -cy,
      bx, height, -by, dx, height, -dy, cx, height, -cy);
  }
  return vertices;
}

function shrubRadius(x, y, height, rule) {
  const span = (height - rule.minHeightMeters) / (rule.maxHeightMeters - rule.minHeightMeters);
  const mix = ((Math.imul(Math.round(x * 100), 1664525) ^ Math.imul(Math.round(y * 100), 1013904223)) >>> 0) / 4294967296;
  return 0.42 + (0.65 * span + 0.35 * mix) * 0.38;
}

function addMesh(group, name, vertices, material) {
  if (!vertices.length) return null;
  const mesh = new THREE.Mesh(geometryFrom(vertices), material);
  mesh.name = name;
  group.add(mesh);
  return mesh;
}

function insideRing(x, y, ring) {
  let inside = false;
  for (let index = 0, previous = ring.length - 1; index < ring.length; previous = index++) {
    const [ax, ay] = ring[previous];
    const [bx, by] = ring[index];
    if ((ay > y) !== (by > y) && x < ax + (bx - ax) * (y - ay) / (by - ay)) inside = !inside;
  }
  return inside;
}

function insidePolygon(x, y, polygon) {
  return insideRing(x, y, polygon.outer) && !polygon.holes.some(hole => insideRing(x, y, hole));
}

function hatchTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const context = canvas.getContext("2d");
  context.fillStyle = "#9aa3b2";
  context.fillRect(0, 0, 64, 64);
  context.strokeStyle = "#5d6778";
  context.lineWidth = 3;
  context.beginPath();
  for (let line = -64; line < 128; line += 10) {
    context.moveTo(line, 0);
    context.lineTo(line + 64, 64);
  }
  context.stroke();
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function toScenePolygons(features, coordinates) {
  return features.map(feature => {
    const ring = feature.geometry.coordinates[0].slice(0, -1).map(point => coordinates.fromGeo(point));
    const outer = orient(ring);
    return { outer: outer.map(meters), holes: [], feature };
  }).filter(polygon => polygon.outer.length >= 3);
}

function carriageway(lanes, street, coordinates, geographicBounds) {
  const hole = pilotGroundHole(geographicBounds, coordinates);
  const xs = hole.map(([x]) => x);
  const ys = hole.map(([, y]) => y);
  const minX = Math.min(...xs) - 40;
  const maxX = Math.max(...xs) + 40;
  const minY = Math.min(...ys) - 40;
  const maxY = Math.max(...ys) + 40;
  const paths = [];
  for (const [id, lane] of Object.entries(lanes)) {
    if (lane.edge.startsWith(":") || street.pedestrianLanes?.[id]) continue;
    const line = lane.points.map(point => coordinates.fromSumo(point));
    if (line.length < 2 || !line.some(([x, y]) => x >= minX && x <= maxX && y >= minY && y <= maxY)) continue;
    const half = (street.widths?.[id] ?? 3.2) / 2 + .35;
    paths.push(...bufferOpen(line, half));
  }
  return paths;
}

function shrubPlacements(polygons, rule, blocked) {
  const spacing = rule.spacingMeters;
  let state = rule.seed >>> 0;
  const random = () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
  const points = [];
  for (const polygon of polygons) {
    const xs = polygon.outer.map(([x]) => x);
    const ys = polygon.outer.map(([, y]) => y);
    for (let x = Math.min(...xs); x <= Math.max(...xs); x += spacing) {
      for (let y = Math.min(...ys); y <= Math.max(...ys); y += spacing) {
        const px = x + (random() - .5) * spacing * rule.jitter;
        const py = y + (random() - .5) * spacing * rule.jitter;
        const height = rule.minHeightMeters + random() * (rule.maxHeightMeters - rule.minHeightMeters);
        if (!insidePolygon(px, py, polygon) || blocked(px, py)) continue;
        points.push([px, py, height]);
      }
    }
  }
  return points;
}

export function pilotGroundHole(bounds, coordinates) {
  const [west, south, east, north] = bounds;
  return [[west, south], [east, south], [east, north], [west, north]].map(point => coordinates.fromGeo(point));
}

export function addGeography(scene, geography, coordinates, lanes, street, onRoad) {
  const group = new THREE.Group();
  group.name = "geography";
  const features = geography.features ?? [];
  const ofClass = name => features.filter(feature => feature.properties.class === name && feature.geometry.type === "Polygon");
  const plain = color => new THREE.MeshStandardMaterial({ color, roughness: .96 });
  const earthRing = orient(pilotGroundHole(geography.meta.bounds, coordinates)).map(meters);
  const earthPolygon = [{ outer: earthRing, holes: [] }];
  const water = toScenePolygons(ofClass("water"), coordinates);
  const sand = toScenePolygons(ofClass("sand"), coordinates);
  const asPaths = polygons => polygons.flatMap(item => {
    const outer = orient(item.outer);
    return outer.length ? [outer] : [];
  });
  const coverPaths = [...asPaths(water), ...asPaths(sand)];
  const subtract = polygons => overlay(ClipType.ctDifference, asPaths(polygons), coverPaths);
  const grass = subtract(toScenePolygons(ofClass("grass"), coordinates));
  const scrub = subtract(toScenePolygons(ofClass("scrub"), coordinates));
  const roads = carriageway(lanes, street, coordinates, geography.meta.bounds);

  addMesh(group, "geography-earth", polygonSurface(earthPolygon, .004), plain(0xb7a48a));
  addMesh(group, "geography-water", polygonSurface(water, .008), plain(0x3c86b0));
  addMesh(group, "geography-sand", polygonSurface(sand, .012), plain(0xe4d2a4));
  addMesh(group, "geography-grass", polygonSurface(grass, .016), plain(0x7d9a58));
  addMesh(group, "geography-scrub", polygonSurface(scrub, .02), plain(0x5f7544));

  const coast = features.find(feature => feature.properties.class === "coastline");
  if (coast) {
    const points = coast.geometry.coordinates.map(point => {
      const [x, y] = coordinates.fromGeo(point);
      return new THREE.Vector3(x, .03, -y);
    });
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: 0xf3efe4 }));
    line.name = "geography-coastline";
    group.add(line);
  }

  const rule = geography.meta.vegetationRule;
  const shrubs = shrubPlacements(scrub, rule, (x, y) => onRoad(x, y));
  if (shrubs.length) {
    const baseCone = new THREE.ConeGeometry(1, 1, 7);
    const crownCone = new THREE.ConeGeometry(1, 1, 7);
    baseCone.translate(0, .5, 0);
    crownCone.translate(0, .5, 0);
    const baseMesh = new THREE.InstancedMesh(baseCone, plain(0x2a6136), shrubs.length);
    const crownMesh = new THREE.InstancedMesh(crownCone, plain(0x3e7c48), shrubs.length);
    baseMesh.name = "geography-shrubs";
    crownMesh.name = "geography-shrubs-crown";
    const matrix = new THREE.Matrix4();
    const position = new THREE.Vector3();
    const quaternion = new THREE.Quaternion();
    const scale = new THREE.Vector3();
    shrubs.forEach(([x, y, height], index) => {
      const radius = shrubRadius(x, y, height, rule);
      matrix.compose(position.set(x, .02, -y), quaternion, scale.set(radius * 1.15, height * .68, radius * 1.15));
      baseMesh.setMatrixAt(index, matrix);
      matrix.compose(position.set(x, .02 + height * .4, -y), quaternion, scale.set(radius * .62, height * .55, radius * .62));
      crownMesh.setMatrixAt(index, matrix);
    });
    group.add(baseMesh, crownMesh);
  }

  const estimatedMaterial = plain(0xd5c4b0);
  const estimatedRoof = plain(0xb0aaa4);
  const hatch = hatchTexture();
  const provisionalGround = new THREE.MeshStandardMaterial({
    map: hatch, roughness: .9, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
  });
  const provisionalEdge = plain(0x2c3442);
  const heights = { measured: 0, estimated: 0, provisional: 0 };
  const walls = [];
  const roofs = [];
  const footprints = [];
  const outlines = [];
  const seenBuildings = new Set();
  for (const polygon of toScenePolygons(ofClass("building"), coordinates)) {
    const osmId = String(polygon.feature.properties.osmId ?? polygon.feature.id ?? "");
    if (seenBuildings.has(osmId)) continue;
    seenBuildings.add(osmId);
    const visual = buildingHeight(polygon.feature.properties, geography.meta.heightRule);
    if (visual.meters == null) {
      heights.provisional += 1;
      footprints.push(...polygonSurface([polygon], .022));
      outlines.push(...outlineRibbon(polygon.outer, .8, .18));
      continue;
    }
    const clipped = overlay(ClipType.ctDifference, [orient(polygon.outer)], roads)
      .filter(item => item.outer.length >= 3);
    if (!clipped.length) continue;
    heights[visual.source] += 1;
    for (const building of clipped) {
      const rings = [building.outer, ...building.holes];
      walls.push(...polygonWalls(rings, .05, visual.meters));
      roofs.push(...polygonSurface([building], visual.meters));
    }
  }
  addMesh(group, "geography-buildings-estimated", walls, estimatedMaterial);
  addMesh(group, "geography-roofs-estimated", roofs, estimatedRoof);
  addMesh(group, "geography-footprints-provisional", footprints, provisionalGround);
  addMesh(group, "geography-outlines-provisional", outlines, provisionalEdge);
  scene.add(group);
  return {
    bounds: geography.meta.bounds,
    shrubs: shrubs.length,
    surfaces: { water: water.length, sand: sand.length, grass: grass.length, scrub: scrub.length },
    buildings: heights,
  };
}
