"use strict";

const element = id => document.getElementById(id);
const pilotScenario = window.urbanflowPilot;
const geographicMap = createMaldonadoMap(onMapSelection);
geographicMap.setVehicleSelect(selectVehicle);
geographicMap.setSignalSelect(selectSignal);
const replayViews = createReplayViews(geographicMap, draw);
replayViews.setVehicleSelect(selectVehicle);
replayViews.setSignalSelect(selectSignal);
const replayQa = createReplayQa(geographicMap, time => {
  setRunning(false);
  currentTime = Math.max(0, Math.min(duration, time - firstTime));
  draw();
}, draw, replayViews);
const canvas = element("traffic-map");
const timeline = element("timeline");
const highlight = element("highlight");
const simulation = element("simulador");
const mapSection = element("maldonado");
const librarySection = element("estudios");
const comparisonSection = element("comparacion");
const routeFeedback = element("route-feedback");
const trafficEditor = element("traffic-editor");
const trafficForm = element("traffic-form");
const trafficFields = element("traffic-fields");
const trafficDuration = element("traffic-duration");
const trafficSource = element("traffic-source");
const trafficFleetOption = element("traffic-fleet-option");
const trafficMixedFleet = element("traffic-mixed-fleet");
const trafficFile = element("traffic-file");
const trafficFeedback = element("traffic-feedback");
const number = new Intl.NumberFormat("es-UY");
const studyDate = new Intl.DateTimeFormat("es-UY", { dateStyle: "short", timeStyle: "medium", timeZone: "America/Montevideo" });
const generatorAddressError = "Esta dirección sirve la página, pero no tiene el generador actualizado. Usá la dirección que imprime la ventana nueva de UrbanFlow, que puede ser la del puerto 8765.";
let scenario;
let frames;
let firstTime;
let duration;
let cycle;
let trafficMap;
let laneMotion;
let routes;
let currentTime = 0;
let running = false;
let animation = 0;
let lastTick = null;
let lastFrame = -1;
let lastPhase = "";
let viewVersion = 0;
let trafficInputs = new Map();

async function apiRequest(path, options) {
  let response;
  try {
    response = await fetch(path, { cache: "no-store", ...options });
  } catch {
    throw new Error("El servidor local dejó de responder. Revisá la ventana de UrbanFlow y su dirección.");
  }
  if (!response.headers.get("Content-Type")?.includes("application/json")) {
    throw new Error(generatorAddressError);
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || `El servidor devolvió un error (${response.status}).`);
  return data;
}

function studyRequest(path, options) {
  return apiRequest(`/api/studies${path}`, options);
}

async function verifyGenerator() {
  if (location.protocol === "file:") {
    throw new Error("Este archivo está abierto directamente desde la carpeta. Usá la dirección que imprime Abrir UrbanFlow.cmd.");
  }
  const health = await apiRequest("/api/health");
  if (health.app !== "urbanflow" || health.apiVersion !== 13) throw new Error(generatorAddressError);
}

function postStudy(path, data) {
  return studyRequest(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
}

async function waitForStudy(id, isCurrent, onStatus) {
  const deadline = Date.now() + 10 * 60 * 1000;
  while (isCurrent()) {
    const status = await studyRequest(`/${id}`);
    if (!isCurrent()) return false;
    onStatus(status);
    if (status.stage === "error") throw new Error(status.message);
    if (status.stage === "ready") return true;
    if (Date.now() >= deadline) throw new Error("La corrida está tardando más de lo esperado. Podés volver a abrir el estudio desde Estudios para revisar el avance.");
    await new Promise(resolve => setTimeout(resolve, 600));
  }
  return false;
}

function groupSavedStudies(studies) {
  const byId = new Map(studies.map(study => [study.id, study]));
  const groups = new Map();
  for (const study of studies) {
    const visited = new Set([study.id]);
    let original = study;
    while (byId.has(original.parentId) && !visited.has(original.parentId)) {
      original = byId.get(original.parentId);
      visited.add(original.id);
    }
    if (!groups.has(original.id)) groups.set(original.id, { original, runs: [] });
    groups.get(original.id).runs.push(study);
  }
  return [...groups.values()];
}

function searchable(text) {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase("es-UY");
}

function studyDetails(study) {
  const source = study.traffic?.source === "observed" ? "Conteos observados" : "Tráfico de muestra";
  const period = study.traffic?.durationMinutes ? `${study.traffic.durationMinutes} min` : "";
  const date = new Date(study.createdAt ?? NaN);
  return [source, period, Number.isFinite(study.trips) ? `${number.format(study.trips)} viajes programados` : "",
    Number.isNaN(date.valueOf()) ? "" : studyDate.format(date)].filter(Boolean).join(" · ");
}

function showTrafficFeedback(message, error = false) {
  trafficFeedback.textContent = message;
  trafficFeedback.hidden = !message;
  trafficFeedback.dataset.error = String(error);
}

function updateTrafficTotal() {
  const total = [...trafficInputs.values()].reduce((sum, input) => sum + (Number(input.value) || 0), 0);
  const description = trafficMixedFleet.checked ? "vehículos configurados, más la flota faltante" : "vehículos en el período";
  element("traffic-total").textContent = `${number.format(total)} ${description}`;
}

function updateTrafficSource() {
  const sector = scenario ? sectorForStudy(scenario) : null;
  trafficFleetOption.hidden = !sector?.features?.includes("sampleFleet") || trafficSource.value !== "sample";
  if (trafficFleetOption.hidden) trafficMixedFleet.checked = false;
  updateTrafficTotal();
}

function showInspectorPanel(editing) {
  element("study-summary").hidden = editing;
  trafficEditor.hidden = !editing;
  element("show-summary").setAttribute("aria-pressed", String(!editing));
  element("edit-traffic").setAttribute("aria-pressed", String(editing));
}

function configureTraffic(data) {
  const movements = data.traffic?.movements ?? [];
  element("inspector-switch").hidden = !movements.length && !data.trafficMessage;
  showInspectorPanel(false);
  trafficFields.hidden = !movements.length;
  trafficFields.disabled = false;
  trafficFile.value = "";
  trafficMixedFleet.checked = false;
  showTrafficFeedback(data.trafficMessage ?? "");
  const list = element("traffic-movements");
  list.replaceChildren();
  trafficInputs = new Map();
  if (!movements.length) return;

  trafficDuration.value = data.traffic.durationMinutes;
  trafficSource.value = data.traffic.source;
  for (const movement of movements) {
    const label = document.createElement("label");
    label.className = "traffic-movement";
    const name = document.createElement("span");
    name.textContent = movement.label;
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = "10000";
    input.step = "1";
    input.required = true;
    input.value = movement.count;
    trafficInputs.set(movement.id, input);
    label.append(name, input);
    list.append(label);
  }
  updateTrafficSource();
}

async function applyTrafficFile() {
  const file = trafficFile.files[0];
  if (!file) return;
  const version = viewVersion;
  trafficFile.value = "";
  try {
    if (file.size > 256 * 1024) throw new Error("El archivo supera 256 KB. Usá la plantilla de este estudio.");
    const csv = await file.text();
    if (version !== viewVersion || trafficFields.disabled) return;
    const counts = parseTrafficCsv(csv, scenario.traffic.movements);
    for (const [id, count] of counts) trafficInputs.get(id).value = count;
    trafficSource.value = "observed";
    updateTrafficSource();
    showTrafficFeedback("Conteos cargados. Revisá la duración y elegí Guardar y simular.");
  } catch (error) {
    if (version === viewVersion) showTrafficFeedback(error.message, true);
  }
}

async function saveTraffic(event) {
  event.preventDefault();
  const identifier = studyIdentifier(location.hash);
  if (!identifier || !trafficInputs.size || trafficFields.disabled) return;
  const version = viewVersion;
  const isCurrent = () => version === viewVersion;
  const counts = Object.fromEntries([...trafficInputs].map(([id, input]) => [id, Number(input.value)]));
  const values = Object.values(counts);
  if (values.some(count => !Number.isSafeInteger(count) || count < 0) || !values.some(count => count > 0)) {
    showTrafficFeedback("Ingresá números enteros y al menos un movimiento con vehículos.", true);
    return;
  }
  if (values.reduce((total, count) => total + count, 0) > 10000) {
    showTrafficFeedback("Ingresá hasta 10.000 vehículos en total por corrida.", true);
    return;
  }
  const traffic = { durationMinutes: Number(trafficDuration.value), source: trafficSource.value, counts };
  if (trafficMixedFleet.checked) traffic.sampleMixedFleet = true;
  setRunning(false);
  trafficFields.disabled = true;
  showTrafficFeedback("Guardando y preparando la nueva corrida…");
  try {
    await verifyGenerator();
    if (!isCurrent()) return;
    const { id } = await postStudy(`/${identifier}/runs`, traffic);
    const ready = await waitForStudy(id, isCurrent, status => showTrafficFeedback(status.message));
    if (!ready || !isCurrent()) return;
    location.hash = `#estudio/${id}`;
  } catch (error) {
    if (isCurrent()) showTrafficFeedback(error.message, true);
  } finally {
    if (isCurrent()) trafficFields.disabled = false;
  }
}

function loadScenario(nextScenario) {
  if (scenario === nextScenario) return;
  setRunning(false);
  scenario = nextScenario;
  frames = scenario.frames;
  firstTime = frames[0][0];
  duration = frames[frames.length - 1][0] - firstTime;
  cycle = scenario.phases?.reduce((sum, phase) => sum + phase.duration, 0) ?? 0;
  trafficMap = scenario.geographic ? null : createTrafficMap(canvas, scenario);
  const projection = describeProjection(scenario.laneMotion);
  laneMotion = projection.ok ? createLaneMotion(scenario.laneMotion) : null;
  signalCatalog = buildSignalCatalog(scenario);
  geographicMap.setSignalCatalog(signalCatalog);
  currentTime = Math.min(scenario.pedestrianReplay ? 10 : scenario.geographic ? 20 : 72, duration);
  lastFrame = -1;
  lastPhase = "";
  routes = {};
  element("approaches").replaceChildren();
  for (const [direction, name] of Object.entries(scenario.approaches)) {
    const row = document.createElement("div");
    row.className = "approach";
    const label = document.createElement("span");
    label.textContent = name;
    const meter = document.createElement("meter");
    meter.setAttribute("aria-label", `Proporción detenida, acceso ${name}`);
    const count = document.createElement("strong");
    row.append(label, meter, count);
    element("approaches").append(row);
    routes[direction] = { meter, count };
  }

  const isPilot = scenario === pilotScenario;
  const isGeographic = scenario.geographic;
  element("sim-title").textContent = scenario.title ?? "Cruce semaforizado";
  const schematic = isPilot ? sectorForHash(location.hash).sector?.schematic?.label : "";
  canvas.setAttribute("aria-label", isPilot
    ? (schematic || "Vista esquemática del cruce de demostración con vehículos simulados")
    : "Vista cenital esquemática de una intersección de cuatro accesos con vehículos y semáforos");
  const sourceBadge = isGeographic || isPilot || scenario.source === "demo" ? "Tráfico de muestra" : "Reproducción SUMO";
  element("source-label").textContent = scenario.traffic?.source === "observed" ? "Conteos observados" : sourceBadge;
  element("source-note").textContent = scenario.experimental
    ? `${scenario.experimentalLabel}. ${scenario.inserted} vehículos ingresaron y ${scenario.arrived} terminaron en esta corrida.`
    : isGeographic
    ? `${scenario.inserted} vehículos ingresaron y ${scenario.arrived} terminaron durante la corrida de SUMO.`
    : isPilot
    ? "Corrida de SUMO con rutas y volúmenes ilustrativos."
    : scenario.source === "sumo" ? "Trayectorias exportadas desde SUMO. Vista esquemática del cruce."
      : "Recorridos ilustrativos basados en la red y el ciclo del escenario. Vista esquemática.";
  if (scenario.pedestrianReplay) {
    element("source-note").textContent += ` ${scenario.pedestrianReplay.personIndex.length} peatones de muestra.`;
  }
  element("source-credit").hidden = !isPilot && !isGeographic;
  const signals = Object.keys(scenario.signalReplay?.states ?? {}).length;
  element("signal-legend").hidden = !signals;
  const signalNote = element("signal-note");
  signalNote.hidden = !signals;
  signalNote.textContent = `${signals} ${signals === 1 ? "controlador" : "controladores"} en el área. En el mapa 2D, los colores muestran las fases de SUMO. El violeta indica giros con estados distintos en el mismo carril. Los tiempos son estimados.`;
  const assumptions = element("model-assumptions");
  assumptions.hidden = !isGeographic;
  assumptions.textContent = scenario.assumptions?.join(" ") ?? "";
  element("signal-dot").hidden = !cycle;
  const experimental = element("experimental-replay");
  if (experimental) {
    experimental.hidden = !scenario.experimental;
    const label = element("experimental-replay-label");
    if (label) label.textContent = scenario.experimentalLabel || "";
  }
  if (!cycle) {
    const roundabout = isPilot || scenario.roundabout;
    if (scenario.pedestrianReplay) {
      element("phase-name").textContent = "Prioridad peatonal";
      element("phase-remaining").textContent = "Los vehículos ceden el paso en la cebra de Burnett.";
    } else {
      element("phase-name").textContent = roundabout ? "Prioridad de la rotonda" : "Control vial importado";
      element("phase-remaining").textContent = roundabout ? "Ceda el paso al ingresar." : "Giros, prioridades y señales de la red de SUMO.";
    }
  }
  element("sim-in").disabled = false;
  element("sim-out").disabled = false;
  const period = scenario.traffic?.durationMinutes;
  element("demand").textContent = isGeographic
    ? `${number.format(scenario.trips)} viajes${period ? ` en ${period} min` : ""}`
    : `${number.format(scenario.demand)} veh/h`;
  configureTraffic(scenario);
  element("duration").textContent = formatTime(duration);
  timeline.max = duration;
  timeline.step = "any";
}

function formatTime(time) {
  const whole = Math.floor(time);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

function getFrameIndex(time) {
  let left = 0;
  let right = frames.length - 1;
  while (left < right) {
    const middle = Math.ceil((left + right) / 2);
    if (frames[middle][0] <= time) left = middle;
    else right = middle - 1;
  }
  return left;
}

function phaseAt(time) {
  let timeInCycle = ((time + scenario.offset) % cycle + cycle) % cycle;
  for (const phase of scenario.phases) {
    if (timeInCycle < phase.duration) return [phase.signals, Math.ceil(phase.duration - timeInCycle)];
    timeInCycle -= phase.duration;
  }
  return [scenario.phases[0].signals, 0];
}

function interpolate(index, time) {
  const motion = laneMotion;
  const [from, cars] = frames[index];
  if (index === frames.length - 1 || time === from) return motion ? cars.map(motion.sample) : cars;
  motion?.beginFrame(cars);
  const [to, upcoming] = frames[index + 1];
  const ratio = (time - from) / (to - from);
  const nextCars = new Map(upcoming.map(car => [car[0], car]));
  return cars.map(car => {
    const [id, x, y, angle, speed, approach] = car;
    const next = nextCars.get(id);
    if (motion) return next ? motion.between(car, next, ratio, to - from) : motion.sample(car);
    if (!next) return car;
    const turn = ((next[3] - angle + 540) % 360) - 180;
    return [id, x + (next[1] - x) * ratio, y + (next[2] - y) * ratio, angle + turn * ratio, speed, approach];
  });
}

function updateMetrics(cars) {
  const stops = {};
  const entering = {};
  let stopped = 0;
  let speed = 0;
  for (const car of cars) {
    const velocity = car[4];
    const approach = car[5];
    speed += velocity;
    entering[approach] = (entering[approach] || 0) + 1;
    if (velocity < .1) {
      stopped++;
      stops[approach] = (stops[approach] || 0) + 1;
    }
  }
  element("vehicle-count").textContent = cars.length;
  element("stopped-count").textContent = stopped;
  element("mean-speed").textContent = cars.length ? Math.round(speed * 3.6 / cars.length) : "—";
  for (const [approach, { meter, count }] of Object.entries(routes)) {
    const total = stops[approach] || 0;
    meter.max = entering[approach] || 1;
    meter.value = total;
    count.textContent = total;
  }
}

function updatePhase(signals, remaining) {
  const active = Object.keys(scenario.approaches).filter(direction => signals[direction] === "g" || signals[direction] === "y");
  const amber = Object.values(signals).includes("y");
  const state = amber ? "Amarillo" : active.length ? "Verde" : "Rojo";
  const direction = active.map(code => scenario.approaches[code]).join("–");
  const summary = direction ? `${state} ${direction}` : "Rojo general";
  const signature = `${summary}${remaining}`;
  if (signature === lastPhase) return;
  element("phase-name").textContent = summary;
  element("signal-dot").className = `signal-dot${amber ? " amber" : active.length ? "" : " red"}`;
  element("phase-remaining").textContent = `${remaining} s para el cambio`;
  lastPhase = signature;
}

let inspection = null;
let inspectorClosed = false;
let signalLab = null;
let signalLabPoll = 0;
let signalCatalog = [];
const vehicleTypeNames = {
  car: "Automóvil", bus: "Ómnibus", "terminal-bus": "Ómnibus", motorcycle: "Motocicleta", pickup: "Camioneta",
};
const vehicleMeasure = new Intl.NumberFormat("es-UY", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const signalAspects = {
  r: "Rojo", R: "Rojo", y: "Amarillo", Y: "Amarillo", G: "Verde con prioridad", g: "Verde cediendo",
  s: "Verde tras detenerse", u: "Rojo y amarillo", o: "Apagado", O: "Apagado",
};

function projectLaneEnd(lane, projection) {
  const point = lane?.points?.at(-1);
  if (!point || !projection) return null;
  if (projection.type === "utm" && typeof createSumoProjection === "function") {
    return createSumoProjection(projection).toGeo(point[0], point[1]);
  }
  if (!projection.origin || !projection.location || !projection.east || !projection.north) return null;
  const [ox, oy] = projection.origin;
  return projection.location.map((coordinate, axis) =>
    coordinate + (point[0] - ox) * projection.east[axis] + (point[1] - oy) * projection.north[axis]);
}

function buildSignalCatalog(study) {
  const approaches = study?.signalReplay?.approaches ?? [];
  const lanes = study?.laneMotion?.lanes ?? {};
  const projection = study?.laneMotion?.projection;
  const ends = [];
  for (const [id, lane] of Object.entries(lanes)) {
    if (id.startsWith(":") || !lane?.points || lane.points.length < 2) continue;
    const point = projectLaneEnd(lane, projection);
    if (point) ends.push({ id, point });
  }
  const pairs = [];
  approaches.forEach((approach, index) => {
    const [lng, lat] = approach.point ?? [];
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
    for (const end of ends) pairs.push({ distance: Math.hypot(end.point[0] - lng, end.point[1] - lat), index, id: end.id });
  });
  pairs.sort((a, b) => a.distance - b.distance);
  const usedApproach = new Set();
  const usedLane = new Set();
  const fromLane = [];
  for (const pair of pairs) {
    if (usedApproach.has(pair.index) || usedLane.has(pair.id) || pair.distance > .00003) continue;
    usedApproach.add(pair.index);
    usedLane.add(pair.id);
    fromLane[pair.index] = pair.id;
  }
  return approaches.map((approach, index) => ({
    controllerId: approach.controller,
    fromLane: fromLane[index] ?? null,
    indices: (approach.indices ?? []).map(Number).filter(Number.isInteger),
  })).filter(item => item.controllerId && item.indices.length);
}

function humanizeIdentifier(value) {
  const text = String(value ?? "");
  const tokens = text.split(/[-_]/).filter(Boolean);
  const words = tokens.filter(token => /^[A-Za-z]{3,}$/.test(token));
  if (!words.length || tokens.length > 5 || text.length > 36) return null;
  return tokens.map(token => /^[A-Za-z]{3,}$/.test(token)
    ? token.charAt(0).toUpperCase() + token.slice(1).toLowerCase()
    : token).join(" ");
}

function approachLabel(fromLane) {
  if (!fromLane || !scenario?.approaches) return null;
  const edge = fromLane.replace(/_\d+$/, "");
  const name = scenario.approaches[fromLane] || scenario.approaches[edge];
  return typeof name === "string" ? humanizeIdentifier(name) : null;
}

function aspectTone(code) {
  if (code === "r" || code === "R") return "red";
  if (code === "y" || code === "Y" || code === "u") return "amber";
  if (code === "G" || code === "g" || code === "s") return "green";
  if (code === "o" || code === "O") return "off";
  return "unknown";
}

function fillAspects(container, state, indices) {
  const rows = (indices ?? []).map(index => {
    const code = typeof state === "string" ? state[index] : "";
    const row = document.createElement("div");
    row.className = "movement-row";
    row.dataset.tone = aspectTone(code);
    const badge = document.createElement("span");
    badge.className = "movement-index";
    badge.textContent = String(index);
    const label = document.createElement("span");
    label.textContent = signalAspects[code] || "Sin dato";
    row.append(badge, label);
    return row;
  });
  container.replaceChildren(...(rows.length ? rows : [document.createTextNode("Sin dato")]));
}

function signalTitle(selected) {
  return approachLabel(selected.fromLane)
    || (selected.indices.length === 1 ? `Movimiento ${selected.indices[0]}`
      : selected.indices.length === 2 ? `Movimientos ${selected.indices[0]} y ${selected.indices[1]}`
      : selected.indices.length ? `Movimientos ${selected.indices.join(", ")}`
      : "Semáforo");
}

function syncInspectorChrome() {
  const runId = studyIdentifier(location.hash);
  const selected = Boolean(inspection && runId && inspection.runId === runId);
  const lab = signalLabOpen();
  element("vehicle-inspector").hidden = !selected || inspectorClosed || lab;
  element("inspector-reopen").hidden = !selected || !inspectorClosed || lab;
}

function rememberInspectionRun(runId) {
  if (inspection && inspection.runId !== runId) {
    inspection = null;
    inspectorClosed = false;
    closeSignalLab();
    syncInspectorChrome();
    geographicMap.highlightVehicle(null);
    geographicMap.highlightSignal(null);
    replayViews.noteSignal(null);
    replayViews.releaseFollow();
  }
}

function currentVehicleIndex() {
  if (!inspection || inspection.kind !== "vehicle") return null;
  const runId = studyIdentifier(location.hash);
  if (!runId || inspection.runId !== runId) return null;
  return inspection.index;
}

function selectVehicle(index) {
  const runId = studyIdentifier(location.hash);
  if (!runId || !Number.isInteger(index) || index < 0) return;
  inspection = { runId, kind: "vehicle", index };
  inspectorClosed = false;
  draw();
}

function currentSignal() {
  if (!inspection || inspection.kind !== "signal") return null;
  const runId = studyIdentifier(location.hash);
  if (!runId || inspection.runId !== runId) return null;
  return inspection;
}

function resolveSignal(target) {
  const indices = Array.isArray(target?.indices)
    ? target.indices.filter(Number.isInteger)
    : (Number.isInteger(target?.index) ? [target.index] : []);
  const byLane = target?.fromLane
    ? signalCatalog.find(item => item.controllerId === target.controllerId && item.fromLane === target.fromLane)
    : null;
  if (byLane) return byLane;
  return signalCatalog.find(item => item.controllerId === target?.controllerId
    && indices.some(index => item.indices.includes(index))) ?? null;
}

function selectSignal(target) {
  const runId = studyIdentifier(location.hash);
  const record = resolveSignal(target);
  if (!runId || !record) return;
  inspection = {
    runId, kind: "signal", controllerId: record.controllerId,
    fromLane: record.fromLane, indices: [...record.indices],
  };
  inspectorClosed = false;
  draw();
}

function clearVehicleSelection() {
  inspection = null;
  inspectorClosed = false;
  closeSignalLab();
  syncInspectorChrome();
  geographicMap.highlightVehicle(null);
  geographicMap.highlightSignal(null);
  replayViews.noteSignal(null);
  draw();
}

function dismissInspector() {
  if (!inspection) return;
  inspectorClosed = true;
  syncInspectorChrome();
}

function reopenInspector() {
  if (!inspection) return;
  inspectorClosed = false;
  draw();
}

function showInspectorKind(signal) {
  element("inspector-speed-row").hidden = signal;
  element("inspector-size-row").hidden = signal;
  element("inspector-observed").hidden = !signal;
  element("inspector-upcoming").hidden = !signal;
  element("inspector-type-row").hidden = signal;
  element("signal-lab-open").hidden = !signal;
  element("inspector-id-label").textContent = signal ? "Controlador SUMO" : "Identificador SUMO";
}

function signalProvenance(controllerId) {
  const item = sectorForStudy(scenario)?.signals?.find(entry => entry.id === controllerId);
  if (item?.program === "inferred") return "Inferida";
  if (item?.program === "validated") return "Validada";
  return "Desconocida";
}

function updateSignalInspector(sumoTime) {
  const panel = element("vehicle-inspector");
  const selected = currentSignal();
  if (!selected || !scenario?.geographic) {
    syncInspectorChrome();
    return;
  }
  showInspectorKind(true);
  const timeline = scenario.signalReplay?.states?.[selected.controllerId] ?? [];
  const current = timeline.findLast(([at]) => at <= sumoTime)?.[1] ?? "";
  const upcoming = timeline.find(([at, state]) => at > sumoTime
    && selected.indices.some(index => (state?.[index] ?? "") !== (current[index] ?? "")));
  const provenance = signalProvenance(selected.controllerId);
  panel.dataset.presence = "signal";
  element("vehicle-presence").textContent = "Semáforo";
  element("vehicle-title").textContent = signalTitle(selected);
  element("vehicle-kicker").textContent = `Procedencia ${provenance.toLowerCase()}`;
  element("vehicle-sumo").textContent = textOrMissing(selected.controllerId);
  element("vehicle-lane").textContent = textOrMissing(selected.fromLane);
  element("vehicle-time").textContent = `${vehicleMeasure.format(sumoTime)} s`;
  fillAspects(element("vehicle-observed"), current, selected.indices);
  element("vehicle-upcoming").textContent = upcoming ? `A los ${vehicleMeasure.format(upcoming[0])} s` : "Sin dato";
  if (upcoming) fillAspects(element("vehicle-upcoming-states"), upcoming[1], selected.indices);
  else element("vehicle-upcoming-states").replaceChildren();
  if (signalLabOpen() && signalLab?.controllerId !== selected.controllerId) closeSignalLab();
  syncInspectorChrome();
}

function textOrMissing(value) {
  return value == null || value === "" ? "Sin dato" : String(value);
}

function nominalSize(type) {
  if (!type || !Number.isFinite(type.length) || !Number.isFinite(type.width)) return "Sin dato";
  return `${vehicleMeasure.format(type.length)} × ${vehicleMeasure.format(type.width)} m`;
}

function updateVehicleInspector(rendered, sumoTime, sampleTime, recordedCars) {
  if (signalLabOpen()) closeSignalLab();
  const panel = element("vehicle-inspector");
  const index = currentVehicleIndex();
  if (index == null || !scenario?.geographic) {
    if (!currentSignal()) syncInspectorChrome();
    return null;
  }
  showInspectorKind(false);
  const record = scenario.vehicleIndex?.[index];
  const typeId = record?.type;
  const type = typeId ? scenario.vehicleTypes?.[typeId] : null;
  const present = rendered.find(car => car[0] === index) ?? null;
  const recorded = recordedCars.find(car => car[0] === index);
  const friendlyType = typeLabel(typeId);
  element("vehicle-title").textContent = humanizeIdentifier(record?.sumoId) || friendlyType;
  element("vehicle-kicker").textContent = friendlyType;
  element("vehicle-sumo").textContent = textOrMissing(record?.sumoId);
  element("vehicle-kind").textContent = textOrMissing(typeId);
  element("vehicle-size").textContent = nominalSize(type);
  element("vehicle-time").textContent = `${vehicleMeasure.format(sumoTime)} s`;
  if (!present) {
    panel.dataset.presence = "off";
    element("vehicle-presence").textContent = "No activo";
    element("vehicle-speed").textContent = "Sin dato";
    element("vehicle-sample").textContent = "Sin dato";
    element("vehicle-lane").textContent = "Sin dato";
    syncInspectorChrome();
    return null;
  }
  const speed = Number.isFinite(recorded?.[4]) ? recorded[4] : present[4];
  const lane = typeof recorded?.[6] === "string" && recorded[6] ? recorded[6] : null;
  const moving = Number.isFinite(speed) && speed >= .1;
  panel.dataset.presence = !Number.isFinite(speed) ? "off" : moving ? "on" : "idle";
  element("vehicle-presence").textContent = !Number.isFinite(speed) ? "Sin dato" : moving ? "Circulando" : "Detenido";
  element("vehicle-speed").textContent = Number.isFinite(speed) ? `${vehicleMeasure.format(speed * 3.6)} km/h` : "Sin dato";
  element("vehicle-sample").textContent = Number.isFinite(speed) ? `Muestra ${vehicleMeasure.format(sampleTime)} s` : "Sin dato";
  element("vehicle-lane").textContent = textOrMissing(lane);
  syncInspectorChrome();
  return present;
}

function typeLabel(typeId) {
  return vehicleTypeNames[typeId] || "Vehículo";
}

function draw() {
  if (simulation.hidden || !scenario) return;
  const time = firstTime + currentTime;
  const index = getFrameIndex(time);
  const [signals, remaining] = cycle ? phaseAt(time) : [{}];
  const cars = interpolate(index, time);
  if (scenario.geographic) {
    const snapshot = frames[index][1];
    const rendered = replayViews.active && replayQa.raw && laneMotion ? snapshot.map(laneMotion.sample) : cars;
    const signal = currentSignal();
    const marked = signal ? null : updateVehicleInspector(rendered, time, frames[index][0], snapshot);
    if (signal) updateSignalInspector(time);
    replayViews.noteSelection(currentVehicleIndex(), Boolean(marked));
    replayViews.noteSignal(signal);
    if (!replayViews.draw(rendered, highlight.checked, time, snapshot, marked)) {
      geographicMap.drawVehicles(replayQa.raw ? frames[index][1] : cars, highlight.checked, running);
      geographicMap.drawSignals(time);
    }
    geographicMap.highlightVehicle(marked ? currentVehicleIndex() : null);
    geographicMap.highlightSignal(signal);
    replayQa.updateStatus(cars, replayViews.outside);
  } else trafficMap.draw(cars, signals, highlight.checked);
  if (index !== lastFrame) {
    updateMetrics(frames[index][1]);
    lastFrame = index;
  }
  if (cycle) updatePhase(signals, remaining);
  if (running || Number(timeline.value) !== currentTime) timeline.value = currentTime;
  element("elapsed").textContent = formatTime(currentTime);
  timeline.setAttribute("aria-valuetext", formatTime(currentTime));
}

function setRunning(value) {
  running = value;
  lastTick = null;
  cancelAnimationFrame(animation);
  if (value) animation = requestAnimationFrame(tick);
  element("play-label").textContent = value ? "Pausar" : "Reproducir";
  element("play-icon").textContent = value ? "Ⅱ" : "▶";
}

function tick(timestamp) {
  if (lastTick !== null) {
    const seconds = Math.min(.1, (timestamp - lastTick) / 1000);
    currentTime = Math.min(duration, currentTime + seconds * Number(element("speed").value));
  }
  lastTick = timestamp;
  draw();
  if (currentTime >= duration) setRunning(false);
  else animation = requestAnimationFrame(tick);
}

function setView(view) {
  simulation.hidden = view !== "simulador";
  mapSection.hidden = view !== "maldonado";
  element("mapa").hidden = view !== "mapa";
  librarySection.hidden = view !== "estudios";
  comparisonSection.hidden = view !== "comparacion";
  element("proyecto").hidden = view !== "proyecto";
  element("ejemplos").hidden = view !== "ejemplos";
  element("decision").hidden = view !== "decision";
  element("novillo").hidden = view !== "novillo";
  document.body.classList.toggle("explorer", view === "mapa");
  document.body.classList.toggle("review", view === "decision");
  document.body.classList.toggle("case-stage", view === "novillo");
  document.body.classList.toggle("studio", view === "simulador" && !document.body.classList.contains("probar"));
  const replay = view === "simulador" && studyIdentifier(location.hash);
  const preparedReplay = replay && new URLSearchParams(location.search).get("probar") === "1";
  if (!preparedReplay) {
    document.body.classList.remove("probar");
    document.body.classList.remove("probar-details");
  }
  const currentRun = element("current-run");
  currentRun.hidden = !replay;
  if (replay) currentRun.href = location.hash;
  const activeNavigation = replay ? "simulador"
    : view === "mapa" || view === "novillo" ? "mapa"
    : view === "decision" || view === "comparacion" ? "comparaciones"
    : "estudios";
  for (const link of document.querySelectorAll("[data-view]")) {
    if (link.dataset.view === activeNavigation) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

function studyIdentifier(hash) {
  return /^#estudio\/([a-f0-9]{32})(?:\?t=\d+(?:\.\d+)?)?$/.exec(hash)?.[1];
}

function previewCue(rows, demo) {
  if (demo) {
    let best = null;
    for (const [time, cars] of rows) {
      const moving = cars.filter(car => {
        const way = String(car[6] ?? "").replace(/^-/, "").split("#")[0];
        return car[4] >= demo.minSpeed && demo.ways.includes(way)
          && car[1] >= demo.west && car[1] <= demo.east
          && car[2] >= demo.south && car[2] <= demo.north;
      });
      if (!moving.length) continue;
      const lead = moving.reduce((fastest, car) => car[4] > fastest[4] ? car : fastest);
      if (!best || moving.length > best.count) best = { time, id: lead[0], count: moving.length };
    }
    if (best) return best;
  }
  let best = null;
  for (const [time, cars] of rows) {
    const moving = cars.filter(car => car[4] >= 6);
    if (moving.length < 3) continue;
    const lead = moving.reduce((fastest, car) => car[4] > fastest[4] ? car : fastest);
    if (!best || moving.length > best.count) best = { time, id: lead[0], count: moving.length };
    if (moving.length >= 6) break;
  }
  return best;
}

function describeAnalysis(data) {
  const sector = sectorForStudy(data);
  element("analysis-name").textContent = data.title || "Simulación";
  element("analysis-state").textContent = sector?.data?.fieldValidated === false
    ? "Simulación validada técnicamente, sin calibración municipal."
    : "Reproducción de la corrida guardada.";
  const trips = Number(data.trips);
  const seconds = Number(data.seconds);
  element("analysis-summary").textContent = Number.isFinite(trips) && Number.isFinite(seconds)
    ? `${trips} viajes publicados en ${Math.round(seconds / 60)} min. No es tránsito en tiempo real.`
    : "Reproducción de la corrida guardada. No es tránsito en tiempo real.";
}

let decisionReturn = "#ejemplos";

async function showView() {
  const version = ++viewVersion;
  const fromHash = decisionReturn;
  decisionReturn = location.hash || "#ejemplos";
  try { await loadSectorCatalog(); } catch { /* the study view reports a missing catalog */ }
  if (version !== viewVersion) return;
  const hash = location.hash;
  if (!hash) {
    location.replace("#mapa");
    return;
  }
  const identifier = studyIdentifier(hash);
  rememberInspectionRun(identifier ?? null);
  const project = /^#proyecto\/([a-f0-9]{32})$/.exec(hash)?.[1];
  const comparison = /^#comparar\/([a-f0-9]{32})\/([a-f0-9]{32})$/.exec(hash);
  const showPilot = Boolean(sectorForHash(hash).sector?.schematic);
  routeFeedback.hidden = true;
  replayViews.configure(null);
  replayQa.configure(null);
  geographicMap.hide();
  setRunning(false);
  if (project) {
    setView("proyecto");
    element("project-title").focus({ preventScroll: true });
    window.scrollTo(0, 0);
    await showProject(project, version);
    return;
  }
  if (comparison) {
    setView("comparacion");
    const back = element("comparison-back");
    const fromProject = comparison.slice(1).every(id => lastOpenedProject?.runs.some(run => run.id === id));
    back.href = fromProject ? `#proyecto/${lastOpenedProject.id}` : "#estudios";
    back.textContent = fromProject ? "Volver al estudio" : "Volver a Estudios";
    element("comparison-title").focus({ preventScroll: true });
    window.scrollTo(0, 0);
    await showComparison(comparison[1], comparison[2], version);
    return;
  }
  if (hash === "#decision-ab") {
    document.body.classList.remove("probar");
    setView("decision");
    const back = element("decision-back");
    const returnToStudy = studyIdentifier(fromHash);
    const returnToExamples = fromHash === "#ejemplos";
    back.hidden = !returnToStudy && !returnToExamples;
    back.href = returnToStudy ? fromHash : "#ejemplos";
    back.textContent = returnToStudy ? "Volver a la demostración" : "Volver a Ejemplos";
    element("decision-title").focus({ preventScroll: true });
    window.scrollTo(0, 0);
    await showDecision(version);
    return;
  }
  if (hash === "#mapa") {
    if (location.search) history.replaceState(null, "", `${location.pathname}#mapa`);
    setView("mapa");
    element("mapa-title").focus({ preventScroll: true });
    window.scrollTo(0, 0);
    await showTerritory(geographicMap, () => version === viewVersion);
    return;
  }
  if (hash === "#novillo") {
    document.body.classList.remove("probar");
    setView("novillo");
    element("novillo-title").focus({ preventScroll: true });
    window.scrollTo(0, 0);
    await showNovillo();
    return;
  }
  if (identifier) {
    trafficFields.disabled = true;
    const search = new URLSearchParams(location.search);
    const probar = search.get("probar") === "1";
    if (probar) {
      document.body.classList.add("probar");
      setView("simulador");
    }
    try {
      routeFeedback.textContent = "Abriendo el estudio guardado…";
      routeFeedback.hidden = false;
      const data = await studyRequest(`/${identifier}/replay`);
      if (version !== viewVersion) return;
      routeFeedback.hidden = !data.legacyCrossingControl;
      if (data.legacyCrossingControl) {
        const sector = sectorForStudy(data);
        routeFeedback.textContent = sector?.messages?.legacyControl
          || "Esta corrida usa un control semafórico anterior. Creá un estudio nuevo para simular el cruce corregido.";
      }
      setView("simulador");
      const back = element("return-to-project");
      const projectId = data.projectId || (lastOpenedProject?.runs.some(run => run.id === identifier) ? lastOpenedProject.id : null);
      back.hidden = !projectId;
      if (projectId) back.href = `#proyecto/${projectId}`;
      element("demo-map-frame").hidden = true;
      element("study-map-host").hidden = false;
      geographicMap.showStudy(data);
      loadScenario(data);
      replayViews.configure(data, identifier);
      const qaRequested = (search.get("qa") === "1" || probar) && data.geographic;
      const qaLoad = qaRequested ? replayQa.load(data, identifier, () => version === viewVersion) : null;
      if (probar && qaLoad) await qaLoad;
      const peakTime = Number(hash.split("?t=")[1]);
      if (Number.isFinite(peakTime)) currentTime = Math.max(0, Math.min(duration, peakTime - firstTime));
      draw();
      requestAnimationFrame(() => geographicMap.resize());
      if (probar && version === viewVersion && data.geographic) {
        describeAnalysis(data);
        element("probar-details").hidden = false;
        element("decision-demo-link").hidden = sectorForStudy(data)?.scene !== "pilot";
        element("speed").value = "1";
        const connectionLayer = document.querySelector("[data-qa-layer=connections]");
        if (connectionLayer?.checked) connectionLayer.click();
        let demo = null;
        try {
          const prepared = await prepareStudySector(data);
          demo = prepared?.demo ?? null;
        } catch { demo = null; }
        const cue = previewCue(frames, demo);
        if (!cue) {
          routeFeedback.textContent = "La corrida no tiene un vehículo en movimiento para el arranque.";
          routeFeedback.hidden = false;
        } else {
          currentTime = Math.max(0, Math.min(duration, cue.time - firstTime));
          const opened = await replayViews.openPreview(cue.id);
          if (version !== viewVersion) return;
          if (opened) setRunning(true);
        }
      }
      window.scrollTo(0, 0);
    } catch (error) {
      if (version !== viewVersion) return;
      document.body.classList.remove("probar");
      setView("estudios");
      routeFeedback.textContent = error.message;
      routeFeedback.hidden = false;
      showSavedStudies();
      window.scrollTo(0, 0);
    }
    return;
  }
  const showSimulation = showPilot || hash === "#simulador";
  const view = showSimulation ? "simulador" : hash === "#maldonado" ? "maldonado" : hash === "#ejemplos" ? "ejemplos" : "estudios";
  setView(view);
  element("demo-map-frame").hidden = false;
  element("study-map-host").hidden = true;
  if (showSimulation) {
    element("return-to-project").hidden = true;
    loadScenario(showPilot ? pilotScenario : window.urbanflowScenario);
    draw();
  } else if (view === "maldonado") {
    geographicMap.showPicker(selectedJunction);
    element("maldonado-title").focus({ preventScroll: true });
  } else if (view === "estudios") {
    showSavedStudies();
  } else {
    element("examples-title").focus({ preventScroll: true });
  }
  window.scrollTo(0, 0);
}

element("probar-details").addEventListener("click", () => {
  const open = document.body.classList.toggle("probar-details");
  const details = element("probar-details");
  details.textContent = open ? "Ocultar detalles" : "Detalles técnicos";
  details.setAttribute("aria-pressed", String(open));
  const signals = document.querySelector("[data-qa-layer=signals]");
  replayViews.setApproachMarkers(open && Boolean(signals?.checked));
});
element("play").addEventListener("click", () => {
  if (!running && currentTime >= duration) currentTime = 0;
  setRunning(!running);
});
element("reset").addEventListener("click", () => {
  setRunning(false);
  currentTime = 0;
  draw();
});
timeline.addEventListener("input", () => {
  currentTime = Number(timeline.value);
  draw();
});
highlight.addEventListener("change", () => {
  element("stopped-legend").hidden = !highlight.checked;
  element("study-stopped-legend").hidden = !highlight.checked;
  draw();
});
for (const [id, amount] of [["sim-in", .25], ["sim-out", -.25], ["sim-center", 0]]) {
  element(id).addEventListener("click", () => {
    const zoom = trafficMap.changeZoom(amount);
    element("sim-in").disabled = zoom === 1.85;
    element("sim-out").disabled = zoom === .7;
    draw();
  });
}
bindJunctionPicker();
element("study-search").addEventListener("input", renderStudyList);
element("project-run").addEventListener("click", startProjectRun);
const comparisonB = element("comparison-b");
for (const id of ["comparison-a", "comparison-b"]) {
  element(id).addEventListener("change", () => comparisonB.setCustomValidity(""));
}
element("comparison-form").addEventListener("submit", event => {
  event.preventDefault();
  const first = element("comparison-a").value;
  const second = comparisonB.value;
  if (first === second) {
    comparisonB.setCustomValidity("Elegí dos corridas distintas.");
    comparisonB.reportValidity();
    return;
  }
  location.hash = comparisonHash(first, second);
});
element("show-summary").addEventListener("click", () => showInspectorPanel(false));
element("edit-traffic").addEventListener("click", () => showInspectorPanel(true));
element("traffic-movements").addEventListener("input", updateTrafficTotal);
trafficSource.addEventListener("change", updateTrafficSource);
trafficMixedFleet.addEventListener("change", updateTrafficTotal);
element("traffic-upload").addEventListener("click", () => trafficFile.click());
trafficFile.addEventListener("change", applyTrafficFile);
trafficForm.addEventListener("submit", saveTraffic);
element("traffic-template").addEventListener("click", () => {
  const csv = trafficCsvTemplate(scenario.traffic.movements);
  const url = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "urbanflow-conteos.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
new ResizeObserver(draw).observe(canvas);
element("close-urbanflow").addEventListener("click", async () => {
  if (!window.confirm("¿Cerrar UrbanFlow en esta computadora?")) return;
  const button = element("close-urbanflow");
  const note = element("close-urbanflow-note");
  button.disabled = true;
  try {
    const health = await fetch("/api/health", { cache: "no-store", headers: { Accept: "application/json" } });
    const data = await health.json();
    if (!data.controlToken) throw new Error("Esta sesión no admite el cierre desde la aplicación.");
    const response = await fetch("/api/shutdown", {
      method: "POST",
      headers: { "X-UrbanFlow-Token": data.controlToken },
    });
    if (!response.ok) throw new Error("No se pudo cerrar UrbanFlow.");
    note.textContent = "UrbanFlow se cerró. Ya podés cerrar esta pestaña.";
  } catch (error) {
    button.disabled = false;
    note.textContent = error.message || "No se pudo cerrar UrbanFlow.";
  }
});
const signalLabFields = {
  duration: "Duración", minDur: "Mínimo", maxDur: "Máximo", earliestEnd: "Fin más temprano",
  latestEnd: "Fin más tardío", yellow: "Amarillo", red: "Rojo", vehext: "Extensión", offset: "Desfase",
};

function signalLabOpen() {
  const lab = element("signal-lab");
  return Boolean(lab && !lab.hidden);
}

function closeSignalLab() {
  window.clearTimeout(signalLabPoll);
  if (!signalLabOpen()) {
    signalLab = null;
    return;
  }
  element("signal-lab").hidden = true;
  signalLab = null;
  syncInspectorChrome();
}

function formatLabDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "";
  return new Intl.DateTimeFormat("es-UY", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function signalLabField(label, value, original, editable, phase, field) {
  const row = document.createElement("div");
  row.className = "signal-lab-field";
  const name = document.createElement("span");
  const changed = String(value) !== String(original);
  name.textContent = editable
    ? `${label} · publicado ${original} s`
    : changed ? `${label} ${value} s · publicado ${original} s` : `${label} ${value} s`;
  row.append(name);
  if (!editable) return row;
  const input = document.createElement("input");
  input.type = "text";
  input.inputMode = "decimal";
  input.value = value;
  input.dataset.field = field;
  if (phase != null) input.dataset.phase = String(phase);
  input.setAttribute("aria-label", `${label} de la variante`);
  input.addEventListener("input", () => {
    input.dataset.changed = input.value.trim() !== String(original) ? "true" : "false";
  });
  if (String(value) !== String(original)) input.dataset.changed = "true";
  row.append(input);
  return row;
}

function signalLabProgram(description, program, editable) {
  const nodes = [];
  program.phases.forEach((phase, index) => {
    const block = document.createElement("article");
    block.className = "signal-lab-phase";
    const title = document.createElement("h4");
    title.textContent = `Fase ${index + 1} · ${phase.state}`;
    block.append(title);
    Object.keys(phase).forEach(field => {
      if (!signalLabFields[field]) return;
      const canEdit = editable && description.editableFields.some(item => item.phase === index && item.field === field);
      block.append(signalLabField(signalLabFields[field], phase[field], description.program.phases[index][field], canEdit, index, field));
    });
    nodes.push(block);
  });
  if (description.editableFields.some(item => item.phase == null && item.field === "offset")) {
    nodes.push(signalLabField("Desfase", program.offset, description.program.offset, editable, null, "offset"));
  }
  return nodes;
}

function signalLabState(variant) {
  const comparison = variant?.execution?.comparison;
  if (variant?.status === "finalizado" && comparison && comparison.available === false) return "Comparación no disponible";
  return {
    "borrador experimental": "Borrador",
    ejecutando: "Ejecutando",
    finalizado: "Finalizado",
    error: "Error",
  }[variant?.status] || "";
}

function labNumber(value, digits = 0) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("es-UY", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

function labDelta(item, digits) {
  if (item.absolute == null) return "—";
  const absolute = `${item.absolute > 0 ? "+" : ""}${labNumber(item.absolute, digits)}`;
  if (item.percent == null) return absolute;
  return `${absolute} · ${item.percent > 0 ? "+" : ""}${labNumber(item.percent, 1)} %`;
}

function signalLabMetrics(comparison) {
  const table = document.createElement("table");
  table.className = "signal-lab-metrics";
  const head = document.createElement("tr");
  ["Indicador", "Control", "Variante", "Diferencia"].forEach(text => {
    const cell = document.createElement("th");
    cell.textContent = text;
    head.append(cell);
  });
  table.append(head);
  ["completed", "meanTravelSeconds", "meanWaitSeconds"].forEach(key => {
    const item = comparison.indicators[key];
    const digits = key === "completed" ? 0 : 2;
    const row = document.createElement("tr");
    [item.label, labNumber(item.control, digits), labNumber(item.variant, digits), labDelta(item, digits)].forEach(text => {
      const cell = document.createElement("td");
      cell.textContent = text;
      row.append(cell);
    });
    table.append(row);
  });
  return table;
}

function signalLabTechnical(execution) {
  const details = document.createElement("details");
  details.id = "signal-lab-technical";
  details.className = "signal-lab-technical";
  const summary = document.createElement("summary");
  summary.textContent = "Resultados técnicos";
  details.append(summary);
  if (execution.comparison?.summary) {
    const text = document.createElement("p");
    text.className = "signal-lab-summary";
    text.textContent = execution.comparison.summary;
    details.append(text);
  }
  const buttons = signalLabReplayButtons(execution);
  if (buttons) details.append(buttons);
  const list = document.createElement("dl");
  const rows = [
    ["SUMO", execution.sumoVersion],
    ["Activación", `${execution.activation || ""} · programa ${execution.loadedProgramID || ""}`],
    ["Programa adicional", execution.variantRun?.programSha256],
    ["Fases del control", (execution.evidence?.controlPhaseSeconds || []).join(", ")],
    ["Fases de la variante", (execution.evidence?.variantPhaseSeconds || []).join(", ")],
    ["Sin completar", execution.comparison?.incomplete ? `${execution.comparison.incomplete.control} · ${execution.comparison.incomplete.variant}` : ""],
    ["Despeje", execution.comparison?.clearanceSeconds ? `${execution.comparison.clearanceSeconds.control ?? "—"} s · ${execution.comparison.clearanceSeconds.variant ?? "—"} s` : ""],
    ["Viajes publicados", execution.publishedReproduction?.note],
    ["Control", execution.control?.directory],
    ["Variante", execution.variantRun?.directory],
  ];
  rows.forEach(([name, value]) => {
    if (!value) return;
    const row = document.createElement("div");
    const term = document.createElement("dt");
    term.textContent = name;
    const data = document.createElement("dd");
    data.textContent = String(value);
    row.append(term, data);
    list.append(row);
  });
  details.append(list);
  return details;
}

function signalLabReplayButtons(execution) {
  const row = document.createElement("div");
  row.className = "signal-lab-actions";
  [["control", "Abrir control"], ["variant", "Abrir variante experimental"]].forEach(([role, label]) => {
    if (!execution.replays?.[role]) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button-secondary";
    button.textContent = label;
    button.addEventListener("click", () => openExperimentalReplay(role));
    row.append(button);
  });
  return row.childElementCount ? row : null;
}

function renderSignalResults(execution) {
  const host = element("signal-lab-results");
  host.replaceChildren();
  const comparison = execution?.comparison;
  const status = signalLab?.variant?.status;
  const published = status === "finalizado" && execution?.resultsValid && comparison?.available && comparison.indicators;
  const withheld = status === "finalizado" && comparison?.available === false;
  host.hidden = !(published || withheld);
  if (!published && !withheld) return;
  if (published) {
    const identity = document.createElement("p");
    identity.className = "signal-lab-summary";
    identity.textContent = `Controlador ${signalLab.controllerId}.`;
    host.append(identity);
    host.append(signalLabMetrics(comparison));
    (execution.differences || []).filter(row => row.phase != null).forEach(change => {
      const line = document.createElement("p");
      line.className = "signal-lab-summary";
      line.textContent = `La fase ${change.phase + 1} pasó de ${change.original} s a ${change.proposed} s.`;
      host.append(line);
    });
    const conditions = document.createElement("p");
    conditions.className = "signal-lab-summary";
    const horizon = comparison.horizonSeconds;
    conditions.textContent = horizon == null
      ? "Misma red, rutas, demanda y semilla."
      : `Misma red, rutas, demanda y semilla. Horizonte ${horizon} s.`;
    host.append(conditions);
  } else if (comparison?.reason) {
    const text = document.createElement("p");
    text.className = "signal-lab-summary";
    text.textContent = comparison.reason;
    host.append(text);
  }
  host.append(signalLabTechnical(execution));
}

function renderSignalLab(message = "") {
  const { program, variant } = signalLab;
  const defining = (program.sources || []).filter(item => item.definesProgram).map(item => item.file);
  const controller = signalLab.controllerId ? ` Controlador ${signalLab.controllerId}.` : "";
  const running = variant?.status === "ejecutando";
  const finished = variant?.status === "finalizado";
  const editable = Boolean(variant) && !running && !finished;
  element("signal-lab").classList.toggle("signal-lab-settled", Boolean(
    finished && variant?.execution?.resultsValid && variant.execution.comparison?.available));
  element("signal-lab-source").textContent = program.program
    ? `Procedencia ${program.provenanceLabel.toLowerCase()} · ${defining.join(", ") || "sin programa"} · programa ${program.program.programID} · ${program.program.type}.${controller}`
    : `Procedencia ${program.provenanceLabel.toLowerCase()}. Se revisó ${(program.sources || []).map(item => item.file).join(", ") || "ningún archivo"}.${controller}`;
  element("signal-lab-error").textContent = variant?.status === "error" ? (variant.execution?.error || "") : "";
  element("signal-lab-note").textContent = message || (running
    ? "Ejecutando la variante en SUMO. La reproducción publicada sigue igual."
    : finished ? "La reproducción publicada no cambió." : variant?.contract?.summary || "");
  const state = signalLabState(variant);
  element("signal-lab-status").hidden = !state;
  element("signal-lab-status").textContent = state;
  element("signal-lab-block").hidden = program.editable;
  element("signal-lab-block").textContent = program.editable ? "" : (program.reason || "");
  element("signal-lab-body").hidden = !program.editable;
  element("signal-lab-body").classList.toggle("split", Boolean(variant));
  element("signal-lab-variant-column").hidden = !variant;
  element("signal-lab-create").hidden = !program.editable;
  element("signal-lab-create").disabled = running;
  element("signal-lab-create").textContent = variant ? "Crear otra variante" : "Crear variante experimental";
  element("signal-lab-save").hidden = !editable;
  element("signal-lab-save").disabled = false;
  element("signal-lab-reset").hidden = !editable;
  element("signal-lab-reset").disabled = false;
  element("signal-lab-execute").hidden = !variant;
  element("signal-lab-execute").disabled = running || finished || !program.editable;
  element("signal-lab-execute").textContent = running ? "Ejecutando…" : finished ? "Variante ejecutada" : "Ejecutar variante";
  element("signal-lab-draft").textContent = variant
    ? `${signalLabState(variant) || "Borrador"} · ${formatLabDate(variant.updatedAt)}`
    : "";
  const base = program.program ? signalLabProgram(program, program.program, false) : [];
  const proposed = variant ? signalLabProgram(program, variant.proposed, editable) : [];
  if (finished && variant?.execution?.resultsValid && variant.execution.comparison?.available) {
    base.unshift(signalLabResultLine(variant.execution, "control"));
    proposed.unshift(signalLabResultLine(variant.execution, "variant"));
  }
  element("signal-lab-base").replaceChildren(...base);
  element("signal-lab-proposed").replaceChildren(...proposed);
  renderSignalResults(variant?.execution);
}

function signalLabResultLine(execution, side) {
  const indicators = execution.comparison.indicators;
  const line = document.createElement("p");
  line.className = "signal-lab-result-line";
  line.textContent = `${labNumber(indicators.completed[side])} completados · viaje ${labNumber(indicators.meanTravelSeconds[side], 2)} s · espera ${labNumber(indicators.meanWaitSeconds[side], 2)} s`;
  return line;
}

async function openSignalLab() {
  const selected = currentSignal();
  const runId = studyIdentifier(location.hash);
  if (!selected || !runId) return;
  element("signal-lab").hidden = false;
  element("signal-lab").classList.remove("signal-lab-settled");
  element("signal-lab-body").hidden = true;
  element("signal-lab-block").hidden = true;
  element("signal-lab-create").hidden = true;
  element("signal-lab-save").hidden = true;
  element("signal-lab-reset").hidden = true;
  element("signal-lab-execute").hidden = true;
  element("signal-lab-results").hidden = true;
  element("signal-lab-status").hidden = true;
  element("signal-lab-error").textContent = "";
  element("signal-lab-note").textContent = "Leyendo el programa SUMO…";
  signalLab = null;
  syncInspectorChrome();
  try {
    const program = await apiRequest(`/api/studies/${runId}/signal-program?controller=${encodeURIComponent(selected.controllerId)}`);
    const listed = program.editable
      ? await apiRequest(`/api/studies/${runId}/signal-variants?controller=${encodeURIComponent(selected.controllerId)}`)
      : { variants: [] };
    const newest = listed.variants?.[0];
    const variant = newest ? await apiRequest(`/api/signal-variants/${newest.id}`) : null;
    if (!signalLabOpen() || currentSignal()?.controllerId !== selected.controllerId) return;
    signalLab = { runId, controllerId: selected.controllerId, program, variant };
    renderSignalLab();
    if (variant?.status === "ejecutando") watchSignalRun();
  } catch (error) {
    if (!signalLabOpen()) return;
    element("signal-lab-note").textContent = "";
    element("signal-lab-error").textContent = error.message || "No se pudo leer la configuración.";
  }
}

function proposedFromForm() {
  const proposed = JSON.parse(JSON.stringify(signalLab.variant.original));
  element("signal-lab-proposed").querySelectorAll("input").forEach(input => {
    const value = input.value.trim();
    if (input.dataset.phase == null) proposed[input.dataset.field] = value;
    else proposed.phases[Number(input.dataset.phase)][input.dataset.field] = value;
  });
  return proposed;
}

async function createSignalVariant() {
  if (!signalLab?.program?.editable) return;
  element("signal-lab-error").textContent = "";
  element("signal-lab-create").disabled = true;
  try {
    signalLab.variant = await apiRequest(`/api/studies/${signalLab.runId}/signal-variants`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ controllerId: signalLab.controllerId }),
    });
    renderSignalLab("Variante experimental creada. La corrida publicada sigue igual.");
  } catch (error) {
    element("signal-lab-error").textContent = error.message || "No se pudo crear la variante.";
  } finally {
    element("signal-lab-create").disabled = false;
  }
}

async function saveSignalVariant() {
  if (!signalLab?.variant) return;
  element("signal-lab-error").textContent = "";
  element("signal-lab-save").disabled = true;
  try {
    signalLab.variant = await apiRequest(`/api/signal-variants/${signalLab.variant.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposed: proposedFromForm() }),
    });
    renderSignalLab("Borrador guardado. La reproducción no cambió.");
  } catch (error) {
    element("signal-lab-error").textContent = error.message || "No se pudo guardar el borrador.";
  } finally {
    element("signal-lab-save").disabled = false;
  }
}

async function resetSignalVariant() {
  if (!signalLab?.variant) return;
  element("signal-lab-error").textContent = "";
  element("signal-lab-reset").disabled = true;
  try {
    signalLab.variant = await apiRequest(`/api/signal-variants/${signalLab.variant.id}/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    renderSignalLab("La variante volvió a los valores publicados.");
  } catch (error) {
    element("signal-lab-error").textContent = error.message || "No se pudo restablecer la variante.";
  } finally {
    element("signal-lab-reset").disabled = false;
  }
}

async function executeSignalVariant() {
  if (!signalLab?.variant || signalLab.variant.status === "ejecutando" || signalLab.variant.status === "finalizado") return;
  element("signal-lab-error").textContent = "";
  element("signal-lab-execute").disabled = true;
  try {
    signalLab.variant = await apiRequest(`/api/signal-variants/${signalLab.variant.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposed: proposedFromForm() }),
    });
    await apiRequest(`/api/signal-variants/${signalLab.variant.id}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    signalLab.variant = await apiRequest(`/api/signal-variants/${signalLab.variant.id}`);
    renderSignalLab();
    watchSignalRun();
  } catch (error) {
    element("signal-lab-error").textContent = error.message || "No se pudo ejecutar la variante.";
    element("signal-lab-execute").disabled = false;
  }
}

function watchSignalRun() {
  window.clearTimeout(signalLabPoll);
  if (!signalLabOpen() || signalLab?.variant?.status !== "ejecutando") return;
  signalLabPoll = window.setTimeout(async () => {
    const current = signalLab?.variant?.id;
    if (!current || !signalLabOpen()) return;
    try {
      const variant = await apiRequest(`/api/signal-variants/${current}`);
      if (!signalLabOpen() || signalLab.variant?.id !== current) return;
      signalLab.variant = variant;
      renderSignalLab();
      if (variant.status === "ejecutando") watchSignalRun();
    } catch (error) {
      element("signal-lab-error").textContent = error.message || "No se pudo leer la ejecución.";
    }
  }, 1000);
}

async function openExperimentalReplay(role) {
  if (!signalLab?.variant) return;
  try {
    const data = await apiRequest(`/api/signal-variants/${signalLab.variant.id}/replay?role=${role}`);
    loadScenario(data);
    draw();
  } catch (error) {
    element("signal-lab-error").textContent = error.message || "No se pudo abrir el replay experimental.";
  }
}

async function returnToPublishedReplay() {
  const identifier = studyIdentifier(location.hash);
  if (!identifier) return;
  const data = await studyRequest(`/${identifier}/replay`);
  loadScenario(data);
  draw();
}

element("signal-lab-open").addEventListener("click", openSignalLab);
element("signal-lab-close").addEventListener("click", closeSignalLab);
element("signal-lab-create").addEventListener("click", createSignalVariant);
element("signal-lab-save").addEventListener("click", saveSignalVariant);
element("signal-lab-reset").addEventListener("click", resetSignalVariant);
element("signal-lab-execute").addEventListener("click", executeSignalVariant);
element("experimental-replay-return").addEventListener("click", returnToPublishedReplay);
element("vehicle-clear").addEventListener("click", clearVehicleSelection);
element("vehicle-dismiss").addEventListener("click", dismissInspector);
element("inspector-reopen").addEventListener("click", reopenInspector);
window.addEventListener("hashchange", showView);
showView();
