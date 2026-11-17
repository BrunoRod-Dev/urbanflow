"use strict";

const territoryLabels = {
  sector01: "Sector 01",
  "roosevelt-camacho": "Roosevelt",
  novillo: "Novillo",
};

function territoryElement(id) {
  return document.getElementById(id);
}

function territoryExtent(coordinates, box) {
  if (!Array.isArray(coordinates) || !coordinates.length) return;
  if (typeof coordinates[0] === "number") {
    box[0] = Math.min(box[0], coordinates[0]);
    box[1] = Math.min(box[1], coordinates[1]);
    box[2] = Math.max(box[2], coordinates[0]);
    box[3] = Math.max(box[3], coordinates[1]);
    return;
  }
  for (const child of coordinates) territoryExtent(child, box);
}

function territoryLine(coordinates) {
  if (!Array.isArray(coordinates) || coordinates.length < 2) return null;
  if (!coordinates.every(point => Array.isArray(point) && point.length >= 2 && Number.isFinite(point[0]) && Number.isFinite(point[1]))) return null;
  return coordinates.map(point => [point[0], point[1]]);
}

function territoryCenter(coordinates) {
  const box = [180, 90, -180, -90];
  territoryExtent(coordinates, box);
  if (box[0] > box[2] || box[1] > box[3]) return null;
  return [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2];
}

function territoryZone(sector) {
  if (!Array.isArray(sector?.bounds) || sector.bounds.length !== 4) return null;
  if (sector.id === "sector01") {
    const replayId = sector.data?.replayId;
    if (typeof replayId !== "string" || !/^[a-f0-9]{32}$/.test(replayId) || sector.data?.fieldValidated !== false) return null;
    return {
      id: sector.id,
      label: territoryLabels[sector.id],
      name: sector.title,
      summary: "Permite observar la circulación en 2D y 3D.",
      status: "validated",
      statusLabel: "Simulación validada técnicamente, sin calibración municipal.",
      kind: "Simulación",
      replayId,
      action: { href: `/?probar=1#estudio/${replayId}`, label: "Ver simulación" },
      bounds: sector.bounds,
      point: [(sector.bounds[0] + sector.bounds[2]) / 2, (sector.bounds[1] + sector.bounds[3]) / 2],
    };
  }
  if (sector.id === "roosevelt-camacho") {
    return {
      id: sector.id,
      label: territoryLabels[sector.id],
      name: sector.title,
      summary: "Permite ver la comparación experimental.",
      status: "experimental",
      statusLabel: "Estudios y comparaciones experimentales, sin calibración municipal.",
      kind: "Comparación",
      action: { href: "#decision-ab", label: "Ver comparación" },
      bounds: sector.bounds,
      point: [(sector.bounds[0] + sector.bounds[2]) / 2, (sector.bounds[1] + sector.bounds[3]) / 2],
    };
  }
  return {
    id: sector.id,
    label: sector.title,
    name: sector.title,
    summary: "Este manifiesto no publica una simulación.",
    status: "unavailable",
    kind: "Sin simulación",
    statusLabel: "Sin simulación disponible.",
    action: null,
    bounds: sector.bounds,
    point: [(sector.bounds[0] + sector.bounds[2]) / 2, (sector.bounds[1] + sector.bounds[3]) / 2],
  };
}

async function novilloZone() {
  const [geoResponse, reportResponse] = await Promise.all([
    fetch("assets/novillo-alegre.geojson"),
    fetch("assets/novillo-experimento.json"),
  ]);
  if (!geoResponse.ok || !reportResponse.ok) throw new Error("missing");
  const [geo, report] = await Promise.all([geoResponse.json(), reportResponse.json()]);
  if (report.experimental !== true || report.calibrated !== false || report.seasonal !== false || report.comparison !== null || report.simulated !== null) {
    throw new Error("unmarked");
  }
  const ring = (geo.features ?? []).find(feature => feature.properties?.osmWay === "100089298" && feature.geometry?.type === "LineString");
  const point = ring ? territoryCenter(ring.geometry.coordinates) : null;
  const guide = territoryLine(ring?.geometry?.coordinates);
  if (!point || typeof report.case !== "string") throw new Error("incomplete");
  return {
    id: "novillo",
    label: territoryLabels.novillo,
    name: report.case,
    summary: "La comparación está detenida. No hay resultados publicados.",
    status: "geometry",
    statusLabel: "Solo geometría. Comparación detenida.",
    kind: "Geometría",
    guide: guide ? [guide] : [],
    action: { href: "#novillo", label: "Ver caso" },
    bounds: null,
    point,
  };
}

async function loadTerritoryZones() {
  const sectors = await loadSectorCatalog();
  const zones = sectors.map(territoryZone).filter(Boolean);
  try {
    zones.push(await novilloZone());
  } catch {
    zones.novilloUnavailable = true;
  }
  return zones;
}

let territoryZones = [];
let territorySelected = null;
let territoryMap = null;

function renderTerritoryList(onSelect) {
  const list = territoryElement("territory-zones");
  list.replaceChildren();
  for (const zone of territoryZones) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("aria-pressed", String(zone.id === territorySelected));
    button.setAttribute("aria-label", `${zone.name}. ${zone.statusLabel}`);
    const swatch = document.createElement("i");
    swatch.className = `swatch-${zone.status}`;
    swatch.setAttribute("aria-hidden", "true");
    const name = document.createElement("strong");
    name.textContent = zone.label;
    const kind = document.createElement("span");
    kind.className = "explorer-kind";
    kind.textContent = zone.kind ?? "";
    button.append(swatch, name, kind);
    button.addEventListener("click", () => onSelect(zone.id));
    item.append(button);
    list.append(item);
  }
}

function showTerritoryDetail(zone) {
  const detail = territoryElement("territory-detail");
  const action = territoryElement("territory-action");
  if (!zone) {
    detail.hidden = true;
    delete detail.dataset.status;
    return;
  }
  detail.hidden = false;
  detail.dataset.status = zone.status;
  territoryElement("territory-state").textContent = zone.statusLabel;
  territoryElement("territory-name").textContent = zone.name;
  territoryElement("territory-summary").textContent = zone.summary;
  if (zone.action) {
    action.hidden = false;
    action.href = zone.action.href;
    action.textContent = zone.action.label;
  } else {
    action.hidden = true;
    action.removeAttribute("href");
  }
}

function selectTerritory(id, map) {
  territorySelected = id;
  const zone = territoryZones.find(item => item.id === id) ?? null;
  renderTerritoryList(next => selectTerritory(next, map));
  showTerritoryDetail(zone);
  map.highlightTerritory(id);
}

async function attachPublishedRoads(zones, isCurrent) {
  await Promise.all(zones.map(async zone => {
    if (typeof zone.replayId !== "string") return;
    try {
      const response = await fetch(`/api/studies/${zone.replayId}/replay`);
      if (!response.ok || !isCurrent()) return;
      const replay = await response.json();
      const features = replay?.geographic === true ? replay.network?.features : null;
      if (!isCurrent() || !Array.isArray(features)) return;
      zone.lines = features.flatMap(feature => {
        if (feature?.properties?.used !== true || feature.geometry?.type !== "LineString") return [];
        const line = territoryLine(feature.geometry.coordinates);
        return line ? [line] : [];
      });
    } catch {
      zone.lines = [];
    }
  }));
}

async function showTerritory(map, isCurrent) {
  territoryMap = map;
  const status = territoryElement("territory-status");
  status.textContent = "Cargando casos…";
  territoryElement("territory-detail").hidden = territorySelected == null;
  try {
    const zones = await loadTerritoryZones();
    if (!isCurrent()) return;
    territoryZones = zones;
    status.textContent = zones.novilloUnavailable ? "No se pudo leer el caso de geometría." : "";
    map.showTerritory(zones, id => selectTerritory(id, map));
    renderTerritoryList(id => selectTerritory(id, map));
    if (territorySelected) selectTerritory(territorySelected, map);
    await attachPublishedRoads(zones, isCurrent);
    if (!isCurrent()) return;
    const unreadNetwork = zones.some(zone => zone.replayId && !zone.lines?.length);
    if (unreadNetwork) status.textContent = "No se pudo leer la red simulada.";
    map.redrawTerritory();
  } catch {
    if (!isCurrent()) return;
    territoryZones = [];
    status.textContent = "No se pudieron leer los casos publicados.";
    map.showTerritory([], id => selectTerritory(id, map));
    renderTerritoryList(id => selectTerritory(id, map));
  }
}

territoryElement("territory-close").addEventListener("click", () => {
  if (territoryMap) selectTerritory(null, territoryMap);
});
