// Use the recorded SUMO projection, centered near the junction.
export function createSceneCoordinates(projection, center) {
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

