"use strict";

function createReferenceBadges(host, references = []) {
  const badges = references.map(({ label }) => {
    const badge = document.createElement("span");
    badge.className = "reference-badge";
    badge.textContent = label;
    badge.hidden = true;
    return badge;
  });
  host.replaceChildren(...badges);
  return badges;
}

function createReplayViews(geographicMap, redraw) {
  const mapHost = document.querySelector("#study-map-host");
  const panel = document.querySelector("#study-3d");
  const frame = document.querySelector("#scene-frame");
  const canvasHost = document.querySelector("#scene-canvas");
  const referenceHost = document.querySelector("#scene-references");
  const switcher = document.querySelector("#replay-view-switch");
  const legend = document.querySelector("#pilot-reference-legend");
  const feedback = document.querySelector("#replay-view-feedback");
  const mapButton = document.querySelector("#use-map-view");
  const sceneButton = document.querySelector("#use-3d-view");
  const oblique = document.querySelector("#camera-oblique");
  const street = document.querySelector("#camera-street");
  const chaseButton = document.querySelector("#camera-chase");
  const freeButton = document.querySelector("#camera-free");
  const signalsCamera = document.querySelector("#camera-signals");
  const crossingCamera = document.querySelector("#camera-crossing");
  const pedestrianStatus = document.querySelector("#scene-pedestrians");
  const curbCamera = document.querySelector("#camera-curb");
  const curbPanel = document.querySelector("#curb-survey");
  const curbDistance = document.querySelector("#curb-distance");
  const curbFeature = document.querySelector("#curb-feature");
  const curbSimulation = document.querySelector("#curb-simulation");
  const curbDescription = document.querySelector("#curb-description");
  const curbSources = document.querySelector("#curb-sources");
  const signalToggle = document.querySelector("#signal-movements");
  const signalControl = document.querySelector("#signal-movements-control");
  const signalLegend = document.querySelector("#signal-movement-legend");
  const signalAssumptions = document.querySelector("#scene-signal-assumptions");
  const streetReference = document.querySelector("#scene-street-reference");
  let data;
  let runId;
  let config;
  let viewer;
  let survey;
  let sceneActive = false;
  let camera = "oblique";
  let request = 0;
  let qa;
  let outside = 0;
  let comfort = false;
  let previewFollow = null;
  let previewClose = false;
  let userCamera = null;
  let vehicleSelect = null;
  let signalSelect = null;
  let signalMark = null;
  let sectorReady = Promise.resolve(null);

  function applyChrome() {
    const references = config?.references ?? [];
    legend.replaceChildren(...references.map(item => {
      const span = document.createElement("span");
      const mark = document.createElement("b");
      mark.textContent = item.label ?? "";
      span.append(mark, document.createTextNode(item.title ? ` ${item.title}` : ""));
      return span;
    }));
    const reference = config?.signals?.center ?? data?.location;
    if (reference) {
      const [lon, lat] = reference;
      streetReference.href = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat},${lon}`;
    }
    streetReference.hidden = true;
    switcher.hidden = !config;
    legend.hidden = !references.length;
    signalsCamera.textContent = config?.cameras?.signalsLabel || "Semáforos";
    crossingCamera.textContent = config?.cameras?.crossing?.label || "Cruce peatonal";
    curbCamera.textContent = config?.cameras?.curb?.label || "Cordón";
    showFeedback(config?.projectionError || config?.sectorError || config?.catalogError || "");
  }

  function openingCamera() {
    if (comfort) return config.cameras?.beforeFollow || "street";
    if (config.crossing) return config.cameras?.crossing?.preset || "crossing";
    return config.cameras?.initial || "oblique";
  }

  function configureQa() {
    if (!qa || !viewer) return;
    viewer.qaConfigure(qa.connections);
    viewer.qaPoint(qa.point);
    for (const [key, visible] of Object.entries(qa.layers)) viewer.qaLayer(key, visible);
  }

  function showFeedback(message) {
    feedback.textContent = message;
    feedback.hidden = !message;
  }

  function showCameraControls() {
    const crossing = sceneActive && camera === "crossing";
    const curb = sceneActive && camera === "curb";
    const showSignals = sceneActive && viewer?.signalsAvailable && !crossing && !curb;
    pedestrianStatus.hidden = !crossing;
    curbPanel.hidden = !curb;
    legend.hidden = !config?.references.length || crossing || curb || sceneActive && camera === "signals";
    signalAssumptions.textContent = signalProgramCaption(config?.signalControllers);
    signalControl.hidden = signalAssumptions.hidden = !showSignals;
    signalLegend.hidden = !showSignals || !signalToggle.checked;
    streetReference.hidden = !sceneActive || camera !== "signals";
  }

  function selectView(use3D) {
    sceneActive = use3D;
    panel.hidden = !use3D;
    mapHost.hidden = use3D;
    mapButton.setAttribute("aria-pressed", String(!use3D));
    sceneButton.setAttribute("aria-pressed", String(use3D));
    showCameraControls();
  }

  function syncCameraButtons(followable) {
    chaseButton.disabled = !followable;
    chaseButton.setAttribute("aria-pressed", String(userCamera === "chase" && followable));
    freeButton.setAttribute("aria-pressed", String(userCamera === "free"));
    if (userCamera === "chase") {
      oblique.setAttribute("aria-pressed", "false");
      street.setAttribute("aria-pressed", "false");
      signalsCamera.setAttribute("aria-pressed", "false");
      crossingCamera.setAttribute("aria-pressed", "false");
      curbCamera.setAttribute("aria-pressed", "false");
    }
  }

  function holdPreset(preset) {
    comfort = false;
    previewFollow = null;
    previewClose = false;
    userCamera = "free";
    viewer?.setCameraMode("free");
    setCamera(preset);
  }

  function setCamera(preset) {
    camera = preset;
    oblique.setAttribute("aria-pressed", String(preset === "oblique"));
    street.setAttribute("aria-pressed", String(preset === "street"));
    signalsCamera.setAttribute("aria-pressed", String(preset === "signals"));
    crossingCamera.setAttribute("aria-pressed", String(preset === "crossing"));
    curbCamera.setAttribute("aria-pressed", String(preset === "curb"));
    showCameraControls();
    viewer?.setComfort(comfort);
    viewer?.setCamera(preset);
    if (qa?.followed != null) qa.close = true;
    if (previewFollow != null) previewClose = true;
    redraw();
  }

  const dateLabel = date => date.split("-").reverse().join("/");
  function surveyLink(title, url) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = title;
    return link;
  }

  function simulationUse(osmWay) {
    if (!osmWay) return "Solo visual";
    const lanes = new Set(Object.entries(data.laneMotion.lanes).filter(([, { edge }]) =>
      edge.replace(/^-/, "").split("#")[0] === osmWay).map(([id]) => id));
    if (!lanes.size) return "Solo visual";
    return data.frames.some(([, cars]) => cars.some(car => lanes.has(car[6])))
      ? "Con vehículos en la corrida" : "Acceso en la red de SUMO, sin vehículos en esta corrida";
  }

  function setCurbDetail(feature) {
    const properties = feature?.properties;
    const use = simulationUse(properties?.osmWay ?? (!feature ? survey.road.osmWay : null));
    curbSimulation.textContent = use + ".";
    curbDescription.textContent = properties?.detail ?? "Los indicadores identifican los accesos, las playas y los cordones pendientes.";
    const sources = (properties?.sources ?? ["street"]).map(key => {
      const { title, url, date } = survey.sources[key];
      return surveyLink(date ? `${title} · ${dateLabel(date)}` : title, url);
    });
    if (properties) {
      const [lon, lat] = properties.location;
      sources.push(surveyLink("Ver ubicación", `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=19/${lat}/${lon}`));
    }
    curbSources.replaceChildren(...sources);
  }

  function setCurbDistance(distance) {
    curbDistance.value = distance;
    const origin = config?.cameras?.curb?.origin || "el inicio";
    curbDistance.setAttribute("aria-valuetext", `${Math.round(distance)} m desde ${origin}`);
  }

  function loadCurbControls() {
    document.querySelector("#curb-title").textContent = survey.title;
    document.querySelector("#curb-reviewed").textContent = `Revisión documental · ${dateLabel(survey.reviewedAt)}`;
    curbDistance.max = viewer.curbLength;
    setCurbDistance(0);
    curbFeature.replaceChildren(new Option("Toda la cuadra", ""), ...survey.features.map(feature =>
      new Option(feature.properties.title, feature.id)));
    setCurbDetail();
  }

  mapButton.addEventListener("click", () => {
    const center = sceneActive && qa ? viewer.qaCenter() : null;
    request++;
    sceneButton.disabled = false;
    showFeedback("");
    selectView(false);
    geographicMap.resize();
    if (center) geographicMap.qaFocus(center);
    redraw();
  });
  async function openScene() {
    if (sceneActive) return true;
    const version = ++request;
    sceneButton.disabled = true;
    try {
      const pending = sectorReady;
      const ready = await pending;
      if (version !== request) return false;
      if (ready?.config) config = ready.config;
      applyChrome();
      if (config?.projectionError || config?.sectorError) {
        showFeedback(config.projectionError || config.sectorError);
        return false;
      }
      if (!config) return false;
      showFeedback("Cargando la vista 3D…");
      const firstOpen = !viewer;
      if (firstOpen) {
        const [{ createViewer3D }, street] = await Promise.all([
          import("./viewer3d.js?v=16"),
          studyRequest(`/${runId}/street-scene`),
        ]);
        if (version !== request) return false;
        const assets = ready?.assets ?? { buildings: [], survey: null, geography: null };
        const badges = createReferenceBadges(referenceHost, config.references);
        const nextViewer = await createViewer3D(canvasHost, data, config, badges, street, assets.buildings, assets.survey, assets.geography);
        nextViewer.setVehiclePick(target => {
          if (target?.kind === "signal") signalSelect?.(target);
          else if (Number.isInteger(target?.index)) vehicleSelect?.(target.index);
        });
        nextViewer.setCameraMode(userCamera);
        if (version !== request) {
          nextViewer.dispose();
          return false;
        }
        viewer = nextViewer;
        viewer.setComfort(comfort);
        const geographyNote = document.querySelector("#geography-note");
        if (geographyNote) {
          geographyNote.hidden = !viewer.hasGeography;
          geographyNote.textContent = viewer.hasGeography ? (config.dressing?.note || "Suelo según OpenStreetMap") : "";
          if (viewer.geographySummary) geographyNote.dataset.summary = JSON.stringify(viewer.geographySummary);
        }
        survey = assets.survey;
        configureQa();
        viewer.finishQaSetup();
        if (survey) loadCurbControls();
      }
      const center = qa ? geographicMap.qaCenter() : null;
      selectView(true);
      signalsCamera.hidden = !viewer.signalsAvailable;
      crossingCamera.hidden = !config.crossing;
      curbCamera.hidden = !survey;
      viewer.resize();
      if (firstOpen) setCamera(openingCamera());
      if (qa && !comfort) {
        if (qa.fitPending) setCamera("oblique");
        else if (qa.point || !firstOpen) viewer.qaFocus(center, qa.locatePending);
        qa.fitPending = qa.locatePending = false;
      }
      redraw();
      showFeedback(config.catalogError || "");
      return true;
    } catch (error) {
      console.warn("UrbanFlow: no se pudo iniciar el visor 3D.", error);
      if (version === request && data?.geographic) sectorReady = prepareStudySector(data);
      if (version !== request) return false;
      viewer?.dispose();
      viewer = null;
      const geographyNote = document.querySelector("#geography-note");
      if (geographyNote) geographyNote.hidden = true;
      selectView(false);
      geographicMap.resize();
      redraw();
      showFeedback(error instanceof Error && error.message
        ? error.message
        : "La vista 3D no pudo cargar. Podés seguir usando el mapa 2D o reintentar Vista 3D.");
      return false;
    } finally {
      if (version === request) sceneButton.disabled = false;
    }
  }
  sceneButton.addEventListener("click", () => { openScene(); });
  oblique.addEventListener("click", () => holdPreset("oblique"));
  street.addEventListener("click", () => holdPreset("street"));
  signalsCamera.addEventListener("click", () => holdPreset("signals"));
  crossingCamera.addEventListener("click", () => holdPreset("crossing"));
  curbCamera.addEventListener("click", () => holdPreset("curb"));
  chaseButton.addEventListener("click", () => {
    if (chaseButton.disabled) return;
    comfort = false;
    previewFollow = null;
    previewClose = false;
    userCamera = "chase";
    viewer?.setComfort(false);
    viewer?.setCameraMode("chase");
    syncCameraButtons(true);
    redraw();
  });
  freeButton.addEventListener("click", () => {
    comfort = false;
    previewFollow = null;
    previewClose = false;
    userCamera = "free";
    viewer?.setComfort(false);
    viewer?.setCameraMode("free");
    syncCameraButtons(!chaseButton.disabled);
    redraw();
  });
  curbDistance.addEventListener("input", () => {
    const distance = Number(curbDistance.value);
    curbFeature.value = "";
    viewer.setCurbDistance(distance);
    setCurbDistance(distance);
    setCurbDetail();
  });
  curbFeature.addEventListener("change", () => {
    const feature = survey.features.find(item => item.id === curbFeature.value);
    if (feature) setCurbDistance(viewer.focusCurbFeature(feature.properties.location));
    else viewer.setCurbDistance(Number(curbDistance.value));
    setCurbDetail(feature);
  });
  signalToggle.addEventListener("change", () => {
    showCameraControls();
    viewer?.setSignalOverlay(signalToggle.checked);
  });
  function zoom(factor) {
    viewer?.zoom(factor);
    if (qa && sceneActive) redraw();
  }
  document.querySelector("#camera-reset").addEventListener("click", () => holdPreset(camera));
  document.querySelector("#camera-zoom-in").addEventListener("click", () => zoom(.8));
  document.querySelector("#camera-zoom-out").addEventListener("click", () => zoom(1.25));
  frame.addEventListener("keydown", event => {
    if (event.target !== frame || !viewer) return;
    const directions = { ArrowLeft: [-.12, 0], ArrowRight: [.12, 0], ArrowUp: [0, -.1], ArrowDown: [0, .1] };
    if (directions[event.key]) viewer.orbit(...directions[event.key]);
    else if (event.key === "+" || event.key === "=") viewer.zoom(.8);
    else if (event.key === "-") viewer.zoom(1.25);
    else return;
    if (qa && sceneActive) redraw();
    event.preventDefault();
  });

  return {
    get active() { return sceneActive; },
    get outside() { return sceneActive ? outside : 0; },
    qaConfigure(connections) {
      qa = connections ? { connections, point: null, followed: null,
        close: false, fitPending: false, locatePending: false,
        layers: { roads: true, connections: true, signals: true, cars: true } } : null;
      configureQa();
    },
    qaFollow(id) {
      if (!qa) return;
      qa.followed = id;
      qa.close = id != null;
      if (id != null) {
        userCamera = null;
        viewer?.setCameraMode(null);
        syncCameraButtons(!chaseButton.disabled);
      }
    },
    qaFit() {
      if (!qa) return;
      qa.point = null;
      qa.locatePending = false;
      qa.fitPending = !sceneActive;
      viewer?.qaPoint(null);
      if (sceneActive) {
        if (userCamera === "chase") {
          userCamera = "free";
          viewer?.setCameraMode("free");
        }
        setCamera("oblique");
        syncCameraButtons(!chaseButton.disabled);
      }
    },
    qaLocate(point) {
      if (!qa) return;
      qa.point = point;
      qa.fitPending = false;
      qa.locatePending = !sceneActive;
      viewer?.qaPoint(point);
      if (sceneActive) {
        viewer.qaFocus(point, true);
        redraw();
      }
    },
    qaLayer(key, visible) {
      if (!qa) return;
      qa.layers[key] = visible;
      viewer?.qaLayer(key, visible);
      if (sceneActive) redraw();
    },
    configure(next, identifier) {
      request++;
      comfort = false;
      previewFollow = null;
      previewClose = false;
      userCamera = null;
      syncCameraButtons(false);
      if (sceneActive) selectView(false);
      viewer?.dispose();
      viewer = null;
      survey = null;
      qa = null;
      data = next;
      config = null;
      runId = identifier;
      const geographyNote = document.querySelector("#geography-note");
      if (geographyNote) {
        geographyNote.hidden = true;
        geographyNote.textContent = "";
      }
      legend.replaceChildren();
      legend.hidden = true;
      streetReference.hidden = true;
      switcher.hidden = !next?.geographic;
      signalsCamera.textContent = "Semáforos";
      crossingCamera.textContent = "Cruce peatonal";
      curbCamera.textContent = "Cordón";
      signalsCamera.hidden = signalControl.hidden = signalLegend.hidden = signalAssumptions.hidden = true;
      crossingCamera.hidden = pedestrianStatus.hidden = true;
      curbCamera.hidden = curbPanel.hidden = true;
      signalToggle.checked = false;
      sceneButton.disabled = false;
      showFeedback("");
      const token = next;
      sectorReady = next?.geographic ? prepareStudySector(next) : Promise.resolve(null);
      sectorReady.then(result => {
        if (data !== token) return;
        config = result?.config ?? null;
        applyChrome();
      }).catch(error => {
        if (data !== token) return;
        config = {
          bounds: next?.bounds, references: [],
          sectorError: error instanceof Error ? error.message : "No se pudo leer la configuración del sector.",
        };
        applyChrome();
      });
    },
    setApproachMarkers(visible) { viewer?.setApproachMarkers(visible); },
    setVehicleSelect(handler) { vehicleSelect = handler; },
    setSignalSelect(handler) { signalSelect = handler; },
    noteSignal(selection) { signalMark = selection; },
    noteSelection(index, present) {
      const followable = Number.isInteger(index) && present;
      if (userCamera === "chase" && !followable) {
        userCamera = "free";
        viewer?.setCameraMode("free");
      }
      syncCameraButtons(followable);
    },
    releaseFollow() {
      if (userCamera === "chase") {
        userCamera = "free";
        viewer?.setCameraMode("free");
      }
      syncCameraButtons(false);
    },
    async openPreview(vehicleIndex) {
      userCamera = null;
      comfort = true;
      previewFollow = vehicleIndex;
      const select = document.querySelector("#qa-vehicle");
      if (select && [...select.options].some(option => option.value === String(vehicleIndex))) {
        select.value = String(vehicleIndex);
        select.dispatchEvent(new Event("change"));
      }
      const opened = await openScene();
      if (opened) {
        viewer.setCameraMode(null);
        syncCameraButtons(false);
        const follow = viewer.hasGeography
          ? (config.cameras?.followWithDressing || "oblique")
          : (config.cameras?.followWithoutDressing || "street");
        setCamera(follow);
      }
      return opened;
    },
    draw(cars, highlightStopped, time, snapshot, marked) {
      if (!sceneActive) return false;
      const followedId = qa?.followed ?? previewFollow;
      const followed = followedId == null ? null : cars.find(car => car[0] === followedId);
      const close = Boolean(qa?.close || previewClose);
      const result = viewer.draw(cars, highlightStopped, time, snapshot, followed, close, marked ?? null, signalMark);
      if (followed) {
        if (qa) qa.close = false;
        previewClose = false;
      }
      outside = result.outside;
      if (!pedestrianStatus.hidden) {
        const status = result.statuses?.join("  •  ") || "Cebra despejada";
        if (pedestrianStatus.textContent !== status) pedestrianStatus.textContent = status;
      }
      return true;
    },
  };
}
