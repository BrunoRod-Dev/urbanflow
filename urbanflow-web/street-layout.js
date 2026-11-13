import Clipper from "clipper-lib";

const SCALE = 1000;
const { ClipType, EndType, JoinType, PolyFillType, PolyType } = Clipper;
export const streetDimensions = { lane: 3.2, sidewalk: 2, curb: .15, curbWidth: .16 };

const integerPoint = ([x, y]) => ({ X: Math.round(x * SCALE), Y: Math.round(y * SCALE) });
const meters = ({ X, Y }) => [X / SCALE, Y / SCALE];

function ring(points) {
  const path = Clipper.Clipper.CleanPolygon(points.map(integerPoint), 8);
  return Clipper.Clipper.Orientation(path) ? path : path.reverse();
}

function buffer(paths, width, end) {
  const operation = new Clipper.ClipperOffset(2, 45);
  const result = [];
  operation.AddPaths(paths, JoinType.jtRound, end);
  operation.Execute(result, width * SCALE);
  return result;
}

function overlay(kind, subjects, clips = []) {
  if (!subjects.length) return [];
  const operation = new Clipper.Clipper();
  operation.AddPaths(subjects, PolyType.ptSubject, true);
  if (clips.length) operation.AddPaths(clips, PolyType.ptClip, true);
  const result = new Clipper.PolyTree();
  operation.Execute(kind, result, PolyFillType.pftNonZero, PolyFillType.pftNonZero);
  return Clipper.JS.PolyTreeToExPolygons(result);
}

const pathsFrom = polygons => polygons.flatMap(({ outer, holes }) => [outer, ...holes]);
const asMeters = polygons => polygons.map(({ outer, holes }) => ({ outer: outer.map(meters), holes: holes.map(path => path.map(meters)) }));
const area = polygon => Math.abs(Clipper.Clipper.Area(polygon));

function hull(points) {
  const ordered = points.map(integerPoint).sort((a, b) => a.X - b.X || a.Y - b.Y);
  const half = sorted => {
    const result = [];
    for (const point of sorted) {
      while (result.length >= 2) {
        const [a, b] = result.slice(-2);
        if ((b.X - a.X) * (point.Y - a.Y) > (b.Y - a.Y) * (point.X - a.X)) break;
        result.pop();
      }
      result.push(point);
    }
    return result.slice(0, -1);
  };
  return [...half(ordered), ...half(ordered.reverse())];
}

function inferredIslands(holes, roundabouts, coordinates) {
  return roundabouts.flatMap(roundabout => {
    const ringPath = ring(roundabout.points.map(coordinates.fromSumo));
    const match = holes.filter(hole => overlay(ClipType.ctIntersection, [hole], [ringPath])
      .some(({ outer }) => area(outer) >= area(hole) * .8)).sort((a, b) => area(b) - area(a))[0];
    return match ? [{ ...roundabout, path: match }] : [];
  });
}

function touchesScene(points, bounds, margin) {
  return bounds.every(([min, max], axis) => points.some(point => point[axis] >= min - margin)
    && points.some(point => point[axis] <= max + margin));
}

function arrowOnLane(points, turn) {
  if (!['left', 'right', 'through'].includes(turn)) return null;
  let distance = 6;
  for (let index = points.length - 1; index > 0; index--) {
    const [a, b] = [points[index - 1], points[index]];
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (length <= distance) {
      distance -= length;
      continue;
    }
    const forward = [(b[0] - a[0]) / length, (b[1] - a[1]) / length];
    const origin = b.map((value, axis) => value - distance * forward[axis]);
    const local = (right, ahead) => [origin[0] + forward[0] * ahead + forward[1] * right,
      origin[1] + forward[1] * ahead - forward[0] * right];
    const arrow = turn === 'through'
      ? [[-.12, -1.25], [.12, -1.25], [.12, .43], [.4, .43], [0, 1.2], [-.4, .43], [-.12, .43]]
      : [[-.11, -1.25], [.11, -1.25], [.11, .28], [.53, .28], [.53, .06], [1.05, .45], [.53, .84], [.53, .6], [-.11, .6]];
    return ring(arrow.map(([right, ahead]) => local(turn === 'left' ? -right : right, ahead)));
  }
  return null;
}

function zebraStripes(points, width = 2.4) {
  const stripes = [];
  let traveled = 0;
  let next = .25;
  for (let index = 1; index < points.length; index++) {
    const [a, b] = [points[index - 1], points[index]];
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (length < .01) continue;
    const dx = (b[0] - a[0]) / length;
    const dy = (b[1] - a[1]) / length;
    while (next <= traveled + length) {
      const x = a[0] + (next - traveled) * dx;
      const y = a[1] + (next - traveled) * dy;
      const halfWidth = width / 2;
      stripes.push(ring([[-.2, -halfWidth], [.2, -halfWidth], [.2, halfWidth], [-.2, halfWidth]]
        .map(([u, v]) => [x + u * dx - v * dy, y + u * dy + v * dx])));
      next += .85;
    }
    traveled += length;
  }
  return stripes;
}

function zebraFromNode(point, segments) {
  let nearest;
  let distance = 4;
  for (const [a, b] of segments) {
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const length = Math.hypot(dx, dy);
    if (length < .01) continue;
    const along = Math.max(0, Math.min(length, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length));
    const gap = Math.hypot(point[0] - a[0] - along * dx / length, point[1] - a[1] - along * dy / length);
    if (gap >= distance) continue;
    distance = gap;
    nearest = [-dy / length, dx / length];
  }
  if (!nearest) return [];
  return zebraStripes([-7, 7].map(offset => point.map((value, axis) => value + nearest[axis] * offset)));
}

function paintStrip(a, dx, dy, start, end, left, right) {
  return ring([[start, left], [end, left], [end, right], [start, right]]
    .map(([along, offset]) => [a[0] + along * dx - offset * dy, a[1] + along * dy + offset * dx]));
}

function laneDividers(points, offset) {
  const stripes = [];
  let traveled = 0;
  const finish = points.slice(1).reduce((sum, p, index) => sum + Math.hypot(p[0] - points[index][0],
    p[1] - points[index][1]), 0) - 2.5;
  for (let index = 1; index < points.length && traveled < finish; index++) {
    const [a, b] = [points[index - 1], points[index]];
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (length < .01) continue;
    const dx = (b[0] - a[0]) / length;
    const dy = (b[1] - a[1]) / length;
    const limit = Math.min(traveled + length, finish);
    const first = 2.5 + Math.max(0, Math.floor((traveled - 2.5) / 6)) * 6;
    for (let start = first; start < limit; start += 6) {
      const from = Math.max(start, traveled);
      const to = Math.min(start + 2.8, limit);
      if (to - from > .02) stripes.push(paintStrip(a, dx, dy, from - traveled, to - traveled, offset - .065, offset + .065));
    }
    traveled += length;
  }
  return stripes;
}

function stopLine(points, halfWidth) {
  const b = points.at(-1);
  const a = points.findLast(point => Math.hypot(b[0] - point[0], b[1] - point[1]) >= .3);
  if (!a) return null;
  const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
  return paintStrip(b, (b[0] - a[0]) / length, (b[1] - a[1]) / length, -.48, -.22, halfWidth - .12, -halfWidth + .12);
}

export function buildStreetLayout(lanes, street, buildings, coordinates, bounds, survey) {
  const [[west, east], [south, north]] = bounds;
  const border = [ring([[west, south], [east, south], [east, north], [west, north]])];
  const paved = [];
  const sidewalkExclusions = [];
  const pedestrianLinks = (street.sidewalkAreas ?? []).map(points => ring(points.map(coordinates.fromSumo)));
  for (const { points } of street.sidewalkLines ?? []) {
    const line = points.map(coordinates.fromGeo);
    if (touchesScene(line, bounds, 3)) pedestrianLinks.push(...buffer([line.map(integerPoint)], streetDimensions.sidewalk / 2, EndType.etOpenRound));
  }
  const paint = [];
  const roadSegments = [];
  const signalLanes = new Set(street.signalLinks?.filter(link => !link.insideJunction).map(link => link.fromLane));
  for (const [id, lane] of Object.entries(lanes)) {
    const points = lane.points.map(coordinates.fromSumo);
    if (points.length < 2 || !touchesScene(points, bounds, 5)) continue;
    const line = [points.map(integerPoint)];
    const pedestrianLane = street.pedestrianLanes?.[id];
    if (pedestrianLane) {
      const width = street.widths[id] ?? streetDimensions.sidewalk;
      if (pedestrianLane === "crossing") paint.push(...zebraStripes(points, width));
      else if (pedestrianLane === "walkingarea" && points.length >= 3) pedestrianLinks.push(ring(points));
      else pedestrianLinks.push(...buffer(line, width / 2, EndType.etOpenRound));
      continue;
    }
    const halfWidth = (street.widths[id] ?? streetDimensions.lane) / 2;
    paved.push(...buffer(line, halfWidth + .04, EndType.etOpenRound));
    if (!lane.edge.startsWith(':')) points.slice(1).forEach((point, index) => roadSegments.push([points[index], point]));
    const tags = street.markings[lane.edge];
    if (tags?.sidewalk === 'no') sidewalkExclusions.push(...buffer(line, halfWidth + streetDimensions.sidewalk, EndType.etOpenButt));
    for (const side of tags?.sidewalkSides ?? []) {
      const offset = side === 'left' ? 1 : -1;
      for (let index = 1; index < points.length; index++) {
        const [a, b] = [points[index - 1], points[index]];
        const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
        if (length < .01) continue;
        pedestrianLinks.push(paintStrip(a, (b[0] - a[0]) / length, (b[1] - a[1]) / length, 0, length,
          offset * (halfWidth + streetDimensions.sidewalk), offset * halfWidth));
      }
    }
    const laneNumber = Number(id.slice(id.lastIndexOf('_') + 1));
    if (tags?.laneMarkings !== 'no') {
      const arrow = arrowOnLane(points, tags?.turns[laneNumber]);
      if (arrow) paint.push(arrow);
      if (lanes[`${lane.edge}_${laneNumber + 1}`] && !lane.edge.startsWith(':')) {
        paint.push(...laneDividers(points, halfWidth));
      }
    }
    const lineMark = signalLanes.has(id) && stopLine(points, halfWidth);
    if (lineMark) paint.push(lineMark);
  }
  for (const polygon of street.junctions) {
    const points = polygon.map(coordinates.fromSumo);
    if (touchesScene(points, bounds, 5)) paved.push(ring(points));
  }
  if (survey) {
    const modeledWays = new Set(Object.values(lanes).map(({ edge }) => edge.replace(/^-/, "").split("#")[0]));
    const pavement = (points, width) => buffer([points.map(coordinates.fromGeo).map(integerPoint)], width / 2, EndType.etOpenRound);
    if (!modeledWays.has(survey.road.osmWay)) paved.push(...pavement(survey.road.coordinates, survey.road.width));
    for (const { properties, geometry } of survey.features) {
      if (properties.kind === "access" && !modeledWays.has(properties.osmWay)) {
        paved.push(...pavement(geometry.coordinates, properties.width));
      } else if (properties.kind === "parking") {
        paved.push(ring(geometry.coordinates[0].map(coordinates.fromGeo)));
      }
    }
  }

  const initialRoads = overlay(ClipType.ctIntersection, paved, border);
  const gaps = initialRoads.flatMap(({ holes }) => holes.map(hole => [...hole].reverse()));
  const roundabouts = inferredIslands(gaps, street.roundabouts ?? [], coordinates);
  const roundaboutGaps = new Set(roundabouts.map(({ path }) => path));
  const envelopes = (street.junctionGroups ?? []).map(group => group.map(coordinates.fromSumo))
    .filter(points => touchesScene(points, bounds, 5)).map(hull).filter(path => path.length >= 3);
  const openJunctions = gaps.filter(gap => !roundaboutGaps.has(gap))
    .flatMap(gap => pathsFrom(overlay(ClipType.ctIntersection, [gap], envelopes)));
  const mapped = (street.physicalSurfaces ?? []).filter(surface => surface.layer === '0')
    .map(surface => ({ ...surface, points: surface.points.map(coordinates.fromGeo) }))
    .filter(surface => touchesScene(surface.points, bounds, 5))
    .map(surface => ({ ...surface, path: ring(surface.points) }));
  const physical = [...mapped, ...roundabouts];
  const roads = overlay(ClipType.ctDifference,
    pathsFrom(overlay(ClipType.ctUnion, [...pathsFrom(initialRoads), ...openJunctions])), physical.map(({ path }) => path));
  const asphalt = pathsFrom(roads);
  const outsideRoads = roads.map(road => road.outer);
  const walkSurface = buffer(outsideRoads, streetDimensions.sidewalk, EndType.etClosedPolygon);
  const mappedPaths = kind => mapped.filter(surface => surface.kind === kind).map(({ path }) => path);
  const islands = overlay(ClipType.ctIntersection, [...mappedPaths('island'), ...roundaboutGaps], border);
  for (const crossing of street.crossings) {
    const points = crossing.points.map(coordinates.fromGeo);
    pedestrianLinks.push(...buffer([points.map(integerPoint)], .85, EndType.etOpenRound));
    if (crossing.zebra) paint.push(...zebraStripes(points));
  }
  for (const crossing of street.nodeCrossings ?? []) paint.push(...zebraFromNode(coordinates.fromGeo(crossing.point), roadSegments));
  const edgeSidewalks = overlay(ClipType.ctDifference, walkSurface, [...outsideRoads, ...sidewalkExclusions]);
  const crossingApproaches = overlay(ClipType.ctDifference, pedestrianLinks, asphalt);
  const walks = [...pathsFrom(edgeSidewalks), ...pathsFrom(crossingApproaches), ...mappedPaths('sidewalk')];
  const sidewalks = overlay(ClipType.ctDifference, pathsFrom(overlay(ClipType.ctIntersection, walks, border)), pathsFrom(islands));
  const curbHoles = roads.flatMap(({ holes }) => holes.filter(hole => physical.some(({ path }) =>
    overlay(ClipType.ctIntersection, [hole], [path]).some(({ outer }) => area(outer) >= area(hole) * .8))));
  const curbBoundaries = [...outsideRoads, ...curbHoles];
  const curbSurface = overlay(ClipType.ctDifference,
    buffer(curbBoundaries, streetDimensions.curbWidth, EndType.etClosedPolygon), curbBoundaries);
  const curbs = overlay(ClipType.ctIntersection, pathsFrom(curbSurface), border);
  const markingPolygons = overlay(ClipType.ctIntersection, paint, asphalt);

  const occupied = pathsFrom(overlay(ClipType.ctUnion, [...asphalt, ...pathsFrom(sidewalks)]));
  const structures = buildings.flatMap(feature => {
    const contour = ring(feature.geometry.coordinates[0].map(coordinates.fromGeo));
    const clipped = overlay(ClipType.ctIntersection, [contour], border);
    const footprints = overlay(ClipType.ctDifference, pathsFrom(clipped), occupied);
    const levels = Number(feature.properties['building:levels']);
    const height = Number.isFinite(levels) && levels > 0 ? levels * 3.1 : 6;
    return asMeters(footprints).map(polygon => ({ ...polygon, height, osmWay: feature.properties.osmWay }));
  });
  return {
    roads: asMeters(roads), sidewalks: asMeters(sidewalks), islands: asMeters(islands), curbs: asMeters(curbs),
    curbBoundaries: curbBoundaries.map(path => path.map(meters)),
    physicalSurfaces: physical.map(({ id, kind, source, estimated, path }) => ({ id, kind, source, estimated, outline: path.map(meters) })),
    markings: asMeters(markingPolygons), structures,
  };
}
