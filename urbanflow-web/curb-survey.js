import * as THREE from "three";

const styles = {
  access: { color: 0x226be2, symbol: "↳", height: 1.7 },
  parking: { color: 0x13835f, symbol: "P", height: 1.5 },
  prohibited: { color: 0xc63f37, symbol: "×", height: .65 },
  unverified: { color: 0x727c89, symbol: "?", height: .7 },
};

function makeMarker({ color, symbol }) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 96;
  const pen = canvas.getContext("2d");
  pen.beginPath();
  pen.roundRect(5, 5, 86, 86, 18);
  pen.fillStyle = "#" + new THREE.Color(color).getHexString();
  pen.fill();
  pen.lineWidth = 5;
  pen.strokeStyle = "#ffffff";
  pen.stroke();
  pen.font = "bold 53px system-ui";
  pen.fillStyle = "#ffffff";
  pen.textAlign = "center";
  pen.textBaseline = "middle";
  pen.fillText(symbol, 48, 46);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false,
    sizeAttenuation: false, toneMapped: false });
}

function addRibbon(group, paths, color, height, dashed) {
  const vertices = [];
  for (const path of paths) {
    for (let index = 1; index < path.length; index++) {
      const [a, b] = [path[index - 1], path[index]];
      const dx = b[0] - a[0];
      const dy = b[1] - a[1];
      const length = Math.hypot(dx, dy);
      if (length < .01) continue;
      const half = dashed ? .11 : .18;
      const point = (distance, side) => [
        a[0] + (dx * distance - side * dy * half) / length,
        height,
        -(a[1] + (dy * distance + side * dx * half) / length),
      ];
      for (let start = 0; start < length; start += dashed ? 2.2 : length) {
        const end = dashed ? Math.min(length, start + 1.25) : length;
        const l0 = point(start, 1);
        const r0 = point(start, -1);
        const l1 = point(end, 1);
        const r1 = point(end, -1);
        vertices.push(...l0, ...r0, ...l1, ...r0, ...r1, ...l1);
      }
    }
  }
  if (!vertices.length) return;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
  const material = new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, toneMapped: false });
  group.add(new THREE.Mesh(geometry, material));
}

export function addCurbSurvey(scene, survey, coordinates, roadHeight) {
  const group = new THREE.Group();
  group.name = "curb-survey";
  group.visible = false;
  const materials = new Map();
  for (const { id, geometry, properties } of survey.features) {
    const { kind, location } = properties;
    const style = styles[kind];
    const paths = geometry.type === "LineString" ? [geometry.coordinates] : geometry.coordinates;
    const feature = new THREE.Group();
    feature.name = id;
    addRibbon(feature, paths.map(path => path.map(coordinates.fromGeo)), style.color, roadHeight + .023, kind === "unverified");
    if (!materials.has(kind)) materials.set(kind, makeMarker(style));
    const marker = new THREE.Sprite(materials.get(kind));
    const [x, y] = coordinates.fromGeo(location);
    marker.position.set(x, style.height, -y);
    marker.scale.set(.072, .072, 1);
    feature.add(marker);
    group.add(feature);
  }
  scene.add(group);
  return group;
}

export function curbWalk(road, coordinates) {
  const points = road.coordinates.map(coordinates.fromGeo);
  let length = 0;
  const segments = points.slice(1).map(([x, y], index) => {
    const from = points[index];
    const direction = new THREE.Vector3(x - from[0], 0, from[1] - y);
    const span = direction.length();
    const start = length;
    length += span;
    return { origin: new THREE.Vector3(from[0], 0, -from[1]), start, direction: direction.normalize() };
  });
  return {
    length,
    positionAt(distance) {
      const along = THREE.MathUtils.clamp(distance, 0, length);
      const { origin, start, direction } = segments.findLast(segment => segment.start <= along);
      const north = direction.clone().cross(new THREE.Vector3(0, 1, 0)).negate();
      const eye = origin.clone().addScaledVector(direction, along - start).addScaledVector(north, road.width / 2 + 1);
      eye.y = 1.78;
      const ahead = Math.min(9, length - along + 1.5);
      return { eye, direction, target: eye.clone().addScaledVector(direction, ahead).addScaledVector(north, -4).setY(1.25) };
    },
    distanceTo(point) {
      const [x, y] = coordinates.fromGeo(point);
      let nearest = Infinity;
      let distance = 0;
      for (const [index, { origin, start, direction }] of segments.entries()) {
        const span = (segments[index + 1]?.start ?? length) - start;
        const offset = new THREE.Vector3(x, 0, -y).sub(origin);
        const along = THREE.MathUtils.clamp(offset.dot(direction), 0, span);
        const gap = offset.addScaledVector(direction, -along).lengthSq();
        if (gap < nearest) {
          nearest = gap;
          distance = start + along;
        }
      }
      return distance;
    },
  };
}
