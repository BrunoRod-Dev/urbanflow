"use strict";

const mapLibreDist = "https://unpkg.com/maplibre-gl@6.17.0/dist/";
const mapStyle = "https://tiles.openfreemap.org/styles/liberty";

function createMaldonadoMap(onSelection) {
  const container = document.querySelector("#geo-map");
  const baseMap = document.querySelector("#base-map");
  const referenceOverlay = document.querySelector("#pilot-map-references");
  const message = document.querySelector("#geo-message");
  const messageText = document.querySelector("#geo-message-text");
  const actions = document.querySelector("#geo-message-actions");
  const selectionHost = document.querySelector("#selection-map-host");
  const projectHost = document.querySelector("#project-map-host");
  const studyHost = document.querySelector("#study-map-host");
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
  let selectable = false;
  let area = null;
  let study = null;
  let queuedVehicles = [];
  let lastVehicleDraw = 0;
  let fitArea = false;
  let region = null;
  let lastSignalTime = 0;
  let lastSignalState = null;
  let references = [];
  let referenceBadges = [];

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
    map.addLayer({ id: "study-accesses", type: "line", source: "study-area",
      filter: ["==", ["geometry-type"], "LineString"], layout: { "line-cap": "round" },
      paint: { "line-color": "#2459cb", "line-opacity": .78, "line-width": 4 } });
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
      if (selectable && !area) showRegionOverview();
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
      if (!study) {
        features.push({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: target.location } });
        for (const coordinates of target.accessLines ?? []) {
          features.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates } });
        }
      }
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
    const target = study ?? area;
    if (target && fitArea) map.fitBounds(target.bounds, { padding: 42, duration: 0 });
    fitArea = false;
    positionReferences();
  }

  function positionReferences() {
    const width = baseMap.clientWidth;
    const height = baseMap.clientHeight;
    for (const [index, reference] of references.entries()) {
      const { x, y } = map.project(reference.location);
      const badge = referenceBadges[index];
      badge.hidden = x < 0 || x > width || y < 0 || y > height;
      if (!badge.hidden) {
        badge.style.left = `${x}px`;
        badge.style.top = `${y}px`;
      }
    }
  }

  function updateControls() {
    zoomIn.disabled = !ready || map.getZoom() >= maxZoom;
    zoomOut.disabled = !ready || map.getZoom() <= minZoom;
    reset.disabled = !ready;
  }

  function showMessage(text, retry) {
    message.hidden = false;
    messageText.textContent = text;
    actions.hidden = !retry;
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
      map.on("move", positionReferences);
      map.on("resize", positionReferences);
      map.on("click", event => {
        if (selectable) onSelection(event.lngLat.wrap());
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
  container.addEventListener("keydown", event => {
    if (!ready || event.target !== container) return;
    const directions = { ArrowUp: [0, -96], ArrowDown: [0, 96], ArrowLeft: [-96, 0], ArrowRight: [96, 0] };
    if (directions[event.key]) map.panBy(directions[event.key]);
    else if (event.key === "+" || event.key === "=") map.zoomIn();
    else if (event.key === "-") map.zoomOut();
    else if (event.key === "Enter" && selectable) onSelection(map.getCenter().wrap());
    else return;
    event.preventDefault();
  });

  function mount(host, target, replay = false) {
    const previous = study ?? area;
    selectable = host === selectionHost;
    container.classList.toggle("selectable-map", selectable);
    container.setAttribute("aria-label", selectable
      ? "Mapa de Maldonado. Usá las flechas para desplazarte y Enter para buscar un cruce en el centro."
      : "Mapa del estudio. Usá las flechas para desplazarte y más o menos para acercar o alejar.");
    if (container.parentElement !== host) {
      if (replay) host.prepend(container);
      else host.append(container);
    }
    fitArea = Boolean(target && (!ready || !previous || target.bounds.some((value, index) => value !== previous.bounds[index])));
    study = replay ? target : null;
    area = replay ? null : target;
    references = pilotSceneFor(study)?.references ?? [];
    referenceOverlay.hidden = !references.length;
    referenceBadges = createReferenceBadges(referenceOverlay, references);
    queuedVehicles = [];
    lastVehicleDraw = 0;
    if (ready) drawStudy();
    else if (message.hidden) initialize();
  }

  updateControls();
  return {
    showPicker(target) {
      mount(selectionHost, target);
      if (ready && !target) showRegionOverview();
    },
    showProject(target) {
      mount(projectHost, target);
    },
    preview(target) {
      area = target;
      fitArea = Boolean(target);
      if (ready) drawStudy();
    },
    showStudy(data) {
      mount(studyHost, data, true);
    },
    hide() {
      selectable = false;
    },
    resize() {
      if (ready) map.resize();
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
