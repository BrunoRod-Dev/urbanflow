"use strict";

// One catalog for every sector. Dressing files are loaded here, attached by the
// viewer as an independent group named "geography", and released with the scene.

const preparedStudies = new WeakMap();
const jsonCache = new Map();
let sectors = [];
let catalogPromise = null;

function geographicOverlap(study, box) {
  if (!study || study.length !== 4 || !box || box.length !== 4) return false;
  return study[0] <= box[2] && study[2] >= box[0] && study[1] <= box[3] && study[3] >= box[1];
}

function boxArea(box) {
  return Math.max(0, box[2] - box[0]) * Math.max(0, box[3] - box[1]);
}

function containsPoint(box, point) {
  return point[0] >= box[0] && point[0] <= box[2] && point[1] >= box[1] && point[1] <= box[3];
}

function loadedSectors() {
  return sectors;
}

function validateSector(sector, name) {
  const missing = ["id", "bounds", "cameras", "signals", "dressing", "data"].filter(key => sector?.[key] == null);
  if (missing.length) throw new Error(`El manifiesto ${name} no trae ${missing.join(", ")}.`);
  if (!Array.isArray(sector.bounds) || sector.bounds.length !== 4) {
    throw new Error(`El manifiesto ${name} no trae límites geográficos.`);
  }
  if (!Array.isArray(sector.signals)) throw new Error(`El manifiesto ${name} no trae la lista de semáforos.`);
  const unknown = sector.signals.filter(item => !["inferred", "validated", "partial"].includes(item?.program));
  if (unknown.length) {
    throw new Error(`El manifiesto ${name} tiene un programa semafórico no reconocido.`);
  }
}

function sectorSelection(list, study) {
  const available = Array.isArray(list) ? list : [];
  if (!study || typeof study !== "object") return { sector: null, error: "" };
  if (study.sectorId) {
    const found = available.filter(sector => sector.id === study.sectorId);
    if (found.length > 1) return { sector: null, error: `Varios manifiestos usan el identificador ${study.sectorId}.` };
    if (!found.length) return { sector: null, error: `El estudio pide el sector ${study.sectorId} y ese manifiesto no está cargado.` };
    return { sector: found[0], error: "" };
  }
  const junctions = study.junctionId
    ? available.filter(sector => (sector.match?.junctionIds ?? []).includes(study.junctionId))
    : [];
  if (junctions.length > 1) return { sector: null, error: `Varios sectores reclaman el cruce ${study.junctionId}.` };
  if (study.pedestrianReplay?.crossing) {
    const flagged = available.filter(sector => sector.match?.pedestrianCrossing);
    if (flagged.length > 1) return { sector: null, error: "Varios sectores reclaman la cámara de cruce peatonal." };
    if (flagged.length === 1) return { sector: flagged[0], error: "" };
  }
  if (junctions.length === 1) return { sector: junctions[0], error: "" };
  const box = study.bounds;
  if (!Array.isArray(box) || box.length !== 4) return { sector: null, error: "" };
  const overlapping = available.filter(sector => sector.match?.bounds
    && Array.isArray(sector.bounds) && geographicOverlap(box, sector.bounds));
  const location = Array.isArray(study.location) ? study.location : null;
  const containing = location ? overlapping.filter(sector => containsPoint(sector.bounds, location)) : [];
  const pool = (containing.length ? containing : overlapping).slice()
    .sort((left, right) => boxArea(left.bounds) - boxArea(right.bounds));
  if (pool.length > 1 && boxArea(pool[0].bounds) === boxArea(pool[1].bounds)) {
    return { sector: null, error: `Los sectores ${pool[0].id} y ${pool[1].id} cubren la misma zona.` };
  }
  return { sector: pool[0] ?? null, error: "" };
}

function sectorForStudy(study) {
  return sectorSelection(sectors, study).sector;
}

function sectorForHash(hash) {
  const found = sectors.filter(sector => (sector.match?.hashes ?? []).includes(hash));
  if (found.length > 1) return { sector: null, error: "Varios sectores usan la misma dirección de demostración." };
  return { sector: found[0] ?? null, error: "" };
}

function genericScene(study) {
  return {
    bounds: study.bounds,
    references: [],
    pilot: false,
    crossing: null,
    streetLane: null,
    signals: null,
    signalControllers: [],
    cameras: {
      initial: "oblique", beforeFollow: "street", followWithDressing: "oblique",
      followWithoutDressing: "street", signalsLabel: "Semáforos del cruce",
    },
    dressing: {},
    messages: {},
    features: [],
    sectorId: null,
  };
}

function sceneFromSector(study, sector) {
  const crossing = study.pedestrianReplay?.crossing?.location ?? null;
  const cameras = sector.cameras ?? {};
  const cameraSignal = (sector.signals ?? []).find(item => item.camera && item.center && item.approach);
  const bounds = crossing && cameras.crossing?.bounds
    ? cameras.crossing.bounds
    : sector.frame === "declared" ? sector.bounds : study.bounds;
  return {
    bounds,
    references: (sector.landmarks ?? []).map(item => ({ label: item.label, location: item.location, title: item.title })),
    pilot: sector.scene === "pilot",
    crossing: crossing && cameras.crossing ? crossing : null,
    streetLane: cameras.streetLane || null,
    signals: cameraSignal
      ? { controller: cameraSignal.id, center: cameraSignal.center, approach: cameraSignal.approach }
      : null,
    signalControllers: sector.signals ?? [],
    cameras,
    dressing: sector.dressing ?? {},
    messages: sector.messages ?? {},
    features: sector.features ?? [],
    sectorId: sector.id,
  };
}

function sceneFor(study) {
  return study ? sceneForStudy(study) : null;
}

function sceneForStudy(study, list) {
  if (!study?.geographic) return null;
  const described = describeProjection(study.laneMotion);
  if (!described.ok) return { bounds: study.bounds, references: [], projectionError: described.message };
  const selection = sectorSelection(list ?? sectors, study);
  if (selection.error) return { bounds: study.bounds, references: [], sectorError: selection.error };
  if (!selection.sector) {
    if (!study.bounds || !study.location) return null;
    return genericScene(study);
  }
  return sceneFromSector(study, selection.sector);
}

function signalProgramCaption(controllers) {
  const list = Array.isArray(controllers) ? controllers : [];
  if (!list.length) return " · Semáforos estimados";
  const unknown = list.filter(item => !["inferred", "validated", "partial"].includes(item?.program));
  if (unknown.length) {
    return ` · El manifiesto no dice si el programa de ${unknown.map(item => item.id).join(", ")} está inferido o contrastado.`;
  }
  const validated = list.filter(item => item.program === "validated");
  const partial = list.filter(item => item.program === "partial");
  if (validated.length === list.length) return " · Programa contrastado en campo";
  if (validated.length) {
    const label = validated.length === 1 ? "programa contrastado" : "programas contrastados";
    return ` · ${validated.length} ${label} en campo. El resto es estimado.`;
  }
  if (partial.length) {
    const note = partial.find(item => item.fieldNote)?.fieldNote;
    return note ? ` · ${note}` : " · Semáforos estimados, con movimientos contrastados en campo";
  }
  return " · Semáforos estimados";
}

async function readJson(url) {
  if (jsonCache.has(url)) return jsonCache.get(url);
  const pending = (async () => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`No se pudo leer ${url}.`);
    return response.json();
  })();
  jsonCache.set(url, pending);
  try {
    return await pending;
  } catch (error) {
    jsonCache.delete(url);
    throw error;
  }
}

async function loadSectorCatalog() {
  if (!catalogPromise) {
    catalogPromise = readCatalog().catch(error => {
      catalogPromise = null;
      sectors = [];
      throw error;
    });
  }
  return catalogPromise;
}

async function readCatalog() {
  const index = await readJson("./sectors/index.json?v=1");
  const names = index?.sectors;
  if (!Array.isArray(names) || names.some(name => typeof name !== "string" || name.includes("/") || name.includes(".."))) {
    throw new Error("El índice de sectores no trae una lista de manifiestos.");
  }
  const list = await Promise.all(names.map(async name => {
    const sector = await readJson(`./sectors/${name}?v=1`);
    validateSector(sector, name);
    return sector;
  }));
  if (new Set(list.map(sector => sector.id)).size !== list.length) {
    throw new Error("Hay dos manifiestos con el mismo identificador de sector.");
  }
  sectors = list;
  return list;
}

async function loadDeclaredAssets(study, config) {
  const dressing = config?.dressing ?? {};
  async function optional(url) {
    if (!url) return null;
    try {
      return await readJson(url);
    } catch {
      return null;
    }
  }
  const buildings = dressing.buildings
    ? readJson(dressing.buildings).catch(() => {
      throw new Error("No se pudo cargar el contorno de los edificios.");
    })
    : null;
  const [buildingsFile, survey, geographyFile, extensionFile] = await Promise.all([
    buildings,
    optional(dressing.curbSurvey),
    optional(dressing.geography),
    optional(dressing.geographyExtension),
  ]);
  const geography = geographyFile && geographicOverlap(study?.bounds, geographyFile.meta?.bounds) ? geographyFile : null;
  const geographyExtension = geography && extensionFile &&
    geographicOverlap(study?.bounds, extensionFile.meta?.bounds) ? extensionFile : null;
  return { buildings: buildingsFile?.features ?? [], survey, geography, geographyExtension, demo: geography?.demo ?? null };
}

function prepareStudySector(study) {
  if (!study || typeof study !== "object") return Promise.resolve(null);
  const cached = preparedStudies.get(study);
  if (cached) return cached;
  const pending = buildPreparedSector(study).catch(error => {
    preparedStudies.delete(study);
    throw error;
  });
  preparedStudies.set(study, pending);
  return pending;
}

async function buildPreparedSector(study) {
  let list = [];
  let catalogError = "";
  try {
    list = await loadSectorCatalog();
  } catch (error) {
    catalogError = error instanceof Error ? error.message : "No se pudo leer el manifiesto de sectores.";
  }
  const config = sceneForStudy(study, list);
  if (config && catalogError && !config.projectionError && !config.sectorError) config.catalogError = catalogError;
  if (!config || config.projectionError || config.sectorError) {
    return { config, demo: null, assets: { buildings: [], survey: null, geography: null, demo: null } };
  }
  const assets = await loadDeclaredAssets(study, config);
  return { config, demo: assets.demo, assets };
}
