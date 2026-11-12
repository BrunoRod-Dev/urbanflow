"use strict";

let selectedJunction = null;
let junctionRequest = 0;
let savingJunction = false;
let studyGroups = [];
let lastOpenedProject = null;

function setJunctionPreview(target) {
  selectedJunction = target;
  element("selection").hidden = !target;
  geographicMap.preview(target);
  if (!target) return;
  element("selected-type").textContent = target.roundabout ? "Rotonda" : "Intersección";
  element("selected-junction").textContent = target.title;
  renderAccesses(element("selected-accesses"), target.accesses);
}

function renderAccesses(list, names) {
  list.replaceChildren();
  for (const name of names ?? []) {
    const item = document.createElement("li");
    item.textContent = name;
    list.append(item);
  }
}

async function loadJunctionOptions(params, fromMap = false) {
  if (savingJunction || mapSection.hidden) return;
  const request = ++junctionRequest;
  const version = viewVersion;
  const status = element("junction-feedback");
  const list = element("junction-options");
  setJunctionPreview(null);
  list.replaceChildren();
  list.hidden = true;
  status.textContent = "Buscando cruces…";
  try {
    const { candidates, more } = await apiRequest(`/api/junctions?${params}`);
    if (request !== junctionRequest || version !== viewVersion) return;
    if (!candidates.length) {
      status.textContent = fromMap ? "No encontramos un cruce vehicular cerca. Acercá el mapa y hacé clic en la unión entre dos calles."
        : "No encontramos cruces con ese nombre. Probá con una sola calle o elegí un lugar en el mapa.";
      return;
    }
    if (candidates.length === 1) {
      setJunctionPreview(candidates[0]);
      status.textContent = "Encontramos un cruce. Revisá los accesos y el área.";
      if (!fromMap) element("study-action").focus();
      return;
    }
    status.textContent = more ? "Hay más coincidencias. Agregá otra calle para acotar la búsqueda."
      : fromMap ? "Hay varios cruces cerca. Revisá las opciones." : "Elegí un cruce de la lista para revisar el área.";
    for (const target of candidates) {
      const item = document.createElement("li");
      const option = document.createElement("button");
      option.type = "button";
      option.dataset.junctionId = target.junctionId;
      option.textContent = target.title;
      option.setAttribute("aria-pressed", "false");
      if (Number.isFinite(target.distanceMeters)) {
        const distance = document.createElement("span");
        distance.textContent = `${target.distanceMeters} m del punto`;
        option.append(distance);
      }
      option.addEventListener("click", () => {
        if (savingJunction) return;
        setJunctionPreview(target);
        for (const button of list.querySelectorAll("button")) button.setAttribute("aria-pressed", String(button === option));
      });
      item.append(option);
      list.append(item);
    }
    list.hidden = false;
    if (fromMap) list.querySelector("button").click();
    else list.querySelector("button").focus();
  } catch (error) {
    if (request === junctionRequest && version === viewVersion) status.textContent = error.message;
  }
}

function onMapSelection(point) {
  loadJunctionOptions(new URLSearchParams({ lng: point.lng, lat: point.lat }), true);
}

function postProject(path, data) {
  return apiRequest(`/api/projects${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
  });
}

async function saveSelectedJunction() {
  if (!selectedJunction || savingJunction) return;
  const version = viewVersion;
  const status = element("junction-feedback");
  const button = element("study-action");
  savingJunction = button.disabled = true;
  status.textContent = "Guardando el estudio…";
  try {
    const { id } = await postProject("", { junctionId: selectedJunction.junctionId });
    if (version === viewVersion) {
      status.textContent = "";
      location.hash = `#proyecto/${id}`;
    }
  } catch (error) {
    if (version === viewVersion) status.textContent = error.message;
  } finally {
    savingJunction = button.disabled = false;
  }
}

function bindJunctionPicker() {
  element("junction-form").addEventListener("submit", event => {
    event.preventDefault();
    const query = element("junction-query").value.trim();
    if (query) loadJunctionOptions(new URLSearchParams({ q: query }));
  });
  element("study-action").addEventListener("click", saveSelectedJunction);
}

async function loadStudyGroups() {
  await verifyGenerator();
  const [{ projects }, { studies }] = await Promise.all([apiRequest("/api/projects"), studyRequest("")]);
  const stored = new Map(projects.map(project => [project.id, { ...project, runs: [], saved: true }]));
  const historical = [];
  for (const run of studies) {
    const project = stored.get(run.projectId);
    if (project) project.runs.push(run);
    else historical.push(run);
  }
  const legacy = groupSavedStudies(historical).map(({ original, runs }) => ({
    id: original.id, target: original, createdAt: original.createdAt, runs,
  }));
  return [...stored.values(), ...legacy].sort((first, second) =>
    (second.runs[0]?.createdAt ?? second.createdAt).localeCompare(first.runs[0]?.createdAt ?? first.createdAt));
}

function renderStudyList() {
  const list = element("saved-studies");
  const status = element("saved-status");
  const words = text => searchable(text).match(/[a-z0-9]+/g) ?? [];
  const query = words(element("study-search").value).filter(word => !["de", "y", "la", "del"].includes(word));
  const groups = studyGroups.filter(group => {
    const names = words([group.target.title, ...(group.target.accesses ?? [])].join(" "));
    return query.every(word => names.some(name => name === word || (word.length >= 3 && name.startsWith(word))));
  });
  list.replaceChildren();
  for (const group of groups) {
    const item = document.createElement("li");
    item.className = "project-list-item";
    const description = document.createElement("div");
    const heading = document.createElement("h3");
    heading.textContent = group.target.title;
    const details = document.createElement("p");
    details.className = "muted";
    const count = group.runs.length;
    const date = new Date(group.runs[0]?.createdAt ?? group.createdAt);
    const statusText = count ? `${count} ${count === 1 ? "corrida" : "corridas"}` : "Cruce guardado";
    details.textContent = Number.isNaN(date.valueOf()) ? statusText : `${statusText} · ${studyDate.format(date)}`;
    description.append(heading, details);
    const open = document.createElement("a");
    open.className = "button button-secondary";
    open.href = `#proyecto/${group.id}`;
    open.textContent = "Abrir estudio";
    open.setAttribute("aria-label", `Abrir estudio ${group.target.title}. ${details.textContent}`);
    item.append(description, open);
    list.append(item);
  }
  status.textContent = groups.length ? "" : studyGroups.length ? "No encontramos estudios con ese nombre."
    : "Todavía no hay estudios. Elegí Nuevo estudio para empezar.";
}

async function showSavedStudies() {
  const version = viewVersion;
  const tools = element("library-tools");
  const status = element("saved-status");
  tools.hidden = true;
  element("saved-studies").replaceChildren();
  status.textContent = "Cargando estudios…";
  try {
    const groups = await loadStudyGroups();
    if (version !== viewVersion) return;
    studyGroups = groups;
    tools.hidden = !groups.length;
    renderStudyList();
  } catch (error) {
    if (version === viewVersion) status.textContent = error.message;
  }
}

function showProjectFeedback(message) {
  const status = element("project-feedback");
  status.textContent = message;
  status.hidden = !message;
}

function renderProjectRuns(group) {
  const list = element("project-runs");
  const compare = element("project-compare");
  const base = group.runs.find(run => !run.parentId);
  const ordered = base ? [base, ...group.runs.filter(run => run !== base)] : group.runs;
  list.replaceChildren();
  for (const run of ordered) {
    const row = document.createElement("li");
    const info = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = run.parentId ? "Corrida" : "Corrida inicial";
    const details = document.createElement("span");
    details.className = "muted";
    details.textContent = studyDetails(run);
    info.append(label, details);
    const link = document.createElement("a");
    link.className = "button button-secondary";
    link.href = `#estudio/${run.id}`;
    link.textContent = "Reproducir";
    link.setAttribute("aria-label", `Reproducir ${label.textContent.toLowerCase()}. ${details.textContent}`);
    row.append(info, link);
    list.append(row);
  }
  compare.hidden = ordered.length < 2;
  if (!compare.hidden) compare.href = comparisonHash(ordered[0].id, ordered[1].id);
  element("project-runs-title").hidden = !ordered.length;
  list.hidden = !ordered.length;
  return base;
}

async function showProject(identifier, version) {
  element("project-title").textContent = "Estudio";
  element("project-type").textContent = "";
  element("project-content").hidden = true;
  showProjectFeedback("Abriendo el estudio…");
  try {
    const groups = await loadStudyGroups();
    if (version !== viewVersion) return;
    const group = groups.find(item => item.id === identifier);
    if (!group) throw new Error("Ese estudio no está disponible. Volvé a Estudios y elegí otro.");
    lastOpenedProject = group;
    const { target } = group;
    element("project-title").textContent = target.title;
    element("project-type").textContent = target.roundabout ? "Rotonda" : "Intersección";
    const base = renderProjectRuns(group);
    element("project-base-description").textContent = base ? studyDetails(base) : group.saved
      ? "Cruce guardado. La primera corrida usa tráfico de muestra." : "El estudio conserva las corridas disponibles.";
    renderAccesses(element("project-accesses"), target.accesses);
    const hasArea = Array.isArray(target.location) && Array.isArray(target.bounds);
    element("project-map-host").hidden = !hasArea;
    element("project-content").hidden = false;
    if (hasArea) geographicMap.showProject(target);
    const simulate = element("project-run");
    simulate.hidden = !group.saved || Boolean(base);
    simulate.disabled = false;
    showProjectFeedback("");
    if (!simulate.hidden && group.baseRunId) trackProjectRun(group.baseRunId, version);
  } catch (error) {
    if (version === viewVersion) showProjectFeedback(error.message);
  }
}

async function trackProjectRun(id, version) {
  const button = element("project-run");
  const isCurrent = () => version === viewVersion;
  button.disabled = true;
  try {
    if (await waitForStudy(id, isCurrent, status => showProjectFeedback(status.message))) await showView();
  } catch (error) {
    if (isCurrent()) showProjectFeedback(error.message);
  } finally {
    if (isCurrent()) button.disabled = false;
  }
}

async function startProjectRun() {
  const group = lastOpenedProject;
  const button = element("project-run");
  if (!group?.saved || button.disabled) return;
  const version = viewVersion;
  button.disabled = true;
  showProjectFeedback("Preparando la corrida…");
  try {
    const { id } = await postProject(`/${group.id}/runs`, {});
    if (version === viewVersion) await trackProjectRun(id, version);
  } catch (error) {
    if (version === viewVersion) showProjectFeedback(error.message);
  } finally {
    if (version === viewVersion) button.disabled = false;
  }
}
