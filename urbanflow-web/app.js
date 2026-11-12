"use strict";

const element = id => document.getElementById(id);
const pilotScenario = window.urbanflowPilot;
const geographicMap = createMaldonadoMap(onMapSelection);
const replayViews = createReplayViews(geographicMap, draw);
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
  if (health.app !== "urbanflow" || health.apiVersion !== 10) throw new Error(generatorAddressError);
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
  trafficFleetOption.hidden = scenario.junctionId !== "r1161502532" || trafficSource.value !== "sample";
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
  laneMotion = scenario.laneMotion ? createLaneMotion(scenario.laneMotion) : null;
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
  canvas.setAttribute("aria-label", isPilot
    ? "Vista de la rotonda y los accesos de las avenidas Roosevelt y Antonio Camacho con vehículos simulados"
    : "Vista cenital esquemática de una intersección de cuatro accesos con vehículos y semáforos");
  const sourceBadge = isGeographic || isPilot || scenario.source === "demo" ? "Tráfico de muestra" : "Reproducción SUMO";
  element("source-label").textContent = scenario.traffic?.source === "observed" ? "Conteos observados" : sourceBadge;
  element("source-note").textContent = isGeographic
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
  const [from, cars] = frames[index];
  if (index === frames.length - 1 || time === from) return laneMotion ? cars.map(laneMotion.sample) : cars;
  laneMotion?.beginFrame(cars);
  const [to, upcoming] = frames[index + 1];
  const ratio = (time - from) / (to - from);
  const nextCars = new Map(upcoming.map(car => [car[0], car]));
  return cars.map(car => {
    const [id, x, y, angle, speed, approach] = car;
    const next = nextCars.get(id);
    if (laneMotion) return next ? laneMotion.between(car, next, ratio, to - from) : laneMotion.sample(car);
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

function draw() {
  if (simulation.hidden || !scenario) return;
  const time = firstTime + currentTime;
  const index = getFrameIndex(time);
  const [signals, remaining] = cycle ? phaseAt(time) : [{}];
  const cars = interpolate(index, time);
  if (scenario.geographic) {
    if (!replayViews.draw(cars, highlight.checked, time, frames[index][1])) {
      geographicMap.drawVehicles(cars, highlight.checked, running);
      geographicMap.drawSignals(time);
    }
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
  librarySection.hidden = view !== "estudios";
  comparisonSection.hidden = view !== "comparacion";
  element("proyecto").hidden = view !== "proyecto";
  element("ejemplos").hidden = view !== "ejemplos";
  const replay = view === "simulador" && studyIdentifier(location.hash);
  if (replay) {
    const currentRun = element("current-run");
    currentRun.href = location.hash;
    currentRun.hidden = false;
  }
  const activeNavigation = replay ? "simulador" : view === "simulador" || view === "ejemplos" ? null : "estudios";
  for (const link of document.querySelectorAll("[data-view]")) {
    if (link.dataset.view === activeNavigation) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

function studyIdentifier(hash) {
  return /^#estudio\/([a-f0-9]{32})(?:\?t=\d+(?:\.\d+)?)?$/.exec(hash)?.[1];
}

async function showView() {
  const version = ++viewVersion;
  const hash = location.hash;
  const identifier = studyIdentifier(hash);
  const project = /^#proyecto\/([a-f0-9]{32})$/.exec(hash)?.[1];
  const comparison = /^#comparar\/([a-f0-9]{32})\/([a-f0-9]{32})$/.exec(hash);
  const showPilot = hash === "#estudio-roosevelt-camacho";
  routeFeedback.hidden = true;
  replayViews.configure(null);
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
  if (identifier) {
    trafficFields.disabled = true;
    try {
      routeFeedback.textContent = "Abriendo el estudio guardado…";
      routeFeedback.hidden = false;
      const data = await studyRequest(`/${identifier}/replay`);
      if (version !== viewVersion) return;
      routeFeedback.hidden = true;
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
      const peakTime = Number(hash.split("?t=")[1]);
      if (Number.isFinite(peakTime)) currentTime = Math.max(0, Math.min(duration, peakTime - firstTime));
      draw();
      window.scrollTo(0, 0);
    } catch (error) {
      if (version !== viewVersion) return;
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
element("examples-link").addEventListener("click", () => { element("help-menu").open = false; });
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
window.addEventListener("hashchange", showView);
showView();
