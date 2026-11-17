"use strict";

// One UTM conversion for every visual window. The false northing is the value
// stored with the replay, read from that network's PROJ string and netOffset.
const SUMO_A = 6378137;
const SUMO_F = 1 / 298.257223563;
const SUMO_E2 = SUMO_F * (2 - SUMO_F);
const SUMO_EP2 = SUMO_E2 / (1 - SUMO_E2);
const SUMO_K0 = 0.9996;
const SUMO_FALSE_EASTING = 500000;
const SUMO_SOUTHERN_FALSE_NORTHING = 10000000;

function sumoMeridional(lat) {
  return SUMO_A * (
    (1 - SUMO_E2 / 4 - 3 * SUMO_E2 ** 2 / 64 - 5 * SUMO_E2 ** 3 / 256) * lat
    - (3 * SUMO_E2 / 8 + 3 * SUMO_E2 ** 2 / 32 + 45 * SUMO_E2 ** 3 / 1024) * Math.sin(2 * lat)
    + (15 * SUMO_E2 ** 2 / 256 + 45 * SUMO_E2 ** 3 / 1024) * Math.sin(4 * lat)
    - (35 * SUMO_E2 ** 3 / 3072) * Math.sin(6 * lat)
  );
}

function sumoForwardEquator(lonDeg, latDeg, zone) {
  const lon = lonDeg * Math.PI / 180;
  const lat = latDeg * Math.PI / 180;
  const lon0 = (-183 + 6 * zone) * Math.PI / 180;
  const sine = Math.sin(lat);
  const cosine = Math.cos(lat);
  const tangent = Math.tan(lat);
  const radius = SUMO_A / Math.sqrt(1 - SUMO_E2 * sine * sine);
  const t = tangent * tangent;
  const c = SUMO_EP2 * cosine * cosine;
  const aa = (lon - lon0) * cosine;
  const easting = SUMO_FALSE_EASTING + SUMO_K0 * radius * (
    aa + (1 - t + c) * aa ** 3 / 6
    + (5 - 18 * t + t * t + 72 * c - 58 * SUMO_EP2) * aa ** 5 / 120
  );
  const northing = SUMO_K0 * (
    sumoMeridional(lat) + radius * tangent * (
      aa * aa / 2
      + (5 - t + 9 * c + 4 * c * c) * aa ** 4 / 24
      + (61 - 58 * t + t * t + 600 * c - 330 * SUMO_EP2) * aa ** 6 / 720
    )
  );
  return [easting, northing];
}

function sumoInverseEquator(easting, northing, zone) {
  const x = easting - SUMO_FALSE_EASTING;
  const lon0 = (-183 + 6 * zone) * Math.PI / 180;
  const e1 = (1 - Math.sqrt(1 - SUMO_E2)) / (1 + Math.sqrt(1 - SUMO_E2));
  const mu = northing / SUMO_K0 / (SUMO_A * (1 - SUMO_E2 / 4 - 3 * SUMO_E2 ** 2 / 64 - 5 * SUMO_E2 ** 3 / 256));
  const lat1 = mu
    + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * Math.sin(2 * mu)
    + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * Math.sin(4 * mu)
    + (151 * e1 ** 3 / 96) * Math.sin(6 * mu)
    + (1097 * e1 ** 4 / 512) * Math.sin(8 * mu);
  const sine = Math.sin(lat1);
  const cosine = Math.cos(lat1);
  const tangent = Math.tan(lat1);
  const radius = SUMO_A / Math.sqrt(1 - SUMO_E2 * sine * sine);
  const t = tangent * tangent;
  const c = SUMO_EP2 * cosine * cosine;
  const vertical = SUMO_A * (1 - SUMO_E2) / (1 - SUMO_E2 * sine * sine) ** 1.5;
  const d = x / (radius * SUMO_K0);
  const lat = lat1 - (radius * tangent / vertical) * (
    d ** 2 / 2
    - (5 + 3 * t + 10 * c - 4 * c * c - 9 * SUMO_EP2) * d ** 4 / 24
    + (61 + 90 * t + 298 * c + 45 * t * t - 252 * SUMO_EP2 - 3 * c * c) * d ** 6 / 720
  );
  const lon = lon0 + (
    d
    - (1 + 2 * t + c) * d ** 3 / 6
    + (5 - 2 * c + 28 * t - 3 * c * c + 8 * SUMO_EP2 + 24 * t * t) * d ** 5 / 120
  ) / cosine;
  return [lon * 180 / Math.PI, lat * 180 / Math.PI];
}

function createSumoProjection(projection) {
  const zone = projection?.zone;
  const offset = projection?.netOffset;
  const falseNorthing = projection?.falseNorthing;
  if (!Number.isInteger(zone) || zone < 1 || zone > 60
      || !Array.isArray(offset) || offset.length !== 2 || offset.some(value => !Number.isFinite(value))
      || (falseNorthing !== 0 && falseNorthing !== SUMO_SOUTHERN_FALSE_NORTHING)) {
    throw new Error("La proyección UTM del replay está incompleta o usa un falso norte que no es el de UTM.");
  }
  return {
    toSumo(lon, lat) {
      const [easting, northing] = sumoForwardEquator(lon, lat, zone);
      return [easting + offset[0], northing + falseNorthing + offset[1]];
    },
    toGeo(x, y) {
      return sumoInverseEquator(x - offset[0], y - offset[1] - falseNorthing, zone);
    },
  };
}

function describeProjection(laneMotion) {
  if (!laneMotion || typeof laneMotion !== "object") {
    return { ok: false, message: "La corrida no trae la geometría de carriles, así que la vista 3D no puede abrirse." };
  }
  if (laneMotion.projectionError) return { ok: false, message: String(laneMotion.projectionError) };
  const projection = laneMotion.projection;
  if (!projection || typeof projection !== "object") {
    return { ok: false, message: "La corrida no trae una proyección geográfica, así que la vista 3D no puede abrirse." };
  }
  const numericPair = key => Array.isArray(projection[key]) && projection[key].length === 2
    && projection[key].every(Number.isFinite);
  const affine = ["east", "north", "origin", "location"].every(numericPair);
  const utm = projection.type === "utm";
  if (affine && utm) {
    return { ok: false, message: "El replay declara una proyección afín y una UTM a la vez. La vista 3D no elige entre las dos." };
  }
  if (utm) {
    try {
      createSumoProjection(projection);
    } catch (error) {
      return { ok: false, message: error.message };
    }
    return { ok: true, kind: "utm" };
  }
  if (affine) return { ok: true, kind: "affine" };
  return {
    ok: false,
    message: "La proyección del replay no está soportada. La vista 3D necesita la proyección afín guardada o UTM de SUMO.",
  };
}
