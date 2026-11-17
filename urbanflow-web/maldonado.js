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
  const territoryHost = document.querySelector("#territory-map-host");
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
  let territory = false;
  let territoryZones = [];
  let territorySelected = null;
  let territorySelect = null;
  let vehicleSelect = null;
  let signalSelect = null;
  let signalCatalog = [];
  let highlightedSignal = null;
  let fitTerritory = false;
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
  let qa = null;

  const collection = features => ({ type: "FeatureCollection", features });
  const qaLayers = { roads: "study-roads", connections: "qa-connections",
    signals: "study-signal-points", cars: "study-cars" };

  function addStudyLayers() {
    map.addSource("territory-zones", { type: "geojson", data: collection([]) });
    map.addLayer({ id: "territory-fill", type: "fill", source: "territory-zones",
      filter: ["==", ["geometry-type"], "Polygon"], paint: {
        "fill-color": "#1a735c",
        "fill-opacity": 0,
      } });
    map.addLayer({ id: "territory-line", type: "line", source: "territory-zones",
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: {
        "line-color": ["match", ["get", "status"], "validated", "#14614d", "experimental", "#8a4508", "#5c6b7a"],
        "line-width": 1.25, "line-opacity": .45, "line-dasharray": [1.4, 1.2],
      } });
    map.addLayer({ id: "territory-road-case", type: "line", source: "territory-zones",
      filter: ["all", ["==", ["geometry-type"], "LineString"], ["==", ["get", "role"], "simulated"]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#ffffff", "line-opacity": .92,
        "line-width": ["interpolate", ["linear"], ["zoom"], 11, 4.2, 15, 8] } });
    map.addLayer({ id: "territory-roads", type: "line", source: "territory-zones",
      filter: ["all", ["==", ["geometry-type"], "LineString"], ["==", ["get", "role"], "simulated"]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": ["match", ["get", "status"], "validated", "#1a735c", "experimental", "#a9520a", "#2459cb"],
        "line-width": ["interpolate", ["linear"], ["zoom"], 11, 2.2, 15, 4.8], "line-opacity": .95,
      } });
    map.addLayer({ id: "territory-guide", type: "line", source: "territory-zones",
      filter: ["all", ["==", ["geometry-type"], "LineString"], ["==", ["get", "role"], "guide"]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#5c6b7a", "line-width": 2, "line-opacity": .85, "line-dasharray": [1.2, 1.3] } });
    map.addLayer({ id: "territory-point", type: "circle", source: "territory-zones",
      filter: ["==", ["geometry-type"], "Point"], paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 7, 15, 12],
        "circle-color": ["match", ["get", "status"], "validated", "#1a735c", "experimental", "#a9520a", "geometry", "#5c6b7a", "#8aa0b4"],
        "circle-stroke-color": "#fff",
        "circle-stroke-width": ["case", ["get", "selected"], 3, 2],
      } });
    const labelFont = map.getStyle().layers.find(layer => layer.type === "symbol" && layer.layout?.["text-font"])?.layout["text-font"];
    if (Array.isArray(labelFont) && labelFont.every(name => typeof name === "string")) {
      map.addLayer({ id: "territory-labels", type: "symbol", source: "territory-zones",
        filter: ["==", ["geometry-type"], "Point"], layout: {
          "text-field": ["get", "label"], "text-size": 12, "text-font": labelFont,
          "text-offset": [0, 1.1], "text-anchor": "top", "text-allow-overlap": true,
        }, paint: { "text-color": "#10223a", "text-halo-color": "#fff", "text-halo-width": 1.4 } });
    }
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
    map.addLayer({ id: "study-selected", type: "circle", source: "study-vehicles",
      layout: { visibility: "none" },
      paint: { "circle-radius": 18, "circle-color": "#214dc526",
        "circle-stroke-color": "#214dc5", "circle-stroke-width": 3 } });
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
      if (territory && !territorySelected) showRegionOverview();
      else if (selectable && !area) showRegionOverview();
    } catch (error) {
      console.warn("UrbanFlow: no se pudo cargar la vista regional.", error);
    }
  }

  function signalIdentity(approach) {
    const indices = approach.indices ?? [];
    const key = [...indices].sort((a, b) => a - b).join(",");
    const found = signalCatalog.find(item => item.controllerId === approach.controller
      && [...item.indices].sort((a, b) => a - b).join(",") === key);
    return found ?? { controllerId: approach.controller, fromLane: null, indices };
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
      const identity = signalIdentity(approach);
      return { type: "Feature", geometry: { type: "Point", coordinates: approach.point },
        properties: {
          state: aspects.size === 1 ? aspects.values().next().value : "mixed",
          controller: identity.controllerId,
          fromLane: identity.fromLane ?? "",
          indices: identity.indices.join(","),
          signalKey: `${identity.controllerId}|${identity.fromLane ?? ""}`,
        } };
    });
    map.getSource("study-signals").setData(collection(features));
  }

  function zoneRing(bounds) {
    const [west, south, east, north] = bounds;
    return [[west, south], [east, south], [east, north], [west, north], [west, south]];
  }

  function pushLines(features, zone, lines, role, selected) {
    for (const coordinates of lines ?? []) {
      if (!Array.isArray(coordinates) || coordinates.length < 2) continue;
      features.push({ type: "Feature", properties: { id: zone.id, status: zone.status, label: zone.label, selected, role },
        geometry: { type: "LineString", coordinates } });
    }
  }

  function simulatedFrame(zone) {
    const box = [180, 90, -180, -90];
    let found = false;
    for (const line of zone?.lines ?? []) {
      for (const point of line) {
        if (!Array.isArray(point) || point.length < 2) continue;
        found = true;
        box[0] = Math.min(box[0], point[0]);
        box[1] = Math.min(box[1], point[1]);
        box[2] = Math.max(box[2], point[0]);
        box[3] = Math.max(box[3], point[1]);
      }
    }
    return found ? box : null;
  }

  function drawZones() {
    const source = map.getSource("territory-zones");
    if (!source) return;
    const features = [];
    if (territory) {
      for (const zone of territoryZones) {
        const selected = zone.id === territorySelected;
        pushLines(features, zone, zone.lines, "simulated", selected);
        pushLines(features, zone, zone.guide, "guide", selected);
        if (selected && Array.isArray(zone.bounds) && zone.bounds.length === 4 && zone.status !== "geometry") {
          features.push({ type: "Feature", properties: { id: zone.id, status: zone.status, label: zone.label, selected },
            geometry: { type: "Polygon", coordinates: [zoneRing(zone.bounds)] } });
        }
        if (Array.isArray(zone.point) && zone.point.length === 2) {
          features.push({ type: "Feature", properties: { id: zone.id, status: zone.status, label: zone.label, selected },
            geometry: { type: "Point", coordinates: zone.point } });
        }
      }
    }
    source.setData(collection(features));
    if (map.getLayer("regional-outline")) {
      map.setLayoutProperty("regional-outline", "visibility", territory ? "none" : "visible");
    }
  }

  function showTerritoryOverview() {
    if (region) showRegionOverview();
    else if (territoryZones.some(zone => Array.isArray(zone.bounds))) {
      const box = [180, 90, -180, -90];
      for (const zone of territoryZones) {
        if (!Array.isArray(zone.bounds)) continue;
        box[0] = Math.min(box[0], zone.bounds[0]);
        box[1] = Math.min(box[1], zone.bounds[1]);
        box[2] = Math.max(box[2], zone.bounds[2]);
        box[3] = Math.max(box[3], zone.bounds[3]);
      }
      map.fitBounds(box, { padding: 64, duration: 0 });
    } else map.jumpTo({ center: maldonado, zoom: 12 });
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
    drawZones();
    drawArea();
    map.getSource("study-network").setData(study?.network ?? collection([]));
    map.setLayoutProperty("study-cars", "icon-anchor", study?.laneMotion?.projection ? "center" : "top");
    map.getSource("study-vehicles").setData(collection(study ? queuedVehicles : []));
    lastSignalState = null;
    drawSignals(lastSignalTime);
    map.resize();
    const target = study ?? area;
    if (target && fitArea) map.fitBounds(target.bounds, { padding: 42, duration: 0 });
    else if (territory && fitTerritory) {
      const zone = territoryZones.find(item => item.id === territorySelected);
      const frame = simulatedFrame(zone) ?? (Array.isArray(zone?.bounds) ? zone.bounds : null);
      if (frame) map.fitBounds(frame, { padding: { top: 92, right: 360, bottom: 108, left: 48 }, duration: 0, maxZoom: 15 });
      else if (zone?.point) map.jumpTo({ center: zone.point, zoom: 13 });
      else showTerritoryOverview();
    }
    fitArea = false;
    fitTerritory = false;
    applyQa();
    positionReferences();
  }

  function applyQa() {
    if (!ready) return;
    if (!map.getLayer("qa-connections") && qa) {
      map.addSource("qa-geometry", { type: "geojson", data: collection([]) });
      map.addLayer({ id: "qa-connections", type: "line", source: "qa-geometry", minzoom: 14,
        paint: { "line-color": "#6e39a8", "line-width": 2, "line-opacity": .78 } }, "study-cars");
      map.addSource("qa-location", { type: "geojson", data: collection([]) });
      map.addLayer({ id: "qa-alert", type: "circle", source: "qa-location",
        paint: { "circle-radius": 12, "circle-color": "#fff", "circle-opacity": .25,
          "circle-stroke-color": "#a32778", "circle-stroke-width": 3 } }, "study-cars");
      map.addLayer({ id: "qa-vehicle-halo", type: "circle", source: "study-vehicles",
        paint: { "circle-radius": ["case", ["boolean", ["get", "followed"], false], 17, 11],
          "circle-color": ["case", ["boolean", ["get", "followed"], false], "#a32778", "#095887"],
          "circle-opacity": .85, "circle-stroke-color": "#fff", "circle-stroke-width": 2 } }, "study-cars");
    }
    if (!map.getLayer("qa-connections")) return;
    for (const [key, layer] of Object.entries(qaLayers)) {
      const visible = qa?.layers[key] ?? (key !== "connections");
      map.setLayoutProperty(layer, "visibility", visible ? "visible" : "none");
    }
    map.setLayoutProperty("qa-vehicle-halo", "visibility", qa?.layers.cars ? "visible" : "none");
    map.setLayoutProperty("qa-alert", "visibility", qa ? "visible" : "none");
    map.setLayoutProperty("study-cars", "icon-size", qa ? 1.5 : 1);
    map.getSource("qa-geometry").setData(qa?.connections ?? collection([]));
    map.getSource("qa-location").setData(collection(qa?.point ? [{
      type: "Feature", properties: {}, geometry: { type: "Point", coordinates: qa.point },
    }] : []));
    if (qa?.pointToFocus) {
      map.jumpTo({ center: qa.point, zoom: 18.5 });
      qa.pointToFocus = false;
    } else if (qa?.fit && study) {
      map.fitBounds(study.bounds, { padding: 35, duration: 0, maxZoom: 17 });
      qa.fit = false;
    }
    if (qa?.pendingCenter) {
      map.jumpTo({ center: qa.pendingCenter });
      qa.pendingCenter = null;
    }
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
        else if (territory && territorySelect) {
          const layers = ["territory-roads", "territory-guide", "territory-point", "territory-labels"].filter(id => map.getLayer(id));
          const hit = layers.length ? map.queryRenderedFeatures(event.point, { layers })[0] : null;
          territorySelect(hit?.properties?.id ?? null);
        } else if (study && map.getLayer("study-cars")) {
          const box = [[event.point.x - 8, event.point.y - 8], [event.point.x + 8, event.point.y + 8]];
          const layers = ["study-signal-points", "study-cars", "study-selected"].filter(id => map.getLayer(id));
          const hit = map.queryRenderedFeatures(box, { layers })[0];
          if (hit?.layer.id === "study-signal-points" && hit.properties?.controller && signalSelect) {
            const indices = String(hit.properties.indices ?? "").split(",").map(Number).filter(Number.isInteger);
            signalSelect({ controllerId: hit.properties.controller, fromLane: hit.properties.fromLane || null, indices });
          } else if (hit && vehicleSelect && Number.isInteger(hit.id)) vehicleSelect(hit.id);
        }
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
    else if (territory) showTerritoryOverview();
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
    territory = host === territoryHost;
    container.classList.toggle("selectable-map", selectable);
    container.classList.toggle("territory-map", territory);
    container.setAttribute("aria-label", territory
      ? "Mapa de Maldonado. Los trazos continuos son calles de una simulación publicada."
      : selectable
      ? "Mapa de Maldonado. Usá las flechas para desplazarte y Enter para buscar un cruce en el centro."
      : "Mapa del estudio. Usá las flechas para desplazarte y más o menos para acercar o alejar.");
    if (container.parentElement !== host) {
      if (replay) host.prepend(container);
      else host.append(container);
    }
    fitArea = Boolean(target && (!ready || !previous || target.bounds.some((value, index) => value !== previous.bounds[index])));
    study = replay ? target : null;
    area = replay ? null : target;
    references = sceneFor(study)?.references ?? [];
    referenceOverlay.hidden = !references.length;
    referenceBadges = createReferenceBadges(referenceOverlay, references);
    queuedVehicles = [];
    lastVehicleDraw = 0;
    if (ready) drawStudy();
    else if (message.hidden) initialize();
  }

  updateControls();
    return {
    setVehicleSelect(handler) { vehicleSelect = handler; },
    setSignalSelect(handler) { signalSelect = handler; },
    setSignalCatalog(list) {
      signalCatalog = Array.isArray(list) ? list : [];
      highlightedSignal = null;
      lastSignalState = null;
      if (ready && study) drawSignals(lastSignalTime);
    },
    highlightSignal(selection) {
      if (!ready || !map.getLayer("study-signal-points")) return;
      const key = selection?.controllerId ? `${selection.controllerId}|${selection.fromLane ?? ""}` : "";
      if (key === highlightedSignal) return;
      highlightedSignal = key;
      const selected = ["==", ["get", "signalKey"], key];
      map.setPaintProperty("study-signal-points", "circle-stroke-color", ["case", selected, "#214dc5", "#fff"]);
      map.setPaintProperty("study-signal-points", "circle-stroke-width", ["case", selected, 3, 1.5]);
      map.setPaintProperty("study-signal-points", "circle-radius", ["case", selected,
        ["interpolate", ["linear"], ["zoom"], 14, 7, 18, 11],
        ["interpolate", ["linear"], ["zoom"], 14, 3, 18, 6]]);
    },
    highlightVehicle(index) {
      if (!ready || !map.getLayer("study-selected")) return;
      const active = Number.isInteger(index) && index >= 0;
      map.setLayoutProperty("study-selected", "visibility", active ? "visible" : "none");
      if (active) map.setFilter("study-selected", ["==", ["id"], index]);
    },
    showTerritory(zones, onSelect) {
      territoryZones = Array.isArray(zones) ? zones : [];
      territorySelect = onSelect;
      territorySelected = null;
      fitTerritory = true;
      mount(territoryHost, null);
    },
    highlightTerritory(id) {
      territorySelected = id;
      const zone = territoryZones.find(item => item.id === id);
      if (!ready) return;
      drawZones();
      const frame = simulatedFrame(zone) ?? (Array.isArray(zone?.bounds) ? zone.bounds : null);
      if (frame) map.fitBounds(frame, { padding: { top: 92, right: 360, bottom: 108, left: 48 }, duration: 0, maxZoom: 15 });
      else if (zone?.point) map.jumpTo({ center: zone.point, zoom: Math.max(map.getZoom(), 13) });
    },
    redrawTerritory() {
      if (ready && territory) drawZones();
    },
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
    qaConfigure(connections) {
      qa = connections ? { connections, layers: { roads: true, connections: true, signals: true, cars: true },
        vehicle: null, point: null, fit: true } : null;
      applyQa();
    },
    qaLayer(key, visible) {
      if (!qa) return;
      qa.layers[key] = visible;
      if (!ready) return;
      map.setLayoutProperty(qaLayers[key], "visibility", visible ? "visible" : "none");
      if (key === "cars") map.setLayoutProperty("qa-vehicle-halo", "visibility", visible ? "visible" : "none");
    },
    qaFit() {
      if (!qa) return;
      qa.point = null;
      qa.pendingCenter = null;
      qa.pointToFocus = false;
      qa.fit = true;
      applyQa();
    },
    qaLocate(point) {
      if (!qa) return;
      qa.point = point;
      qa.pendingCenter = null;
      qa.pointToFocus = true;
      qa.fit = false;
      applyQa();
    },
    qaFollow(vehicle) {
      if (qa) qa.vehicle = vehicle;
    },
    qaFocus(point) {
      if (!qa || !point) return;
      if (ready) map.jumpTo({ center: point });
      else qa.pendingCenter = point;
    },
    qaCenter() {
      return ready && qa ? map.getCenter().toArray() : null;
    },
    drawSignals,
    drawVehicles(cars, highlight, playing) {
      if (!study) return;
      const now = performance.now();
      if (playing && now - lastVehicleDraw < 45) return;
      lastVehicleDraw = now;
      queuedVehicles = cars.map(([id, lng, lat, angle, speed]) => ({
        type: "Feature", id, geometry: { type: "Point", coordinates: [lng, lat] },
        properties: { angle, stopped: highlight && speed < .1, ...(qa ? { followed: id === qa.vehicle } : {}) },
      }));
      if (ready) {
        map.getSource("study-vehicles").setData(collection(queuedVehicles));
        const followed = qa?.vehicle == null ? null : queuedVehicles.find(item => item.id === qa.vehicle);
        if (followed) {
          map.jumpTo({ center: followed.geometry.coordinates, zoom: Math.max(map.getZoom(), 17.5) });
        }
      }
    },
  };
}
