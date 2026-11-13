import * as THREE from "three";
import { addContactShadows } from "./contact-shadows.js";

const { clamp, lerp } = THREE.MathUtils;
const stillSpeed = .05;
const shirtColors = [0x2d7eaf, 0xa06c35, 0x587955, 0xc25f35];

function makeWalker(identifier, shirt, geometry, materials) {
  const root = new THREE.Group();
  const body = new THREE.Group();
  root.name = identifier;
  root.visible = false;
  root.add(body);
  const { box, sphere } = geometry;
  const { skin, hair, trousers, shoes } = materials;

  function part(parent, shape, material, position, size) {
    const mesh = new THREE.Mesh(shape, material);
    mesh.position.set(...position);
    mesh.scale.set(...size);
    parent.add(mesh);
    return mesh;
  }

  part(body, sphere, shirt, [0, 1.21, 0], [.43, .55, .25]);
  part(body, sphere, trousers, [0, .96, 0], [.33, .22, .23]);
  part(body, sphere, skin, [0, 1.46, 0], [.13, .18, .13]);
  part(body, sphere, skin, [0, 1.61, -.015], [.235, .28, .225]);
  part(body, sphere, hair, [0, 1.70, .004], [.24, .14, .225]);
  part(body, sphere, skin, [0, 1.603, -.123], [.069, .07, .069]);
  const legs = [];
  const arms = [];

  for (const side of [-1, 1]) {
    const leg = new THREE.Group();
    leg.position.set(side * .1, .91, 0);
    part(leg, sphere, trousers, [0, -.27, 0], [.161, .65, .16]);
    part(leg, sphere, trousers, [0, -.63, 0], [.127, .43, .13]);
    part(leg, box, shoes, [0, -.87, -.043], [.129, .08, .232]);
    legs.push(leg);
    const arm = new THREE.Group();
    arm.position.set(side * .207, 1.37, 0);
    arm.rotation.z = side * .10;
    part(arm, sphere, shirt, [0, -.108, 0], [.132, .34, .142]);
    part(arm, sphere, skin, [0, -.343, -.018], [.098, .32, .108]);
    arms.push(arm);
    body.add(leg, arm);
  }

  return {
    root,
    pose(distance, speed) {
      const stride = distance * Math.PI * 2 / 1.3;
      const intensity = speed < stillSpeed ? 0 : clamp(speed / 1.45, 0, 1);
      const swing = Math.sin(stride) * intensity;
      legs[0].rotation.x = swing * .49;
      legs[1].rotation.x = -swing * .49;
      arms[0].rotation.x = -swing * .37;
      arms[1].rotation.x = swing * .37;
      body.position.y = Math.sin(stride) ** 2 * intensity * .024;
    },
  };
}

function sampleFrames(replay, coordinates, heightAt) {
  const previous = new Map();
  return replay.frames.map(([time, people]) => [time, new Map(people.map(([id, lng, lat, angle, speed, edge]) => {
    const [x, y] = coordinates.fromGeo([lng, lat]);
    const last = previous.get(id);
    const stopped = speed < stillSpeed;
    const crossed = edge === replay.crossing.edge || last?.crossed;
    const distance = last ? Math.hypot(x - last.x, y - last.y) : 0;
    const waiting = stopped && last && (!last.stopped || last.waiting && distance < .05);
    const stage = edge === replay.crossing.edge ? "Cruzando" : waiting ? "En espera"
      : crossed && !edge.startsWith(":") ? "En la otra vereda" : "En la vereda";
    const sample = {
      x, y, height: heightAt(x, y), speed, stopped, crossed, waiting, stage,
      heading: stopped && last ? last.heading : coordinates.bearing(lat, angle),
      distance: last ? last.distance + (stopped && last.stopped ? 0 : distance) : 0,
    };
    previous.set(id, sample);
    return [id, sample];
  }))]);
}

export function addPedestrianModels(scene, replay, coordinates, heightAt) {
  if (!replay?.personIndex?.length || !replay.frames.length) return null;
  const frames = sampleFrames(replay, coordinates, heightAt);
  const geometry = { box: new THREE.BoxGeometry(1, 1, 1), sphere: new THREE.SphereGeometry(.5, 9, 7) };
  const material = color => new THREE.MeshStandardMaterial({ color, roughness: .9 });
  const materials = { skin: material(0xc78e64), hair: material(0x39322b), trousers: material(0x354756), shoes: material(0x303337) };
  const walkers = replay.personIndex.map(({ id }, index) => {
    const walker = makeWalker(id, material(shirtColors[index % shirtColors.length]), geometry, materials);
    scene.add(walker.root);
    return walker;
  });
  const shadows = addContactShadows(scene, "pedestrian-contact-shadows", walkers.length);
  const shadow = new THREE.Object3D();
  const shadowOffset = new THREE.Vector3(.025, .007, -.024);
  shadow.scale.set(.74, 1, .61);

  return {
    draw(time) {
      let low = 0;
      let high = frames.length - 1;
      while (low < high) {
        const middle = Math.ceil((low + high) / 2);
        if (frames[middle][0] <= time) low = middle;
        else high = middle - 1;
      }
      const [start, current] = frames[low];
      const [end, next] = frames[low + 1] ?? frames[low];
      const fraction = end > start ? clamp((time - start) / (end - start), 0, 1) : 0;
      const statuses = [];
      for (const { root, pose } of walkers) {
        const first = time >= start ? current.get(root.name) : null;
        root.visible = Boolean(first);
        if (!first) continue;
        const upcoming = next.get(root.name) ?? first;
        const second = first.stopped && upcoming.stopped ? first : upcoming;
        const x = lerp(first.x, second.x, fraction);
        const y = lerp(first.y, second.y, fraction);
        const angle = second.heading - first.heading;
        root.position.set(x, lerp(first.height, second.height, fraction), -y);
        root.rotation.y = first.heading + Math.atan2(Math.sin(angle), Math.cos(angle)) * fraction;
        pose(lerp(first.distance, second.distance, fraction), lerp(first.speed, second.speed, fraction));
        shadow.position.copy(root.position).add(shadowOffset);
        shadow.updateMatrix();
        shadows.setMatrixAt(statuses.length, shadow.matrix);
        statuses.push(`${root.name} · ${first.stage}`);
      }
      shadows.count = statuses.length;
      shadows.instanceMatrix.needsUpdate = true;
      return statuses;
    },
  };
}
