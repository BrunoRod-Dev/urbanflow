"use strict";

const mapLibreDist = "https://unpkg.com/maplibre-gl@6.17.0/dist/";
const mapStyle = "https://tiles.openfreemap.org/styles/liberty";

function createMaldonadoMap(pilot, onSelection) {
  const container = document.querySelector("#geo-map");
  const baseMap = document.querySelector("#base-map");
  const message = document.querySelector("#geo-message");
  const messageText = document.querySelector("#geo-message-text");
  const actions = document.querySelector("#geo-message-actions");
  const pin = document.querySelector("#map-pin");
  const pilotMarker = document.querySelector("#pilot-marker");
  const locatePilot = document.querySelector("#locate-pilot");
  const selectionHost = document.querySelector("#selection-map-host");
  const studyHost = document.querySelector("#study-map-host");
  const selectButton = document.querySelector("#select-point");
  const placementHint = document.querySelector("#placement-hint");
  const selection = document.querySelector("#selection");
  const selectionLink = document.querySelector("#selection-link");
  const zoomIn = document.querySelector("#geo-in");
  const zoomOut = document.querySelector("#geo-out");
  const reset = document.querySelector("#geo-center");
  const showRegion = document.querySelector("#show-region");
  const maldonado = [-54.958, -34.910];
  const defaultZoom = 14.7;
  const minZoom = 11;
  const maxZoom = 19;
  let map;
  let ready = false;
  let loading = false;
  let selected = null;
  let placing = false;
  let area = null;
  let study = null;
  let queuedVehicles = [];
  let lastVehicleDraw = 0;
  let fitStudy = false;
  let region = null;
  let lastSignalTime = 0;
  let lastSignalState = null;

  const collection = features => ({ type: "FeatureCollection", features });

  function addStudyLayers() {
    map.addSource("regional-area", { type: "geojson", data: collection([]) });
    map.addLayer({ id: "regional-outline", type: "line", source: "regional-area", maxzoom: 14.5,
      paint: { "line-color": "#2670ad", "line-width": 2, "line-opacity": .7, "line-dasharray": [3, 2] } });
    map.addSource("study-area", { type: "geojson", data: collection([]) });
    map.addLayer({ id: "study-outline", type: "line", source: "study-area",
      filter: ["==", ["geometry-type"], "Polygon"], paint: {
        "line-color": "#2459cb", "line-dasharray": [3, 2], "line-opacity": .7, "line-width": 2,
      } });
    map.addLayer({ id: "study-junction", type: "circle", source: "study-area",
      filter: ["==", ["geometry-type"], "Point"], paint: {
        "circle-radius": 5, "circle-color": "#2459cb", "circle-stroke-color": "#fff", "circle-stroke-width": 2,
      } });
    map.addSource("study-network", { type: "geojson", data: collection([]) });
    const labelLayer = map.getStyle().layers.find(layer => layer.type === "symbol")?.id;
    map.addLayer({ id: "study-roads", type: "line", source: "study-network",
      layout: { "line-cap": "round", "line-join": "round" }, paint: {
        "line-color": ["case", ["get", "used"], "#2565d7", "#6090b2"],
        "line-opacity": ["case", ["get", "used"], .68, .32], "line-width": 2.5,
      } }, labelLayer);
    for (const [name, fill] of [["urbanflow-car", "#1764db"], ["urbanflow-stopped", "#a9520a"]]) {
      const sprite = document.createElement("canvas");
      sprite.width = 16;
      sprite.height = 30;
      const ctx = sprite.getContext("2d");
      ctx.beginPath();
      ctx.roundRect(1, 1, 14, 28, 4);
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#fff";
      ctx.stroke();
      ctx.fillStyle = "#e3efff";
      ctx.fillRect(4, 6, 8, 4);
      map.addImage(name, ctx.getImageData(0, 0, 16, 30), { pixelRatio: 2 });
    }
    map.addSource("study-vehicles", { type: "geojson", data: collection([]) });
    map.addLayer({ id: "study-cars", type: "symbol", source: "study-vehicles", layout: {
      "icon-image": ["case", ["get", "stopped"], "urbanflow-stopped", "urbanflow-car"],
      "icon-anchor": "top", "icon-rotate": ["get", "angle"], "icon-rotation-alignment": "map",
      "icon-allow-overlap": true, "icon-ignore-placement": true,
    } });
    map.addSource("study-signals", { type: "geojson", data: collection([]) });
    map.addLayer({ id: "study-signal-points", type: "circle", source: "study-signals", minzoom: 14,
      paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 14, 3, 18, 6],
        "circle-stroke-width": 1.5, "circle-stroke-color": "#fff",
        "circle-color": ["match", ["get", "state"], "green", "#15784e", "yellow", "#df9c0c",
          "red", "#cb3835", "mixed", "#7954b3", "#7c8b98"] } });
  }

  function showRegionOverview() {
    if (region && ready) map.fitBounds(region.bounds, { padding: 38, duration: 0 });
  }

  async function loadRegion() {
    if (region || location.protocol === "file:") return;
    try {
      const response = await fetch("/api/region", { cache: "no-store", signal: AbortSignal.timeout(3000) });
      if (!response.ok) return;
      const data = await response.json();
      if (!data.available) return;
      region = data;
      map.getSource("regional-area").setData(collection([{ type: "Feature", properties: {},
        geometry: { type: "Polygon", coordinates: [region.outline] } }]));
      showRegion.hidden = false;
      document.querySelector("#region-label").textContent = "Solanas · Maldonado · Punta del Este · La Barra";
      drawArea();
      if (!study && !selected) showRegionOverview();
    } catch (error) {
      console.warn("UrbanFlow: no se pudo cargar la vista regional.", error);
    }
  }

  function drawSignals(time) {
    lastSignalTime = time;
    if (!ready) return;
    const replay = study?.signalReplay;
    const states = new Map(Object.entries(replay?.states ?? {}).map(([id, timeline]) =>
      [id, timeline.findLast(([at]) => at <= time)?.[1] ?? ""]));
    const key = [...states.values()].join("|");
    if (key === lastSignalState) return;
    lastSignalState = key;
    const colors = { g: "green", y: "yellow", u: "yellow", r: "red" };
    const features = (replay?.approaches ?? []).map(approach => {
      const state = states.get(approach.controller);
      const aspects = new Set(approach.indices.map(index => colors[state?.[index]?.toLowerCase()] ?? "off"));
      return { type: "Feature", geometry: { type: "Point", coordinates: approach.point },
        properties: { state: aspects.size === 1 ? aspects.values().next().value : "mixed" } };
    });
    map.getSource("study-signals").setData(collection(features));
  }

  function drawArea() {
    if (!ready) return;
    const target = study ?? area;
    const label = target ? "Encuadrar área de estudio" : region ? "Encuadrar región" : "Centrar en Maldonado";
    reset.setAttribute("aria-label", label);
    reset.title = label;
    const features = [];
    if (target) {
      const [west, south, east, north] = target.bounds;
      features.push({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [
        [[west, south], [east, south], [east, north], [west, north], [west, south]],
      ] } });
      if (!study) features.push({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: target.location } });
    }
    map.getSource("study-area").setData(collection(features));
  }

  function drawStudy() {
    if (!ready) return;
    drawArea();
    map.getSource("study-network").setData(study?.network ?? collection([]));
    map.setLayoutProperty("study-cars", "icon-anchor", study?.laneMotion ? "center" : "top");
    map.getSource("study-vehicles").setData(collection(study ? queuedVehicles : []));
    lastSignalState = null;
    drawSignals(lastSignalTime);
    map.resize();
    if (study && fitStudy) map.fitBounds(study.bounds, { padding: 42, duration: 0 });
    fitStudy = false;
    positionMarkers();
  }

  function updateControls() {
    zoomIn.disabled = !ready || map.getZoom() >= maxZoom;
    zoomOut.disabled = !ready || map.getZoom() <= minZoom;
    reset.disabled = !ready;
    selectButton.disabled = !ready;
    locatePilot.disabled = !ready;
  }

  function showMessage(text, retry) {
    message.hidden = false;
    messageText.textContent = text;
    actions.hidden = !retry;
  }

  function positionMarkers() {
    if (study) {
      pilotMarker.hidden = true;
      pin.hidden = true;
      return;
    }
    const marker = map.project([pilot.location.lng, pilot.location.lat]);
    pilotMarker.style.left = `${marker.x}px`;
    pilotMarker.style.top = `${marker.y}px`;
    pilotMarker.hidden = marker.x < 0 || marker.x > baseMap.clientWidth || marker.y < 0 || marker.y > baseMap.clientHeight;
    if (selected) {
      const point = map.project([selected.lng, selected.lat]);
      pin.style.left = `${point.x}px`;
      pin.style.top = `${point.y}px`;
      pin.hidden = false;
    }
  }

  function togglePlacement(enabled) {
    placing = enabled;
    placementHint.hidden = !enabled;
    selectButton.setAttribute("aria-pressed", String(enabled));
    selectButton.textContent = enabled ? "Cancelar selección" : selected ? "Cambiar punto" : "Marcar un punto";
    container.classList.toggle("placing", enabled);
    if (enabled) container.focus({ preventScroll: true });
  }

  function select(point) {
    selected = point;
    const lat = selected.lat.toFixed(6);
    const lon = selected.lng.toFixed(6);
    selectionLink.textContent = `${lat}, ${lon} ↗`;
    selectionLink.href = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=18/${lat}/${lon}`;
    selection.hidden = false;
    togglePlacement(false);
    positionMarkers();
    onSelection(selected);
  }

  function initialize() {
    if (ready || loading) return;
    loading = true;
    showMessage("Cargando el mapa de Maldonado…", false);
    const stylesheet = document.createElement("link");
    stylesheet.rel = "stylesheet";
    stylesheet.href = `${mapLibreDist}maplibre-gl.css`;
    const cssLoaded = new Promise((resolve, reject) => {
      stylesheet.onload = resolve;
      stylesheet.onerror = reject;
    });
    document.head.append(stylesheet);

    let expired = false;
    let timeout;
    const deadline = new Promise((_, reject) => {
      timeout = setTimeout(() => reject(new Error("Tiempo de carga agotado")), 12000);
    });
    const firstRender = Promise.all([import(`${mapLibreDist}maplibre-gl.mjs`), cssLoaded]).then(([library]) => {
      if (expired) return;
      map = new library.Map({
        container: baseMap,
        style: mapStyle,
        center: maldonado,
        zoom: defaultZoom,
        minZoom,
        maxZoom,
        keyboard: false,
        dragRotate: false,
        pitchWithRotate: false,
        scrollZoom: false,
        renderWorldCopies: false,
        attributionControl: { compact: false },
      });
      map.touchZoomRotate.disableRotation();
      map.getCanvas().tabIndex = -1;
      return new Promise((resolve, reject) => {
        let loadError;
        const recordError = ({ error }) => { loadError = error; };
        map.on("error", recordError);
        map.once("load", () => {
          map.off("error", recordError);
          if (loadError && map.queryRenderedFeatures().length === 0) reject(loadError);
          else resolve();
        });
      });
    });

    Promise.race([firstRender, deadline]).then(() => {
      addStudyLayers();
      ready = true;
      message.hidden = true;
      updateControls();
      map.on("zoom", updateControls);
      map.on("move", positionMarkers);
      map.on("click", event => {
        if (placing) select(event.lngLat.wrap());
      });
      drawStudy();
      loadRegion();
    }).catch(error => {
      expired = true;
      ready = false;
      map?.remove();
      map = undefined;
      updateControls();
      stylesheet.remove();
      console.warn("UrbanFlow: no se pudo cargar el mapa de Maldonado.", error);
      showMessage("El mapa de Maldonado no pudo cargar. Podés reintentar o abrirlo en otra pestaña.", true);
    }).finally(() => {
      clearTimeout(timeout);
      loading = false;
    });
  }

  document.querySelector("#geo-retry").addEventListener("click", initialize);
  zoomIn.addEventListener("click", () => map.zoomIn());
  zoomOut.addEventListener("click", () => map.zoomOut());
  reset.addEventListener("click", () => {
    const target = study ?? area;
    if (target) map.fitBounds(target.bounds, { padding: 42, duration: 0 });
    else if (region) showRegionOverview();
    else map.jumpTo({ center: maldonado, zoom: defaultZoom });
  });
  showRegion.addEventListener("click", showRegionOverview);
  selectButton.addEventListener("click", () => togglePlacement(!placing));
  pilotMarker.addEventListener("click", () => select(pilot.location));
  locatePilot.addEventListener("click", () => {
    map.jumpTo({ center: [pilot.location.lng, pilot.location.lat], zoom: 17 });
    select(pilot.location);
  });
  container.addEventListener("keydown", event => {
    if (!ready || event.target !== container) return;
    const directions = { ArrowUp: [0, -96], ArrowDown: [0, 96], ArrowLeft: [-96, 0], ArrowRight: [96, 0] };
    if (directions[event.key]) map.panBy(directions[event.key]);
    else if (event.key === "+" || event.key === "=") map.zoomIn();
    else if (event.key === "-") map.zoomOut();
    else if (event.key === "Enter" && placing) select(map.getCenter().wrap());
    else if (event.key === "Escape" && placing) {
      togglePlacement(false);
      selectButton.focus();
    }
    else return;
    event.preventDefault();
  });

  updateControls();
  return {
    refresh() {
      if (map) map.resize();
      else if (message.hidden) initialize();
    },
    preview(target) {
      area = target;
      drawArea();
    },
    showStudy(data) {
      togglePlacement(false);
      const sameArea = study?.clicked.every((coordinate, index) => Math.abs(coordinate - data.clicked[index]) < .00001);
      study = data;
      queuedVehicles = [];
      lastVehicleDraw = 0;
      fitStudy = !sameArea && (!selected || Math.abs(selected.lng - data.clicked[0]) > .00001
        || Math.abs(selected.lat - data.clicked[1]) > .00001);
      studyHost.prepend(container);
      if (ready) drawStudy();
      else if (message.hidden) initialize();
    },
    restoreSelection() {
      if (!study) return;
      study = null;
      selectionHost.append(container);
      if (ready) drawStudy();
    },
    drawSignals,
    drawVehicles(cars, highlight, playing) {
      if (!study) return;
      const now = performance.now();
      if (playing && now - lastVehicleDraw < 45) return;
      lastVehicleDraw = now;
      queuedVehicles = cars.map(([id, lng, lat, angle, speed]) => ({
        type: "Feature", id, geometry: { type: "Point", coordinates: [lng, lat] },
        properties: { angle, stopped: highlight && speed < .1 },
      }));
      if (ready) map.getSource("study-vehicles").setData(collection(queuedVehicles));
    },
  };
}
