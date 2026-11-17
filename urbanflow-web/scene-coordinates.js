// Use the recorded SUMO projection, centered near the junction.
function utmSceneCoordinates(converter, center) {
  const origin = converter.toSumo(center[0], center[1]);
  const [lng0, lat0] = converter.toGeo(origin[0], origin[1]);
  const [lngX, latX] = converter.toGeo(origin[0] + 1, origin[1]);
  const [lngY, latY] = converter.toGeo(origin[0], origin[1] + 1);
  const east = [lngX - lng0, latX - lat0];
  const north = [lngY - lng0, latY - lat0];
  const determinant = east[0] * north[1] - east[1] * north[0];
  if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-15) {
    throw new Error("La proyección UTM no tiene ejes válidos para orientar los vehículos.");
  }
  const invert = (lng, lat) => [
    (lng * north[1] - lat * north[0]) / determinant,
    (east[0] * lat - east[1] * lng) / determinant,
  ];
  return {
    fromSumo([x, y]) {
      return [x - origin[0], y - origin[1]];
    },
    fromGeo([lng, lat]) {
      const [x, y] = converter.toSumo(lng, lat);
      return [x - origin[0], y - origin[1]];
    },
    toGeo([x, y]) {
      return converter.toGeo(x + origin[0], y + origin[1]);
    },
    bearing(lat, heading) {
      const angle = heading * Math.PI / 180;
      const [x, y] = invert(Math.sin(angle) / Math.cos(lat * Math.PI / 180), Math.cos(angle));
      return -Math.atan2(x, y);
    },
  };
}

export function createSceneCoordinates(projection, center) {
  if (projection?.type === "utm") {
    const create = globalThis.createSumoProjection;
    if (typeof create !== "function") {
      throw new Error("Falta la conversión UTM del visor. La vista 3D no puede abrir esta corrida.");
    }
    return utmSceneCoordinates(create(projection), center);
  }
  const { origin, location, east, north } = projection;
  const determinant = east[0] * north[1] - east[1] * north[0];
  if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-15) {
    throw new Error("La corrida no tiene una proyección válida para la vista 3D.");
  }
  const invert = (lng, lat) => [
    (lng * north[1] - lat * north[0]) / determinant,
    (east[0] * lat - east[1] * lng) / determinant,
  ];
  const shift = invert(center[0] - location[0], center[1] - location[1]);
  const sumoCenter = [origin[0] + shift[0], origin[1] + shift[1]];
  return {
    fromSumo([x, y]) {
      return [x - sumoCenter[0], y - sumoCenter[1]];
    },
    fromGeo([lng, lat]) {
      return invert(lng - center[0], lat - center[1]);
    },
    toGeo([x, y]) {
      return center.map((value, axis) => value + x * east[axis] + y * north[axis]);
    },
    bearing(lat, heading) {
      const angle = heading * Math.PI / 180;
      const [x, y] = invert(Math.sin(angle) / Math.cos(lat * Math.PI / 180), Math.cos(angle));
      return -Math.atan2(x, y);
    },
  };
}

export function sceneBounds(geographicBounds, coordinates) {
  const [west, south, east, north] = geographicBounds;
  const corners = [[west, south], [west, north], [east, south], [east, north]].map(coordinates.fromGeo);
  return [0, 1].map(axis => {
    const values = corners.map(point => point[axis]);
    return [Math.min(...values), Math.max(...values)];
  });
}

export function vehicleScenePose([, lng, lat, heading], coordinates) {
  const [x, y] = coordinates.fromGeo([lng, lat]);
  return [x, y, coordinates.bearing(lat, heading)];
}
