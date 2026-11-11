"use strict";

const element = id => document.getElementById(id);
const pilotScenario = window.urbanflowPilot;
const geographicMap = createMaldonadoMap(pilotScenario, onSelection);
const canvas = element("traffic-map");
const timeline = element("timeline");
const highlight = element("highlight");
const simulation = element("simulador");
const mapSection = element("maldonado");
const librarySection = element("estudios");
const studySearch = element("study-search");
const studyButton = element("study-action");
const studyStatus = element("study-status");
const routeFeedback = element("route-feedback");
const trafficEditor = element("traffic-editor");
const trafficForm = element("traffic-form");
const trafficFields = element("traffic-fields");
const trafficDuration = element("traffic-duration");
const trafficSource = element("traffic-source");
const trafficFile = element("traffic-file");
const trafficFeedback = element("traffic-feedback");
const number = new Intl.NumberFormat("es-UY");
const studyDate = new Intl.DateTimeFormat("es-UY", { dateStyle: "short", timeStyle: "short", timeZone: "America/Montevideo" });
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
let selectedPoint;
let selectionVersion = 0;
let generatedStudyId = null;
let viewVersion = 0;
let trafficInputs = new Map();
let savedGroups = [];

function onSelection(point) {
  selectedPoint = { lat: point.lat, lng: point.lng };
  selectionVersion++;
  generatedStudyId = null;
  studyStatus.textContent = "";
  studyButton.textContent = "Estudiar este cruce →";
  studyButton.disabled = false;
  element("selection-instruction").textContent = "UrbanFlow buscará el cruce vehicular más cercano al punto marcado.";
  geographicMap.preview(null);
  studyButton.focus();
}

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
  if (health.app !== "urbanflow" || health.apiVersion !== 3) throw new Error(generatorAddressError);
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
    if (Date.now() >= deadline) throw new Error("La corrida está tardando más de lo esperado. Podés buscarla en Estudios guardados cuando termine.");
    await new Promise(resolve => setTimeout(resolve, 600));
  }
  return false;
}

async function generateSelectedStudy() {
  if (!selectedPoint) return;
  if (generatedStudyId) {
    location.hash = `#estudio/${generatedStudyId}`;
    return;
  }
  const version = selectionVersion;
  const point = selectedPoint;
  const isCurrent = () => version === selectionVersion;
  studyButton.disabled = true;
  studyStatus.textContent = "Preparando el estudio…";
  try {
    await verifyGenerator();
    if (!isCurrent()) return;
    const { id } = await postStudy("", point);
    const ready = await waitForStudy(id, isCurrent, status => {
      studyStatus.textContent = status.target ? `${status.target.title}. ${status.message}` : status.message;
      geographicMap.preview(status.target);
    });
    if (!ready || !isCurrent()) return;
    generatedStudyId = id;
    studyButton.textContent = "Abrir estudio →";
    if (!mapSection.hidden) location.hash = `#estudio/${id}`;
  } catch (error) {
    if (isCurrent()) studyStatus.textContent = error.message;
  } finally {
    if (isCurrent()) studyButton.disabled = false;
  }
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

function renderSavedStudies() {
  const list = element("saved-studies");
  const status = element("saved-status");
  const query = searchable(studySearch.value.trim());
  const groups = savedGroups.filter(({ original, runs }) => searchable(original.title).includes(query)
    || runs.some(run => searchable(run.title).includes(query)));
  list.replaceChildren();
  for (const { original, runs } of groups) {
    const group = document.createElement("li");
    const heading = document.createElement("h2");
    heading.textContent = original.title;
    const entries = document.createElement("ul");
    entries.className = "saved-runs";
    const originalAvailable = !original.parentId;
    group.append(heading);
    if (!originalAvailable) {
      const note = document.createElement("p");
      note.className = "muted";
      note.textContent = "El estudio original ya no está disponible.";
      group.append(note);
    }
    group.append(entries);
    const ordered = originalAvailable ? [original, ...runs.filter(run => run !== original)] : runs;
    for (const saved of ordered) {
      const row = document.createElement("li");
      const label = document.createElement("strong");
      label.textContent = saved.parentId ? "Corrida" : "Estudio original";
      const link = document.createElement("a");
      link.href = `#estudio/${saved.id}`;
      link.className = "button button-secondary";
      link.textContent = "Abrir";
      const details = document.createElement("span");
      details.className = "muted";
      const source = saved.traffic?.source === "observed" ? "Conteos observados" : "Tráfico de muestra";
      const period = saved.traffic?.durationMinutes ? `${saved.traffic.durationMinutes} min` : "";
      const date = new Date(saved.createdAt ?? NaN);
      details.textContent = [source, period, Number.isFinite(saved.trips) ? `${number.format(saved.trips)} viajes` : "",
        Number.isNaN(date.valueOf()) ? "" : studyDate.format(date)].filter(Boolean).join(" · ");
      link.setAttribute("aria-label", `Abrir ${label.textContent.toLowerCase()} de ${original.title}. ${details.textContent}`);
      const info = document.createElement("div");
      info.append(label, details);
      row.append(info, link);
      entries.append(row);
    }
    list.append(group);
  }
  status.textContent = groups.length ? "" : savedGroups.length ? "No encontramos cruces con ese nombre."
    : "Todavía no hay estudios. Elegí un cruce en el mapa para empezar.";
}

async function showSavedStudies() {
  const version = viewVersion;
  const tools = element("library-tools");
  const status = element("saved-status");
  savedGroups = [];
  element("saved-studies").replaceChildren();
  tools.hidden = true;
  if (location.protocol === "file:") {
    status.textContent = "Abrí UrbanFlow desde su servidor local para recuperar tus estudios.";
    return;
  }
  status.textContent = "Cargando estudios…";
  try {
    await verifyGenerator();
    const { studies } = await studyRequest("");
    if (version !== viewVersion) return;
    savedGroups = groupSavedStudies(studies);
    tools.hidden = !savedGroups.length;
    renderSavedStudies();
  } catch (error) {
    if (version === viewVersion) status.textContent = error.message;
  }
}

function showTrafficFeedback(message, error = false) {
  trafficFeedback.textContent = message;
  trafficFeedback.hidden = !message;
  trafficFeedback.dataset.error = String(error);
}

function updateTrafficTotal() {
  const total = [...trafficInputs.values()].reduce((sum, input) => sum + (Number(input.value) || 0), 0);
  element("traffic-total").textContent = `${number.format(total)} vehículos en el período`;
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
  updateTrafficTotal();
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
    updateTrafficTotal();
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
  currentTime = Math.min(scenario.geographic ? 20 : 72, duration);
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
  element("source-credit").hidden = !isPilot && !isGeographic;
  const signals = Object.keys(scenario.signalReplay?.states ?? {}).length;
  element("signal-legend").hidden = !signals;
  const signalNote = element("signal-note");
  signalNote.hidden = !signals;
  signalNote.textContent = `${signals} ${signals === 1 ? "controlador" : "controladores"} en el área. Los colores muestran las fases de SUMO. El violeta indica giros con estados distintos en el mismo carril. Los tiempos son estimados.`;
  const assumptions = element("model-assumptions");
  assumptions.hidden = !isGeographic;
  assumptions.textContent = scenario.assumptions?.join(" ") ?? "";
  element("signal-dot").hidden = !cycle;
  if (!cycle) {
    const roundabout = isPilot || scenario.roundabout;
    element("phase-name").textContent = roundabout ? "Prioridad de la rotonda" : "Control vial importado";
    element("phase-remaining").textContent = roundabout ? "Ceda el paso al ingresar." : "Giros, prioridades y señales de la red de SUMO.";
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
    geographicMap.drawVehicles(cars, highlight.checked, running);
    geographicMap.drawSignals(time);
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
  if (view === "simulador") {
    const currentRun = element("current-run");
    currentRun.href = location.hash;
    currentRun.hidden = false;
  }
  for (const link of document.querySelectorAll("[data-view]")) {
    if (link.dataset.view === view) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

function studyIdentifier(hash) {
  return /^#estudio\/([a-f0-9]{32})$/.exec(hash)?.[1];
}

async function showView() {
  const version = ++viewVersion;
  const hash = location.hash;
  const identifier = studyIdentifier(hash);
  const showPilot = hash === "#estudio-roosevelt-camacho";
  routeFeedback.hidden = true;
  if (identifier) {
    setRunning(false);
    trafficFields.disabled = true;
    try {
      routeFeedback.textContent = "Abriendo el estudio guardado…";
      routeFeedback.hidden = false;
      const data = await studyRequest(`/${identifier}/replay`);
      if (version !== viewVersion) return;
      routeFeedback.hidden = true;
      setView("simulador");
      element("demo-map-frame").hidden = true;
      element("study-map-host").hidden = false;
      geographicMap.showStudy(data);
      loadScenario(data);
      draw();
      window.scrollTo(0, 0);
    } catch (error) {
      if (version !== viewVersion) return;
      setView("estudios");
      geographicMap.restoreSelection();
      routeFeedback.textContent = error.message;
      routeFeedback.hidden = false;
      showSavedStudies();
      window.scrollTo(0, 0);
    }
    return;
  }
  const showSimulation = showPilot || hash === "#simulador";
  const view = showSimulation ? "simulador" : hash === "#estudios" ? "estudios" : "maldonado";
  setView(view);
  geographicMap.restoreSelection();
  element("demo-map-frame").hidden = false;
  element("study-map-host").hidden = true;
  if (showSimulation) {
    loadScenario(showPilot ? pilotScenario : window.urbanflowScenario);
    draw();
  } else {
    setRunning(false);
    if (view === "estudios") showSavedStudies();
    else geographicMap.refresh();
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
studyButton.addEventListener("click", generateSelectedStudy);
studySearch.addEventListener("input", renderSavedStudies);
element("show-summary").addEventListener("click", () => showInspectorPanel(false));
element("edit-traffic").addEventListener("click", () => showInspectorPanel(true));
element("traffic-movements").addEventListener("input", updateTrafficTotal);
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
