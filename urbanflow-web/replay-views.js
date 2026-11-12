"use strict";

const rooseveltPilotScene = {
  bounds: [-54.96200, -34.91665, -54.95815, -34.91395],
  streetLane: "783169882#0_0",
  signals: {
    controller: "joinedS_1360014840_13966777057_13966777058_2375592994",
    center: [-54.9614, -34.91426],
    approach: "1532518649#0_0",
  },
  references: [
    { label: "A", location: [-54.9589550, -34.9162702] },
    { label: "B", location: [-54.9593847, -34.9158082] },
  ],
};

function pilotSceneFor(data) {
  if (!data?.geographic || !data.laneMotion?.projection) return null;
  const crossing = data.pedestrianReplay?.crossing?.location;
  if (crossing) return { ...rooseveltPilotScene, crossing, bounds: [-54.962, -34.91665, -54.95675, -34.91395] };
  return data.junctionId === "r1161502532" ? rooseveltPilotScene : null;
}

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
  let data;
  let runId;
  let config;
  let viewer;
  let survey;
  let sceneActive = false;
  let camera = "oblique";
  let request = 0;

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
    legend.hidden = !config || crossing || curb || sceneActive && camera === "signals";
    signalControl.hidden = signalAssumptions.hidden = !showSignals;
    signalLegend.hidden = !showSignals || !signalToggle.checked;
  }

  function selectView(use3D) {
    sceneActive = use3D;
    panel.hidden = !use3D;
    mapHost.hidden = use3D;
    mapButton.setAttribute("aria-pressed", String(!use3D));
    sceneButton.setAttribute("aria-pressed", String(use3D));
    showCameraControls();
  }

  function setCamera(preset) {
    camera = preset;
    oblique.setAttribute("aria-pressed", String(preset === "oblique"));
    street.setAttribute("aria-pressed", String(preset === "street"));
    signalsCamera.setAttribute("aria-pressed", String(preset === "signals"));
    crossingCamera.setAttribute("aria-pressed", String(preset === "crossing"));
    curbCamera.setAttribute("aria-pressed", String(preset === "curb"));
    showCameraControls();
    viewer?.setCamera(preset);
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
    curbDistance.setAttribute("aria-valuetext", `${Math.round(distance)} m desde 18 de Julio`);
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
    request++;
    sceneButton.disabled = false;
    showFeedback("");
    selectView(false);
    geographicMap.resize();
    redraw();
  });
  sceneButton.addEventListener("click", async () => {
    if (!config || sceneActive) return;
    const version = ++request;
    sceneButton.disabled = true;
    showFeedback("Cargando la vista 3D…");
    try {
      const firstOpen = !viewer;
      if (firstOpen) {
        const [{ createViewer3D }, street, buildings, curbSurvey] = await Promise.all([
          import("./viewer3d.js"),
          studyRequest(`/${runId}/street-scene`),
          fetch("./assets/pilot-roosevelt-buildings.geojson").then(response => {
            if (!response.ok) throw new Error("No se pudo cargar el contorno de los edificios.");
            return response.json();
          }),
          fetch("./assets/terminal-curb-survey.geojson")
            .then(response => response.ok ? response.json() : null).catch(() => null),
        ]);
        if (version !== request) return;
        const badges = createReferenceBadges(referenceHost, config.references);
        const nextViewer = await createViewer3D(canvasHost, data, config, badges, street, buildings.features, createLaneMotion, curbSurvey);
        if (version !== request) {
          nextViewer.dispose();
          return;
        }
        viewer = nextViewer;
        survey = curbSurvey;
        if (survey) loadCurbControls();
      }
      selectView(true);
      signalsCamera.hidden = !viewer.signalsAvailable;
      crossingCamera.hidden = !config.crossing;
      curbCamera.hidden = !survey;
      viewer.resize();
      if (firstOpen) setCamera(config.crossing ? "crossing" : "oblique");
      else redraw();
      showFeedback("");
    } catch (error) {
      console.warn("UrbanFlow: no se pudo iniciar el visor 3D.", error);
      if (version !== request) return;
      viewer?.dispose();
      viewer = null;
      selectView(false);
      geographicMap.resize();
      redraw();
      showFeedback("La vista 3D no pudo cargar. Podés seguir usando el mapa 2D o reintentar Vista 3D.");
    } finally {
      if (version === request) sceneButton.disabled = false;
    }
  });
  oblique.addEventListener("click", () => setCamera("oblique"));
  street.addEventListener("click", () => setCamera("street"));
  signalsCamera.addEventListener("click", () => setCamera("signals"));
  crossingCamera.addEventListener("click", () => setCamera("crossing"));
  curbCamera.addEventListener("click", () => setCamera("curb"));
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
  document.querySelector("#camera-reset").addEventListener("click", () => setCamera(camera));
  document.querySelector("#camera-zoom-in").addEventListener("click", () => viewer?.zoom(.8));
  document.querySelector("#camera-zoom-out").addEventListener("click", () => viewer?.zoom(1.25));
  frame.addEventListener("keydown", event => {
    if (event.target !== frame || !viewer) return;
    const directions = { ArrowLeft: [-.12, 0], ArrowRight: [.12, 0], ArrowUp: [0, -.1], ArrowDown: [0, .1] };
    if (directions[event.key]) viewer.orbit(...directions[event.key]);
    else if (event.key === "+" || event.key === "=") viewer.zoom(.8);
    else if (event.key === "-") viewer.zoom(1.25);
    else return;
    event.preventDefault();
  });

  return {
    configure(next, identifier) {
      request++;
      if (sceneActive) selectView(false);
      viewer?.dispose();
      viewer = null;
      survey = null;
      data = next;
      runId = identifier;
      config = pilotSceneFor(next);
      switcher.hidden = legend.hidden = !config;
      signalsCamera.hidden = signalControl.hidden = signalLegend.hidden = signalAssumptions.hidden = true;
      crossingCamera.hidden = pedestrianStatus.hidden = true;
      curbCamera.hidden = curbPanel.hidden = true;
      signalToggle.checked = false;
      sceneButton.disabled = false;
      showFeedback("");
    },
    draw(cars, highlightStopped, time, snapshot) {
      if (!sceneActive) return false;
      const people = viewer.draw(cars, highlightStopped, time, snapshot);
      if (!pedestrianStatus.hidden) {
        const status = people?.join("  •  ") || "Cebra despejada";
        if (pedestrianStatus.textContent !== status) pedestrianStatus.textContent = status;
      }
      return true;
    },
  };
}
