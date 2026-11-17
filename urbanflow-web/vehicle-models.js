import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { vehicleScenePose } from "./scene-coordinates.js?v=2";
import { createMotorcycleModel } from "./motorcycle-model.js";
import { addContactShadows } from "./contact-shadows.js";

const assetDefinitions = {
  car: { url: new URL("./assets/vehicles/sedan.glb", import.meta.url), yaw: Math.PI },
  bus: { url: new URL("./assets/vehicles/urban-bus.glb", import.meta.url), yaw: Math.PI },
  motorcycle: { create: createMotorcycleModel, yaw: 0 },
  pickup: { url: new URL("./assets/vehicles/pickup.glb", import.meta.url), yaw: Math.PI },
};
const fallbackCar = { vClass: "passenger", length: 5, width: 1.8, height: 1.5 };

function fitModel(root, spec, yaw) {
  const oriented = new THREE.Group();
  oriented.rotation.y = yaw;
  oriented.add(root);
  oriented.updateMatrixWorld(true);
  const bounds = new THREE.Box3().setFromObject(oriented, true);
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const scale = new THREE.Vector3(spec.width / size.x, spec.height / size.y, spec.length / size.z);
  const normalize = new THREE.Matrix4().makeScale(scale.x, scale.y, scale.z);
  normalize.setPosition(-center.x * scale.x, -bounds.min.y * scale.y, -center.z * scale.z);
  const byMaterial = new Map();
  oriented.traverse(mesh => {
    if (!mesh.isMesh) return;
    const material = mesh.material;
    const geometry = mesh.geometry.clone().applyMatrix4(normalize.clone().multiply(mesh.matrixWorld));
    if (!byMaterial.has(material)) byMaterial.set(material, []);
    byMaterial.get(material).push(geometry);
  });
  return [...byMaterial].flatMap(([material, geometries]) => {
    const first = geometries[0];
    const attributes = Object.keys(first.attributes);
    const compatible = geometries.length > 1 && geometries.every(geometry =>
      Boolean(geometry.index) === Boolean(first.index) && Object.keys(geometry.attributes).length === attributes.length
      && attributes.every(key => {
        const attribute = geometry.attributes[key];
        return attribute?.array.constructor === first.attributes[key].array.constructor
          && attribute.itemSize === first.attributes[key].itemSize && attribute.normalized === first.attributes[key].normalized;
      }));
    const merged = compatible && !Array.isArray(material) ? mergeGeometries(geometries) : null;
    if (merged) geometries.forEach(geometry => geometry.dispose());
    return (merged ? [merged] : geometries).map(geometry => ({ geometry, material }));
  });
}

function modelBatch(scene, asset, kind, spec, capacity, yaw) {
  const parts = fitModel(asset, spec, yaw).map(({ geometry, material }, index) => {
    const instances = new THREE.InstancedMesh(geometry, material, capacity);
    instances.name = `vehicle-${kind}-${index}`;
    instances.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    instances.count = 0;
    instances.frustumCulled = false;
    scene.add(instances);
    return instances;
  });
  return { parts, spec, count: 0 };
}

function stoppedOutline() {
  const vertices = [];
  const strip = (x0, z0, x1, z1) => {
    vertices.push(x0, 0, z0, x0, 0, z1, x1, 0, z0, x1, 0, z0, x0, 0, z1, x1, 0, z1);
  };
  strip(-.5, -.5, -.445, .5);
  strip(.445, -.5, .5, .5);
  strip(-.445, -.5, .445, -.465);
  strip(-.445, .465, .445, .5);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
  return geometry;
}

export async function addVehicleModels(scene, data, coordinates, roadHeight) {
  const kindFor = id => data.vehicleIndex?.[id]?.type ?? "car";
  const specFor = kind => data.vehicleTypes?.[kind] ?? fallbackCar;
  const assetFor = kind => {
    if (Object.hasOwn(assetDefinitions, kind)) return kind;
    const vClass = specFor(kind).vClass;
    return Object.hasOwn(assetDefinitions, vClass) ? vClass : "car";
  };
  const capacities = new Map();
  let markerCapacity = 0;
  for (const [, cars] of data.frames) {
    markerCapacity = Math.max(markerCapacity, cars.length);
    const frameCounts = new Map();
    for (const car of cars) {
      const kind = kindFor(car[0]);
      const count = (frameCounts.get(kind) ?? 0) + 1;
      frameCounts.set(kind, count);
      capacities.set(kind, Math.max(capacities.get(kind) ?? 0, count));
    }
  }
  const loader = new GLTFLoader();
  const assetKeys = new Set([...capacities.keys()].map(assetFor));
  const assets = new Map(await Promise.all([...assetKeys].map(async key => {
    const { create, url } = assetDefinitions[key];
    return [key, create ? create() : (await loader.loadAsync(url.href)).scene];
  })));
  const batches = new Map([...capacities].map(([kind, capacity]) => {
    const key = assetFor(kind);
    return [kind, modelBatch(scene, assets.get(key), kind, specFor(kind), capacity, assetDefinitions[key].yaw)];
  }));
  const stopped = new THREE.InstancedMesh(stoppedOutline(),
    new THREE.MeshBasicMaterial({ color: 0xffbf62, opacity: .93, transparent: true, depthWrite: false, toneMapped: false }),
    Math.max(markerCapacity, 1));
  stopped.name = "stopped-vehicle-markers";
  stopped.count = 0;
  stopped.frustumCulled = false;
  stopped.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  scene.add(stopped);

  const shadows = addContactShadows(scene, "vehicle-contact-shadows", Math.max(markerCapacity, 1));
  const pose = new THREE.Object3D();
  const marker = new THREE.Object3D();
  const slots = new Map();
  return {
    vehicleAt(object, instanceId) {
      if (!object?.isInstancedMesh || !Number.isInteger(instanceId) || instanceId < 0) return null;
      const list = slots.get(object);
      const index = list?.[instanceId];
      return Number.isInteger(index) ? index : null;
    },
    draw(cars, highlightStopped) {
      slots.clear();
      for (const batch of batches.values()) batch.count = 0;
      let stoppedCount = 0;
      let shadowCount = 0;
      for (const car of cars) {
        const [id, , , , speed] = car;
        const batch = batches.get(kindFor(id));
        // The normalized bus mesh is one rigid body. Its axle spacing follows its model scale.
        const [x, y, yaw] = vehicleScenePose(car, coordinates);
        pose.position.set(x, roadHeight, -y);
        pose.rotation.y = yaw;
        pose.updateMatrix();
        const slot = batch.count;
        for (const instances of batch.parts) {
          instances.setMatrixAt(slot, pose.matrix);
          let list = slots.get(instances);
          if (!list) {
            list = [];
            slots.set(instances, list);
          }
          list[slot] = id;
        }
        batch.count++;
        marker.position.set(x + .11, roadHeight + .006, -y - .09);
        marker.rotation.y = yaw;
        marker.scale.set(batch.spec.width + .72, 1, batch.spec.length + .75);
        marker.updateMatrix();
        shadows.setMatrixAt(shadowCount++, marker.matrix);
        if (highlightStopped && speed < .1) {
          marker.position.set(x, roadHeight + .012, -y);
          marker.scale.set(batch.spec.width + .38, 1, batch.spec.length + .36);
          marker.updateMatrix();
          stopped.setMatrixAt(stoppedCount++, marker.matrix);
        }
      }
      for (const batch of batches.values()) {
        for (const instances of batch.parts) {
          instances.count = batch.count;
          instances.instanceMatrix.needsUpdate = true;
        }
      }
      stopped.count = stoppedCount;
      stopped.instanceMatrix.needsUpdate = true;
      shadows.count = shadowCount;
      shadows.instanceMatrix.needsUpdate = true;
    },
  };
}
