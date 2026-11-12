import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { createSceneCoordinates, sceneBounds } from "./scene-coordinates.js";
import { addStreetMeshes, roadHeight } from "./street-meshes.js";
import { addVehicleModels } from "./vehicle-models.js";
import { addSignals3D } from "./signals3d.js";
import { addPedestrianModels } from "./pedestrian-models.js";
import { addCurbSurvey, curbWalk } from "./curb-survey.js";
import { addLaneQueueLabels } from "./lane-queues.js";

function worldPoint([x, y], height = 0) {
  return new THREE.Vector3(x, height, -y);
}

function disposeScene(scene, extraMaterials) {
  const resources = new Set(extraMaterials);
  scene.traverse(object => {
    if (object.isInstancedMesh) resources.add(object);
    if (object.geometry) resources.add(object.geometry);
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of materials) {
      if (!material || resources.has(material)) continue;
      resources.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) resources.add(value);
    }
  });
  resources.forEach(resource => resource.dispose());
}

export async function createViewer3D(host, data, config, badges, street, buildings, createMotion, survey) {
  const coordinates = createSceneCoordinates(data.laneMotion.projection, data.sceneOrigin ?? data.location);
  const overviewBounds = sceneBounds(config.bounds, coordinates);
  const bounds = survey ? sceneBounds(config.bounds.map((value, index) =>
    index < 2 ? Math.min(value, survey.bounds[index]) : Math.max(value, survey.bounds[index])), coordinates) : overviewBounds;
  const scene = new THREE.Scene();
  const walk = survey && curbWalk(survey.road, coordinates);
  let fleet;
  let signals;
  let queues;
  let pedestrians;
  let curbLayer;
  let curbDistance = 0;
  let curbFocus;
  let renderer;
  try {
    fleet = await addVehicleModels(scene, data, coordinates, bounds, roadHeight, createMotion);
    const heightAt = addStreetMeshes(scene, data, street, buildings, coordinates, bounds, survey);
    signals = addSignals3D(scene, data, street.signalLinks ?? [], config.signals.controller, coordinates, roadHeight);
    if (signals) queues = addLaneQueueLabels(scene, street.signalLinks, config.signals.controller, coordinates);
    pedestrians = addPedestrianModels(scene, data.pedestrianReplay, coordinates, heightAt);
    if (survey) curbLayer = addCurbSurvey(scene, survey, coordinates, roadHeight);
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  } catch (error) {
    disposeScene(scene, signals?.materials);
    throw error;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.domElement.setAttribute("aria-hidden", "true");
  host.append(renderer.domElement);
  scene.background = new THREE.Color(0xd8e7f0);
  scene.fog = new THREE.Fog(0xd8e7f0, 165, 490);
  scene.add(new THREE.HemisphereLight(0xe7f1ff, 0x9d987f, 1.32));
  const sun = new THREE.DirectionalLight(0xffead1, 2.55);
  sun.position.set(-98, 135, 68);
  scene.add(sun);

  const camera = new THREE.PerspectiveCamera(47, 1, .12, 1500);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.minDistance = 2.8;
  controls.maxDistance = 950;
  controls.maxPolarAngle = Math.PI / 2;
  const references = config.references.map(reference => worldPoint(coordinates.fromGeo(reference.location), .06));
  const ramp = data.laneMotion.lanes[config.streetLane]?.points;
  const viewPoint = new THREE.Vector3();
  let width = 0;
  let height = 0;
  let preset = "oblique";

  function render() {
    if (!width || !height || !host.clientWidth) return;
    const near = THREE.MathUtils.clamp(camera.position.distanceTo(controls.target) / 95, .12, 6);
    if (camera.near !== near) {
      camera.near = near;
      camera.updateProjectionMatrix();
    }
    renderer.render(scene, camera);
    for (const [index, point] of references.entries()) {
      viewPoint.copy(point).project(camera);
      const badge = badges[index];
      badge.hidden = Math.abs(viewPoint.x) > 1 || Math.abs(viewPoint.y) > 1 || Math.abs(viewPoint.z) > 1;
      if (!badge.hidden) {
        badge.style.left = `${(viewPoint.x + 1) * width / 2}px`;
        badge.style.top = `${(1 - viewPoint.y) * height / 2}px`;
      }
    }
  }

  function resize() {
    if (!host.clientWidth || !host.clientHeight) return;
    width = host.clientWidth;
    height = host.clientHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
    render();
  }

  function setCamera(view) {
    preset = view;
    if (curbLayer) curbLayer.visible = preset === "curb";
    if (preset === "curb" && walk) {
      setCurbDistance(curbDistance, curbFocus);
      return;
    }
    if (preset === "street") {
      const forward = ramp?.length >= 2
        ? worldPoint(coordinates.fromSumo(ramp.at(-1))).sub(worldPoint(coordinates.fromSumo(ramp.at(-2)))).normalize()
        : references[1].clone().sub(references[0]).normalize();
      const right = forward.clone().cross(new THREE.Vector3(0, 1, 0));
      camera.position.copy(references[0]).addScaledVector(forward, -15).addScaledVector(right, 2.5);
      camera.position.y = 1.65;
      controls.target.copy(references[0]).addScaledVector(forward, 15);
      controls.target.y = 1.05;
    } else if (preset === "crossing") {
      controls.target.copy(worldPoint(coordinates.fromGeo(config.crossing), 1.05));
      controls.target.x -= 6;
      camera.position.copy(controls.target).addScaledVector(new THREE.Vector3(-4, 0, 15),
        Math.max(1, 1 / camera.aspect));
      camera.position.y = 1.75;
    } else if (preset === "signals") {
      const approach = data.laneMotion.lanes[config.signals.approach]?.points;
      const forward = approach?.length >= 2
        ? worldPoint(coordinates.fromSumo(approach.at(-1))).sub(worldPoint(coordinates.fromSumo(approach.at(-2)))).normalize()
        : new THREE.Vector3(1, 0, 0);
      const right = forward.clone().cross(new THREE.Vector3(0, 1, 0));
      controls.target.copy(worldPoint(coordinates.fromGeo(config.signals.center), 1.3));
      camera.position.copy(controls.target).addScaledVector(forward, -32).addScaledVector(right, 10);
      camera.position.y = 18;
    } else {
      controls.target.copy(references[0]).lerp(worldPoint([0, 0], .3), .55);
      const halfVertical = THREE.MathUtils.degToRad(camera.fov / 2);
      const halfHorizontal = Math.atan(Math.tan(halfVertical) * camera.aspect);
      const coverage = Math.max(63, references[0].length() * .84);
      const distance = coverage / Math.tan(Math.min(halfVertical, halfHorizontal));
      camera.position.copy(controls.target).addScaledVector(new THREE.Vector3(.85, 1.14, 1).normalize(), distance);
    }
    controls.update();
    render();
  }

  function setCurbDistance(distance, focus) {
    curbDistance = distance;
    curbFocus = focus;
    const { eye, target, direction } = walk.positionAt(distance);
    camera.position.copy(eye);
    controls.target.copy(focus ? worldPoint(coordinates.fromGeo(focus), .8) : target);
    if (camera.position.distanceTo(controls.target) < 3) camera.position.addScaledVector(direction, -3);
    controls.update();
    render();
  }

  function orbit(azimuth, polar) {
    const offset = camera.position.clone().sub(controls.target);
    const angle = new THREE.Spherical().setFromVector3(offset);
    angle.theta += azimuth;
    angle.phi = THREE.MathUtils.clamp(angle.phi + polar, .08, controls.maxPolarAngle);
    camera.position.copy(controls.target).add(offset.setFromSpherical(angle));
    controls.update();
  }

  controls.addEventListener("change", render);
  const observer = new ResizeObserver(resize);
  observer.observe(host);
  return {
    resize, setCamera, orbit, signalsAvailable: Boolean(signals),
    curbLength: walk?.length,
    setCurbDistance,
    focusCurbFeature(location) {
      const distance = walk.distanceTo(location);
      setCurbDistance(distance, location);
      return distance;
    },
    setSignalOverlay(visible) {
      signals?.setOverlay(visible);
      render();
    },
    zoom(factor) {
      const offset = camera.position.clone().sub(controls.target);
      offset.setLength(THREE.MathUtils.clamp(offset.length() * factor, controls.minDistance, controls.maxDistance));
      camera.position.copy(controls.target).add(offset);
      controls.update();
    },
    draw(cars, highlightStopped, time, snapshot) {
      fleet.draw(cars, highlightStopped, time);
      signals?.update(time);
      queues?.show(preset === "signals" && highlightStopped);
      queues?.update(snapshot);
      const statuses = pedestrians?.draw(time);
      render();
      return statuses;
    },
    dispose() {
      observer.disconnect();
      controls.dispose();
      disposeScene(scene, signals?.materials);
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    },
  };
}
