"use strict";

const novilloMapLibre = "https://unpkg.com/maplibre-gl@6.17.0/dist/";
const novilloStyle = "https://tiles.openfreemap.org/styles/liberty";
let novilloMap = null;
let novilloGeo = null;

function novilloList(selector, lines) {
  const list = document.querySelector(selector);
  list.replaceChildren();
  for (const line of lines) {
    const item = document.createElement("li");
    item.textContent = line;
    list.appendChild(item);
  }
}

function novilloLegend(items) {
  const host = document.querySelector("#novillo-legend");
  host.replaceChildren();
  for (const item of items) {
    const row = document.createElement("span");
    const swatch = document.createElement("i");
    swatch.style.background = item.color;
    row.append(swatch, document.createTextNode(item.label));
    host.appendChild(row);
  }
}

function fitNovillo(geo) {
  const box = [180, 90, -180, -90];
  for (const feature of geo.features) {
    if (feature.geometry.type !== "LineString") continue;
    for (const [lon, lat] of feature.geometry.coordinates) {
      box[0] = Math.min(box[0], lon);
      box[1] = Math.min(box[1], lat);
      box[2] = Math.max(box[2], lon);
      box[3] = Math.max(box[3], lat);
    }
  }
  novilloMap.resize();
  novilloMap.fitBounds([[box[0], box[1]], [box[2], box[3]]], {
    padding: { top: 88, right: 340, bottom: 48, left: 48 },
    duration: 0,
  });
}

function addNovilloLayers() {
  if (novilloMap.getSource("novillo")) return;
  novilloMap.addSource("novillo", { type: "geojson", data: novilloGeo });
  const lines = ["==", ["geometry-type"], "LineString"];
  novilloMap.addLayer({
    id: "novillo-solid",
    type: "line",
    source: "novillo",
    filter: ["all", lines, ["==", ["get", "verified"], true]],
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": ["get", "color"], "line-width": 4, "line-opacity": 0.9 },
  });
  novilloMap.addLayer({
    id: "novillo-dashed",
    type: "line",
    source: "novillo",
    filter: ["all", lines, ["==", ["get", "verified"], false]],
    layout: { "line-cap": "butt", "line-join": "round" },
    paint: { "line-color": ["get", "color"], "line-width": 4, "line-opacity": 0.95, "line-dasharray": [1.1, 0.8] },
  });
  fitNovillo(novilloGeo);
}

async function drawNovillo(geo) {
  novilloGeo = geo;
  if (!document.querySelector("link[href*='maplibre-gl.css']")) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = `${novilloMapLibre}maplibre-gl.css`;
    document.head.append(link);
  }
  if (!novilloMap) {
    const library = await import(`${novilloMapLibre}maplibre-gl.mjs`);
    novilloMap = new library.Map({
      container: "novillo-map",
      style: novilloStyle,
      center: [-54.937, -34.938],
      zoom: 13,
    });
    novilloMap.on("load", addNovilloLayers);
    return;
  }
  const source = novilloMap.getSource("novillo");
  if (source) source.setData(geo);
  if (novilloMap.isStyleLoaded()) fitNovillo(geo);
}

async function showNovilloExperiment(geometrySummary = "") {
  const slot = document.querySelector("#novillo-experiment");
  const technical = document.querySelector("#novillo-technical");
  if (!slot) return;
  try {
    const response = await fetch("assets/novillo-experimento.json");
    if (!response.ok) throw new Error("missing");
    const report = await response.json();
    if (report.experimental !== true || report.calibrated !== false || report.seasonal !== false || report.comparison !== null || report.simulated !== null) {
      throw new Error("unmarked");
    }
    const routes = report.routes;
    slot.textContent = report.summary;
    if (technical) {
      technical.textContent = [
        geometrySummary,
        report.blockage?.reason,
        `Rotonda: ${routes.throughWays.join(", ")}.`,
        `Desvío: ${routes.avoidWays.join(", ")}.`,
        report.speedAssumption?.note,
      ].filter(Boolean).join(" ");
    }
  } catch {
    slot.textContent = "";
    if (technical) technical.textContent = geometrySummary;
  }
}

async function showNovillo() {
  const status = document.querySelector("#novillo-status");
  status.textContent = "Cargando el recorte…";
  try {
    const [reportResponse, geoResponse] = await Promise.all([
      fetch("assets/novillo-alegre.json"),
      fetch("assets/novillo-alegre.geojson"),
    ]);
    if (!reportResponse.ok || !geoResponse.ok) throw new Error("missing");
    const report = await reportResponse.json();
    const geo = await geoResponse.json();
    if (report.experimental !== true || report.calibrated !== false || report.seasonal !== false || report.comparison !== null) {
      throw new Error("unmarked");
    }
    status.textContent = "";
    novilloList("#novillo-verified", report.notes);
    novilloList("#novillo-pending", report.pendingLocalObservations);
    novilloLegend(report.legend);
    await drawNovillo(geo);
    await showNovilloExperiment(report.summary);
  } catch {
    status.textContent = "No se pudo abrir el caso geométrico.";
  }
}
