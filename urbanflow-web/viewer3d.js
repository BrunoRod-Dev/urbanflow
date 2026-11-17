import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { createSceneCoordinates, sceneBounds, vehicleScenePose } from "./scene-coordinates.js?v=2";
import { addStreetMeshes, roadHeight } from "./street-meshes.js";
import { addGeography, pilotGroundHole } from "./geography-layer.js?v=3";
import { addVehicleModels } from "./vehicle-models.js?v=3";
import { addSignals3D } from "./signals3d.js?v=1";
import { addPedestrianModels } from "./pedestrian-models.js";
import { addCurbSurvey, curbWalk } from "./curb-survey.js";
import { addLaneQueueLabels } from "./lane-queues.js";

function worldPoint([x, y], height = 0) {
  return new THREE.Vector3(x, height, -y);
}

function nearestApproach(lanes, coordinates, ids, center) {
  let nearest;
  let distance = Infinity;
  for (const id of ids) {
    const points = lanes[id]?.points;
    if (!points || points.length < 2) continue;
    const end = worldPoint(coordinates.fromSumo(points.at(-1)));
    const gap = end.distanceToSquared(center);
    if (gap >= distance) continue;
    const forward = end.clone().sub(worldPoint(coordinates.fromSumo(points.at(-2)))).normalize();
    if (!forward.lengthSq()) continue;
    distance = gap;
    nearest = { id, end, forward };
  }
  return nearest;
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

export async function createViewer3D(host, data, config, badges, street, buildings, survey, geography = null) {
  const coordinates = createSceneCoordinates(data.laneMotion.projection, data.sceneOrigin ?? data.location);
  const geographicBounds = [...config.bounds];
  if (!config.pilot) {
    for (const [, cars] of data.frames) {
      for (const [, lng, lat] of cars) {
        geographicBounds[0] = Math.min(geographicBounds[0], lng - .0001);
        geographicBounds[1] = Math.min(geographicBounds[1], lat - .0001);
        geographicBounds[2] = Math.max(geographicBounds[2], lng + .0001);
        geographicBounds[3] = Math.max(geographicBounds[3], lat + .0001);
      }
    }
  }
  const overviewBounds = sceneBounds(geographicBounds, coordinates);
  const bounds = survey ? sceneBounds(config.bounds.map((value, index) =>
    index < 2 ? Math.min(value, survey.bounds[index]) : Math.max(value, survey.bounds[index])), coordinates) : overviewBounds;
  const scene = new THREE.Scene();
  const lanes = data.laneMotion.lanes;
  const center = worldPoint(coordinates.fromGeo(data.location));
  const signalCenter = config.signals ? worldPoint(coordinates.fromGeo(config.signals.center)) : center;
  const signalLinks = street.signalLinks ?? [];
  const signalApproach = nearestApproach(lanes, coordinates,
    signalLinks.filter(link => !link.insideJunction).map(link => link.fromLane), signalCenter);
  const savedController = config.signals?.controller;
  const controller = data.signalReplay?.states?.[savedController] ? savedController :
    signalApproach?.end.distanceTo(signalCenter) < 45
      ? signalLinks.find(link => link.fromLane === signalApproach.id)?.controller : null;
  const walk = survey && curbWalk(survey.road, coordinates);
  let fleet;
  let signals;
  let queues;
  let pedestrians;
  let curbLayer;
  let curbDistance = 0;
  let curbFocus;
  let renderer;
  let geographySummary = null;
  const roads = new THREE.Group();
  const carsLayer = new THREE.Group();
  const signalLayer = new THREE.Group();
  scene.add(roads, carsLayer, signalLayer);
  try {
    fleet = await addVehicleModels(carsLayer, data, coordinates, roadHeight);
    const groundHole = geography ? pilotGroundHole(geography.meta.bounds, coordinates) : null;
    const { heightAt, onRoad } = addStreetMeshes(roads, data, street, buildings, coordinates, bounds, survey, groundHole);
    if (geography) {
      try {
        geographySummary = addGeography(scene, geography, coordinates, lanes, street, onRoad);
      } catch (error) {
        console.warn("UrbanFlow: la ambientación del piloto no se pudo dibujar.", error);
      }
    }
    if (controller) signals = addSignals3D(signalLayer, data, signalLinks, controller, coordinates, roadHeight, onRoad);
    if (signals) queues = addLaneQueueLabels(scene, signalLinks, controller, coordinates);
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
  const initialFar = camera.far;
  const references = config.references.map(reference => worldPoint(coordinates.fromGeo(reference.location), .06));
  const streetApproach = nearestApproach(lanes, coordinates, config.streetLane ? [config.streetLane] :
    Object.entries(lanes).filter(([id, lane]) => !lane.edge.startsWith(':') && !street.pedestrianLanes?.[id])
      .map(([id]) => id), center);
  const viewPoint = new THREE.Vector3();
  let width = 0;
  let height = 0;
  let preset = "oblique";
  let qa = false;
  let comfortFollow = false;
  let cameraMode = null;
  let chaseState = null;
  let pickHandler = null;
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let deferApproachMarkers = false;
  let qaConnections;
  let qaSignals;
  let updating = false;
  const alert = new THREE.Mesh(new THREE.RingGeometry(2.2, 3, 32),
    new THREE.MeshBasicMaterial({ color: 0xff9d31, side: THREE.DoubleSide, depthTest: false }));
  alert.rotation.x = -Math.PI / 2;
  alert.visible = false;
  scene.add(alert);
  const selected = new THREE.Mesh(new THREE.RingGeometry(3, 3.4, 32),
    new THREE.MeshBasicMaterial({ color: 0x55e4ff, side: THREE.DoubleSide }));
  selected.name = "vehicle-selection";
  selected.rotation.x = -Math.PI / 2;
  selected.visible = false;
  carsLayer.add(selected);

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

  function framePilot(anchor) {
    const [west, south, east, north] = geographySummary.bounds;
    const target = anchor ?? worldPoint(coordinates.fromGeo([(west + east) / 2, (south + north) / 2]), 1.2);
    controls.target.copy(target);
    controls.target.y = 1.2;
    camera.position.set(target.x + 12, 54, target.z + 70);
    camera.far = 2200;
    camera.updateProjectionMatrix();
    scene.fog = null;
    controls.update();
  }

  function setCamera(view) {
    preset = view;
    const aerial = qa && view === "oblique" && !comfortFollow;
    const [[west, east], [south, north]] = overviewBounds;
    const halfVertical = THREE.MathUtils.degToRad(camera.fov / 2);
    const halfHorizontal = Math.atan(Math.tan(halfVertical) * camera.aspect);
    const fitDistance = 1.07 * Math.hypot(east - west, north - south) / 2 /
      Math.sin(Math.min(halfVertical, halfHorizontal));
    controls.maxDistance = aerial ? Math.max(950, fitDistance * 1.5) : 950;
    camera.far = aerial ? Math.max(initialFar, controls.maxDistance * 2) : initialFar;
    camera.updateProjectionMatrix();
    scene.fog = aerial ? null : new THREE.Fog(0xd8e7f0, 165, 490);
    if (curbLayer) curbLayer.visible = preset === "curb";
    if (comfortFollow && geographySummary && preset === "oblique") {
      framePilot();
      render();
      return;
    }
    if (preset === "curb" && walk) {
      setCurbDistance(curbDistance, curbFocus);
      return;
    }
    if (preset === "street") {
      const forward = streetApproach?.forward ?? new THREE.Vector3(1, 0, 0);
      const start = references[0] ?? streetApproach?.end ?? center;
      const right = forward.clone().cross(new THREE.Vector3(0, 1, 0));
      camera.position.copy(start).addScaledVector(forward, -15).addScaledVector(right, 2.5);
      camera.position.y = 1.65;
      controls.target.copy(start).addScaledVector(forward, 15);
      controls.target.y = 1.05;
    } else if (preset === "crossing") {
      controls.target.copy(worldPoint(coordinates.fromGeo(config.crossing), 1.05));
      controls.target.x -= 6;
      camera.position.copy(controls.target).addScaledVector(new THREE.Vector3(-4, 0, 15),
        Math.max(1, 1 / camera.aspect));
      camera.position.y = 1.75;
    } else if (preset === "signals") {
      const approach = lanes[config.signals?.approach ?? signalApproach?.id]?.points;
      const forward = approach?.length >= 2
        ? worldPoint(coordinates.fromSumo(approach.at(-1))).sub(worldPoint(coordinates.fromSumo(approach.at(-2)))).normalize()
        : new THREE.Vector3(1, 0, 0);
      const right = forward.clone().cross(new THREE.Vector3(0, 1, 0));
      controls.target.copy(signalCenter).setY(1.3);
      camera.position.copy(controls.target).addScaledVector(forward, -32).addScaledVector(right, 10);
      camera.position.y = 18;
    } else if (aerial) {
      controls.target.set((west + east) / 2, 0, -(south + north) / 2);
      camera.position.copy(controls.target).addScaledVector(new THREE.Vector3(.04, 1, .18).normalize(), fitDistance);
    } else {
      controls.target.copy(references[0] ?? center).lerp(worldPoint([0, 0], .3), .55);
      const coverage = Math.max(63, (references[0]?.length() ?? 0) * .84);
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

  function focus(target, distance) {
    if (controls.target.distanceToSquared(target) < 1e-8 && distance == null) return;
    const offset = camera.position.clone().sub(controls.target);
    if (distance != null) offset.setLength(distance);
    controls.target.copy(target);
    camera.position.copy(target).add(offset);
    controls.update();
  }

  function pickSceneTarget(clientX, clientY) {
    const rect = renderer.domElement.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    // InstancedMesh keeps a bounding sphere from the last explicit update. The
    // vehicles move every frame, so a click must refresh the selectable meshes.
    scene.traverse(object => {
      if (object.isInstancedMesh && object.name?.startsWith("vehicle-") && object.name !== "vehicle-contact-shadows") {
        object.computeBoundingSphere();
      }
    });
    const hits = raycaster.intersectObjects(scene.children, true);
    for (const hit of hits) {
      const index = fleet.vehicleAt(hit.object, hit.instanceId);
      if (Number.isInteger(index)) return { kind: "vehicle", index };
      const signal = signals?.signalAt(hit.object, hit.instanceId);
      if (signal) return { kind: "signal", ...signal };
      const name = hit.object?.name || "";
      if (name === "vehicle-contact-shadows" || name === "stopped-vehicle-markers" || name === "vehicle-selection"
        || name === "signal-selection" || name === "signal-poles" || name === "signal-signs" || name === "signal-lens"
        || name === "qa-signal-marker" || name.startsWith("signal-movement")) continue;
      return null;
    }
    return null;
  }

  let press = null;
  renderer.domElement.addEventListener("pointerdown", event => {
    if (event.button !== 0) return;
    press = { id: event.pointerId, x: event.clientX, y: event.clientY };
  });
  renderer.domElement.addEventListener("pointerup", event => {
    if (!press || event.pointerId !== press.id || event.button !== 0) return;
    const moved = Math.hypot(event.clientX - press.x, event.clientY - press.y);
    press = null;
    if (moved > 6) return;
    const target = pickSceneTarget(event.clientX, event.clientY);
    if (target) pickHandler?.(target);
  });
  renderer.domElement.addEventListener("pointercancel", () => { press = null; });

  function followSelection(car) {
    const [x, y, yaw] = vehicleScenePose(car, coordinates);
    const index = car[0];
    const now = performance.now();
    const look = worldPoint([x, y], 1.15);
    const place = (heading, alpha) => {
      const behind = new THREE.Vector3(Math.sin(heading), 0, Math.cos(heading));
      const desired = look.clone().addScaledVector(behind, 9);
      desired.y += 3.2;
      if (alpha >= 1) {
        controls.target.copy(look);
        camera.position.copy(desired);
      } else {
        controls.target.lerp(look, alpha);
        camera.position.lerp(desired, alpha);
      }
    };
    if (!chaseState || chaseState.index !== index) {
      chaseState = { index, yaw, time: now };
      place(yaw, 1);
    } else {
      const dt = Math.min(.05, Math.max(0, (now - chaseState.time) / 1000));
      chaseState.time = now;
      const delta = Math.atan2(Math.sin(yaw - chaseState.yaw), Math.cos(yaw - chaseState.yaw));
      const goal = look.clone().addScaledVector(new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw)), 9);
      goal.y += 3.2;
      const snap = camera.position.distanceTo(goal) > 30;
      const blend = 1 - Math.exp(-dt / .14);
      chaseState.yaw = snap ? yaw : chaseState.yaw + delta * blend;
      place(chaseState.yaw, snap ? 1 : blend);
    }
    updating = true;
    controls.update();
    updating = false;
  }

  controls.addEventListener("change", () => { if (!updating) render(); });
  const observer = new ResizeObserver(resize);
  observer.observe(host);
  return {
    resize, setCamera, orbit, signalsAvailable: Boolean(signals),
    hasGeography: Boolean(geographySummary),
    geographySummary,
    setComfort(enabled) { comfortFollow = enabled; },
    setCameraMode(mode) {
      cameraMode = mode === "chase" || mode === "free" ? mode : null;
      if (cameraMode !== "chase") chaseState = null;
      controls.enabled = cameraMode !== "chase";
      renderer.domElement.style.cursor = cameraMode === "chase" ? "default" : "";
    },
    setVehiclePick(handler) { pickHandler = handler; },
    setApproachMarkers(visible) { if (qaSignals) qaSignals.visible = visible; },
    finishQaSetup() { deferApproachMarkers = false; },
    qaConfigure(connections) {
      qa = Boolean(connections);
      deferApproachMarkers = comfortFollow;
      if (!qa || qaConnections) return;
      const vertices = connections.features.flatMap(({ geometry }) => {
        const points = geometry.coordinates.map(point => worldPoint(coordinates.fromGeo(point), roadHeight + .08));
        return points.slice(1).flatMap((point, index) => [points[index], point]);
      });
      qaConnections = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(vertices),
        new THREE.LineBasicMaterial({ color: 0x51e0ff }));
      scene.add(qaConnections);
      qaSignals = new THREE.Group();
      qaSignals.name = "qa-signal-approaches";
      const signalGeometry = new THREE.SphereGeometry(.32, 12, 8);
      const signalMaterial = new THREE.MeshBasicMaterial({ color: 0xffb84a, transparent: true, opacity: .8 });
      for (const { point } of data.signalReplay?.approaches ?? []) {
        const marker = new THREE.Mesh(signalGeometry, signalMaterial);
        marker.name = "qa-signal-marker";
        marker.position.copy(worldPoint(coordinates.fromGeo(point), 1.35));
        qaSignals.add(marker);
      }
      qaSignals.visible = !comfortFollow;
      scene.add(qaSignals);
    },
    qaLayer(key, visible) {
      if (key === "signals" && qaSignals && !deferApproachMarkers) qaSignals.visible = visible;
      const layer = { roads, cars: carsLayer, connections: qaConnections, signals: signalLayer }[key];
      if (layer) layer.visible = visible;
    },
    qaPoint(point) {
      alert.visible = Boolean(point);
      if (point) alert.position.copy(worldPoint(coordinates.fromGeo(point), roadHeight + .12));
    },
    qaFocus(point, close = false) {
      if (!point) return;
      focus(worldPoint(coordinates.fromGeo(point), 1), close ? (preset === "street" ? 25 : 70) : null);
      render();
    },
    qaCenter() {
      return coordinates.toGeo([controls.target.x, -controls.target.z]);
    },
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
    draw(cars, highlightStopped, time, snapshot, followed, close, marked, signalSelection) {
      fleet.draw(cars, highlightStopped);
      signals?.update(time);
      signals?.setSelected(signalSelection?.controllerId ?? null, signalSelection?.fromLane ?? null);
      queues?.show(preset === "signals" && highlightStopped);
      queues?.update(snapshot);
      const statuses = pedestrians?.draw(time);
      if (cameraMode === "chase") {
        if (marked) followSelection(marked);
      } else if (cameraMode == null && followed) {
        const [x, y, yaw] = vehicleScenePose(followed, coordinates);
        updating = true;
        const target = worldPoint([x, y], 1);
        const behind = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw));
        if (comfortFollow && preset === "street") {
          controls.target.copy(target);
          camera.position.copy(target).addScaledVector(behind, 12);
          camera.position.y += 3.8;
          controls.update();
        } else if (comfortFollow && preset === "oblique" && geographySummary) {
          controls.target.copy(target);
          controls.target.y = 1.2;
          camera.position.set(target.x + 12, 54, target.z + 70);
          scene.fog = null;
          controls.update();
        } else if (comfortFollow && preset === "oblique") {
          controls.target.copy(target).addScaledVector(behind, -12);
          controls.target.y = .8;
          camera.position.copy(target).addScaledVector(behind, 26);
          camera.position.y += 15;
          controls.update();
        } else if (close && preset === "street") {
          controls.target.copy(target);
          camera.position.copy(target).add(new THREE.Vector3(25 * Math.sin(yaw), .65, 25 * Math.cos(yaw)));
          controls.update();
        } else {
          focus(target, close ? 70 : null);
        }
        updating = false;
      }
      const ring = marked || (!comfortFollow ? followed : null);
      if (ring) {
        const [x, y] = vehicleScenePose(ring, coordinates);
        selected.position.set(x, roadHeight + .045, -y);
        selected.visible = true;
      } else selected.visible = false;
      render();
      let outside = 0;
      if (qa && carsLayer.visible) {
        for (const [, lng, lat] of cars) {
          const [x, y] = coordinates.fromGeo([lng, lat]);
          viewPoint.set(x, 1, -y).project(camera);
          if (Math.abs(viewPoint.x) > 1 || Math.abs(viewPoint.y) > 1 || Math.abs(viewPoint.z) > 1) outside++;
        }
      }
      return { statuses, outside };
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
