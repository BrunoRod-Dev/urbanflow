import * as THREE from "three";
import { buildStreetLayout, streetDimensions } from "./street-layout.js";

export const roadHeight = .025;

function geometryFrom(vertices) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
  const uv = [];
  for (let index = 0; index < vertices.length; index += 3) uv.push(vertices[index] / 5, vertices[index + 2] / 5);
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geometry.computeVertexNormals();
  return geometry;
}

function polygonSurface(polygons, height) {
  const vertices = [];
  for (const { outer, holes } of polygons) {
    const contours = [outer, ...holes].map(ring => ring.map(([x, y]) => new THREE.Vector2(x, y)));
    const faces = THREE.ShapeUtils.triangulateShape(contours[0], contours.slice(1));
    const points = contours.flat();
    for (const face of faces) {
      for (const index of face) vertices.push(points[index].x, height, -points[index].y);
    }
  }
  return vertices;
}

function polygonWalls(rings, bottom, top, include = () => true) {
  const vertices = [];
  for (const ring of rings) {
    for (const [index, a] of ring.entries()) {
      const b = ring[(index + 1) % ring.length];
      if (!include(a, b)) continue;
      const [ax, ay] = a;
      const [bx, by] = b;
      vertices.push(ax, bottom, -ay, bx, bottom, -by, ax, top, -ay,
        bx, bottom, -by, bx, top, -by, ax, top, -ay);
    }
  }
  return vertices;
}

function addMesh(scene, name, vertices, material) {
  if (!vertices.length) return;
  const mesh = new THREE.Mesh(geometryFrom(vertices), material);
  mesh.name = name;
  scene.add(mesh);
}

function surfaceTexture(base, spread, joints = false) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const context = canvas.getContext("2d");
  const image = context.createImageData(canvas.width, canvas.height);
  let seed = 31013;
  for (let index = 0; index < image.data.length; index += 4) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    const shade = base + (seed >>> 26) % spread;
    image.data[index] = image.data[index + 1] = image.data[index + 2] = shade;
    image.data[index + 3] = 255;
  }
  context.putImageData(image, 0, 0);
  if (joints) {
    context.strokeStyle = "#a6a49d";
    context.lineWidth = .8;
    context.beginPath();
    for (let line = 0; line < 128; line += 32) {
      context.moveTo(line + .5, 0);
      context.lineTo(line + .5, 128);
      context.moveTo(0, line + .5);
      context.lineTo(128, line + .5);
    }
    context.stroke();
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
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

export function addStreetMeshes(scene, data, street, buildings, coordinates, bounds, survey) {
  const layout = buildStreetLayout(data.laneMotion.lanes, street, buildings, coordinates, bounds, survey);
  const material = (color, options = {}) => new THREE.MeshStandardMaterial({
    color, roughness: .97, side: THREE.DoubleSide, ...options,
  });
  const [[west, east], [south, north]] = bounds;
  const terrainWidth = east - west + 320;
  const terrainDepth = north - south + 320;
  const grass = surfaceTexture(223, 25);
  grass.repeat.set(terrainWidth / 16, terrainDepth / 16);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(terrainWidth, terrainDepth), material(0x8d9e73, { map: grass }));
  ground.name = "street-ground";
  ground.rotation.x = -Math.PI / 2;
  ground.position.set((west + east) / 2, 0, -(south + north) / 2);
  scene.add(ground);

  const curbTop = streetDimensions.curb;
  addMesh(scene, "street-asphalt", polygonSurface(layout.roads, roadHeight), material(0x4b5059, { map: surfaceTexture(208, 44) }));
  addMesh(scene, "street-islands", polygonSurface(layout.islands, curbTop - .015), material(0x80975f));
  addMesh(scene, "street-sidewalks", polygonSurface(layout.sidewalks, curbTop),
    material(0xc9c4b5, { map: surfaceTexture(237, 16, true) }));
  const boundaries = layout.roads.flatMap(({ outer, holes }) => [outer, ...holes]);
  const insideScene = (a, b) => !bounds.some(([min, max], axis) => [min, max].some(edge =>
    Math.abs(a[axis] - edge) < .015 && Math.abs(b[axis] - edge) < .015));
  const curbWalls = polygonWalls(boundaries, roadHeight, curbTop, insideScene);
  const curbCaps = polygonSurface(layout.curbs, curbTop + .006);
  addMesh(scene, "street-curbs", [...curbWalls, ...curbCaps], material(0xb0a99a));
  addMesh(scene, "street-markings", polygonSurface(layout.markings, roadHeight + .015), material(0xf6f3e7));

  const walls = [];
  const bases = [];
  const roofs = [];
  for (const building of layout.structures) {
    const rings = [building.outer, ...building.holes];
    bases.push(...polygonWalls(rings, 0, .42));
    walls.push(...polygonWalls(rings, .42, building.height));
    roofs.push(...polygonSurface([building], building.height));
  }
  addMesh(scene, "street-building-bases", bases, material(0x8b887c));
  addMesh(scene, "street-building-walls", walls, material(0xd5c8b7));
  addMesh(scene, "street-building-roofs", roofs, material(0xadada8, { map: surfaceTexture(218, 32) }));
  return (x, y) => layout.sidewalks.some(({ outer, holes }) => insideRing(x, y, outer)
    && !holes.some(hole => insideRing(x, y, hole))) ? curbTop : roadHeight;
}
