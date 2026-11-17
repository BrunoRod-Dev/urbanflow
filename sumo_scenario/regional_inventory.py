"""Build an offline regional road inventory from the shared OSM snapshot."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from heapq import heappop, heappush
import json
from math import cos, hypot, radians
from pathlib import Path

from .regional_map import SNAPSHOT, regional_network


ROADS = set('motorway trunk primary secondary tertiary unclassified residential service living_street road'.split())
ROADS |= {kind + '_link' for kind in ('motorway', 'trunk', 'primary', 'secondary', 'tertiary')}
ATTRIBUTES = ('name', 'ref', 'lanes', 'maxspeed', 'surface', 'oneway')


def tags(element):
    return {tag.attrib['k']: tag.attrib['v'] for tag in element.findall('tag')}


def meters(a, b):
    return 111320 * hypot((b[0] - a[0]) * cos(radians((a[1] + b[1]) / 2)), b[1] - a[1])


def direction(info):
    value = info.get('oneway')
    if value in ('yes', '1', 'true'):
        return 'forward'
    if value == '-1':
        return 'reverse'
    if value in ('no', '0', 'false'):
        return 'both'
    if value is not None or 'oneway:conditional' in info:
        return 'unknown'
    if info.get('junction') in ('roundabout', 'circular') or info.get('highway') == 'motorway':
        return 'inferred-forward'
    return 'inferred-both'


def road_segments(ways, points):
    segments, missing = {}, []
    for way, (element, refs) in ways.items():
        info = tags(element)
        if info.get('highway') not in ROADS or info.get('area') == 'yes':
            continue
        for index, (a, b) in enumerate(zip(refs, refs[1:])):
            key = f'{way}:{index}'
            if a not in points or b not in points:
                missing.append(key)
            elif a != b:
                segments[key] = (way, a, b, info)
    return segments, missing


def road_graph(segments, points):
    graph = defaultdict(list)
    for key, (_, a, b, info) in segments.items():
        access = next((info[k] for k in ('motorcar', 'motor_vehicle', 'vehicle', 'access') if k in info), None)
        if access in ('no', 'private', 'destination', 'customers', 'delivery'):
            continue
        sense = direction(info)
        if sense == 'unknown':
            continue
        length = meters(points[a], points[b])
        if sense != 'reverse':
            graph[a].append((b, key, length))
        if not sense.endswith('forward'):
            graph[b].append((a, key, length))
    return graph


def route(graph, segments, start, end, preferred, forbidden=(), blocked_nodes=()):
    """Find a candidate over connected directed segments, favoring the named corridor."""
    distance = {start: 0}
    parents = {}
    queue = [(0, start)]
    while queue:
        cost, node = heappop(queue)
        if node == end:
            break
        if cost != distance[node]:
            continue
        for following, key, length in graph.get(node, ()):
            if following in blocked_nodes:
                continue
            info = segments[key][3]
            name = info.get('name', '').casefold()
            if any(term in name for term in forbidden):
                continue
            penalty = 1 if any(term in name for term in preferred) else 8
            kind = info['highway'].removesuffix('_link')
            if kind == 'service':
                penalty *= 12
            elif kind not in ('motorway', 'trunk', 'primary', 'secondary', 'tertiary'):
                penalty *= 3
            total = cost + length * penalty
            if total < distance.get(following, float('inf')):
                distance[following] = total
                parents[following] = node, key
                heappush(queue, (total, following))
    if end not in distance:
        raise ValueError(f'Sin conexión OSM dirigida de {start} a {end}')
    steps = []
    while end != start:
        parent, key = parents[end]
        steps.append((key, parent, end))
        end = parent
    return steps[::-1]


def interior_faces(paths, points):
    from shapely.geometry import MultiLineString
    from shapely.ops import polygonize_full

    # Remove immediate retracing of identical OSM segments, including access spurs.
    unique = {key: (a, b) for path in paths for key, a, b in path}
    lines = MultiLineString([(points[a], points[b]) for a, b in unique.values()])
    return polygonize_full(lines)


def roundabout_selection(ways, segments, points, locations):
    """Find OSM roundabout components and retain complete rings and incident ways at the border."""
    ring_ways = {way: refs for way, (element, refs) in ways.items()
                 if refs and tags(element).get('junction') == 'roundabout'}
    ring_by_node = defaultdict(set)
    for way, refs in ring_ways.items():
        for node in refs:
            ring_by_node[node].add(way)
    keys_by_way, approaches_by_node = defaultdict(set), defaultdict(set)
    for key, (way, a, b, _) in segments.items():
        keys_by_way[way].add(key)
        if way not in ring_ways:
            approaches_by_node[a].add(way)
            approaches_by_node[b].add(way)

    pending = set(ring_ways)
    groups, required = [], set()
    while pending:
        first = min(pending)
        pending.remove(first)
        stack, members, nodes = [first], {first}, set()
        while stack:
            way = stack.pop()
            for node in ring_ways[way]:
                if node in nodes:
                    continue
                nodes.add(node)
                linked = ring_by_node[node] & pending
                pending.difference_update(linked)
                members.update(linked)
                stack.extend(linked)

        ring_keys = set().union(*(keys_by_way[way] for way in members))
        outside = {key for key in ring_keys if locations[key] == 'outside'}
        missing = sorted(node for node in nodes if node not in points)
        incoming, outgoing = Counter(), Counter()
        for key in ring_keys:
            _, a, b, info = segments[key]
            sense = direction(info)
            if sense == 'reverse':
                a, b = b, a
            if sense in ('forward', 'inferred-forward', 'reverse'):
                outgoing[a] += 1
                incoming[b] += 1
        complete = not missing and all(incoming[node] == outgoing[node] == 1 for node in nodes)
        touched = bool(ring_keys - outside)
        row = {'ringWays': sorted(members), 'completeDirectedCycle': complete, 'missingNodes': missing,
               'ringSegments': len(ring_keys), 'outsideRingSegments': len(outside), 'intersectsSelection': touched}
        if touched and (outside or not complete):
            approaches = set().union(*(approaches_by_node[node] for node in nodes))
            preserve = ring_keys | set().union(*(keys_by_way[way] for way in approaches))
            expanded = {key for key in preserve if locations[key] == 'outside'}
            coordinates = [points[node] for key in preserve for node in segments[key][1:3]]
            xs, ys = zip(*coordinates)
            row.update(approachWays=sorted(approaches), preserveWays=sorted(members | approaches),
                       expansionSegments=sorted(expanded), requiredBounds=[min(xs), min(ys), max(xs), max(ys)])
            required.update(expanded)
        groups.append(row)
    return groups, required


def audit_joins(specs, paths, segments, restrictions):
    rows = []
    for spec in specs:
        node = spec['node']
        before, after = paths[spec['from']], paths[spec['to']]
        if spec['from'] == spec['to']:
            pairs = [(left, right) for left, right in zip(before, before[1:]) if left[2] == node]
        else:
            pairs = [(before[-1], after[0])] if before[-1][2] == after[0][1] == node else []
        if len(pairs) != 1:
            raise ValueError(f'Empalme ausente o ambiguo: {spec["id"]} en {node}.')
        pair = pairs[0]
        rows.append({**spec, 'steps': pair, 'wayIds': [segments[step[0]][0] for step in pair],
                     'directions': [direction(segments[step[0]][3]) for step in pair],
                     'restrictionReview': restriction_candidates(pair, segments, restrictions)})
    return rows


def weak_components(neighbors_by_node):
    remaining = set(neighbors_by_node)
    components = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        stack = [start]
        size = 0
        while stack:
            current = stack.pop()
            size += 1
            neighbors = neighbors_by_node[current] & remaining
            remaining.difference_update(neighbors)
            stack.extend(neighbors)
        components.append({'sampleNode': start, 'nodes': size})
    return sorted(components, key=lambda component: -component['nodes'])


def build(plan, output):
    from shapely.geometry import LineString, Point, mapping
    from shapely.ops import unary_union
    from shapely.prepared import prep

    source, nodes, points, ways, relations = regional_network()
    segments, missing = road_segments(ways, points)
    graph = road_graph(segments, points)
    paths, features, corridor_rows = [], [], []
    membership = defaultdict(set)

    def feature(geometry, **properties):
        return {'type': 'Feature', 'geometry': mapping(geometry), 'properties': properties}

    for corridor in plan['corridors']:
        if len(corridor['nodes']) < 2 or any(node not in points for node in corridor['nodes']):
            raise ValueError(f'Anclas OSM ausentes o insuficientes para {corridor["id"]}.')
        terms = [word.casefold() for word in corridor['preferred']]
        excluded = [word.casefold() for word in corridor.get('exclude', [])]
        steps, visited = [], set()
        for a, b in zip(corridor['nodes'], corridor['nodes'][1:]):
            blocked = visited - {b} if corridor.get('simple') else ()
            if corridor.get('simple') and b in visited and b != corridor['nodes'][0]:
                raise ValueError(f'Ancla ya recorrida en {corridor["id"]}: {b}.')
            leg = route(graph, segments, a, b, terms, excluded, blocked)
            steps.extend(leg)
            visited.update(start for _, start, _ in leg)
        paths.append(steps)
        for key, _, _ in steps:
            membership[key].add(corridor['id'])
        way_order = list(dict.fromkeys(segments[k][0] for k, _, _ in steps))
        length = sum(meters(points[a], points[b]) for _, a, b in steps)
        if not length:
            raise ValueError(f'Corredor sin longitud: {corridor["id"]}.')
        preferred_length = sum(meters(points[a], points[b]) for k, a, b in steps
                               if any(term in segments[k][3].get('name', '').casefold() for term in terms))
        corridor_rows.append({'id': corridor['id'], 'anchors': corridor['nodes'], 'lengthKm': round(length / 1000, 3),
                              'preferredLengthPct': round(100 * preferred_length / length, 2),
                              'connectedAnchorPairs': len(corridor['nodes']) - 1,
                              'geometryCoveragePct': 100.0,
                              'osmWays': way_order, 'steps': steps,
                              'names': list(dict.fromkeys(segments[k][3].get('name') for k, _, _ in steps))})
        features.append(feature(LineString([points[steps[0][1]], *(points[b] for _, _, b in steps)]),
                                kind='corridor', id=corridor['id']))

    # Polygonize the undirected boundary; the travel directions remain on the routes.
    by_id = dict(zip((c['id'] for c in plan['corridors']), paths))
    main_boundary = [by_id[key] for key in plan['boundary']]
    circuit_ids = plan.get('boundaryCircuits', [])
    perimeter = main_boundary + [by_id[key] for key in circuit_ids]
    main_nodes = {node for path in main_boundary for _, a, b in path for node in (a, b)}
    for key in circuit_ids:
        steps = by_id[key]
        starts = {a for _, a, _ in steps}
        if steps[0][1] != steps[-1][2] or len(starts) != len(steps) or not starts & main_nodes:
            raise ValueError(f'El circuito {key} debe cerrar sin repeticiones y compartir un nodo OSM con el perímetro principal.')
    boundary_keys = {key for path in perimeter for key, _, _ in path}
    if plan.get('auditBoundary'):
        nodes_by_position = defaultdict(set)
        for path in perimeter:
            for _, a, b in path:
                nodes_by_position[points[a]].add(a)
                nodes_by_position[points[b]].add(b)
        if any(len(ids) > 1 for ids in nodes_by_position.values()):
            raise ValueError('El perímetro contiene nodos OSM distintos con coordenadas idénticas.')
    polygons = []
    perimeter_parts = []
    for label, group in [('main', main_boundary), *((key, [by_id[key]]) for key in circuit_ids)]:
        faces, cuts, dangles, invalid = interior_faces(group, points)
        if label != 'main' and (len(faces.geoms) != 1 or any(not geometry.is_empty for geometry in (cuts, dangles, invalid))):
            raise ValueError(f'El circuito {label} debe delimitar una sola cara sin colgantes ni cortes.')
        polygons.extend(faces.geoms)
        perimeter_parts.append((label, faces, cuts, dangles, invalid))
    # Distinct small loops also occur on dual carriageways at shared approaches.
    area = unary_union(polygons)
    if area.is_empty:
        raise ValueError('Los corredores no delimitan un interior cerrado.')
    mask = prep(area)
    for label, faces, *_ in perimeter_parts:
        face_properties = {'boundaryGroup': label} if plan.get('auditBoundary') else {}
        features.extend(feature(polygon, kind='interior-face', **face_properties) for polygon in faces.geoms)
    metrics, unknown, interior_unknown, incidence = Counter(), Counter(), Counter(), defaultdict(set)
    neighbors_by_node = defaultdict(set)
    graph_neighbors = defaultdict(set)
    inside_by_way, sector_counts = Counter(), Counter()
    locations, road_properties = {}, {}
    for key, (way, a, b, info) in segments.items():
        line = LineString([points[a], points[b]])
        if mask.contains(line) and not area.boundary.intersects(line):
            location = 'interior'
        elif mask.intersects(line) and line.intersection(area).length > 0:
            location = 'perimeter-or-crossing'
        else:
            location = 'outside'
        metrics[location] += 1
        locations[key] = location
        if location == 'interior':
            inside_by_way[way] += 1
            interior_unknown.update(k for k in ATTRIBUTES if not info.get(k))
        sector = None
        if location != 'outside' and plan.get('sectors'):
            middle = tuple((x + y) / 2 for x, y in zip(points[a], points[b]))
            sector = min(plan['sectors'], key=lambda s: meters(middle, points[s['seed']]))['id']
            sector_counts[sector] += 1
        if location != 'outside':
            graph_neighbors[a].add(b)
            graph_neighbors[b].add(a)
        incidence[a].add(way)
        incidence[b].add(way)
        neighbors_by_node[a].add(b)
        neighbors_by_node[b].add(a)
        unknown.update(k for k in ATTRIBUTES if not info.get(k))
        features.append(feature(line, kind='road-segment', id=key, osmWay=way, osmNodes=[a, b],
                                location=location, direction=direction(info), tags=info,
                                unknown=[k for k in ATTRIBUTES if not info.get(k)],
                                corridors=sorted(membership[key]), sector=sector))
        road_properties[key] = features[-1]['properties']

    junction_count = Counter()
    for node, linked in incidence.items():
        info = tags(nodes[node])
        signal = info.get('highway') == 'traffic_signals'
        crossing = info.get('highway') == 'crossing'
        intersection = len(neighbors_by_node[node]) >= 3
        # Way breaks alone do not establish a junction; use distinct neighbors.
        if signal or crossing or intersection:
            inside = mask.covers(Point(points[node]))
            for label, present in [('signals', signal), ('crossings', crossing), ('intersections', intersection)]:
                if present:
                    junction_count[label] += 1
                    if inside:
                        junction_count[label + 'InPerimeter'] += 1
            features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': points[node]},
                             'properties': {'kind': 'road-node', 'osmNode': node, 'osmWays': sorted(linked), 'tags': info,
                                            'intersection': intersection, 'insidePerimeter': inside}})
    restriction_rows = []
    for relation in relations:
        members = [dict(item.attrib) for item in relation.findall('member')]
        absent = [item for item in members if item['ref'] not in {'way': ways, 'node': nodes}.get(item['type'], {})]
        restriction_rows.append({'osmRelation': relation.attrib['id'], 'tags': tags(relation), 'members': members,
                                 'missingMembers': absent})
    for row, steps in zip(corridor_rows, paths):
        row['restrictionReview'] = restriction_candidates(steps, segments, restriction_rows)
    rings = []
    for way, (element, refs) in ways.items():
        if not refs or tags(element).get('junction') != 'roundabout':
            continue
        present = [points[node] for node in refs if node in points]
        geometry = LineString(present) if len(present) == len(refs) and len(refs) >= 2 else None
        rings.append({'osmWay': way, 'firstNode': refs[0], 'lastNode': refs[-1],
                      'closedAsSingleWay': refs[0] == refs[-1], 'missingNodes': len(refs) - len(present),
                      'partlyInPerimeter': geometry is not None and mask.intersects(geometry) and not mask.covers(geometry)})
    perimeter_metrics = []
    for label, faces, cuts, dangles, invalid in perimeter_parts:
        for kind, geometry in [('perimeter-cut', cuts), ('perimeter-dangle', dangles), ('invalid-ring', invalid)]:
            features.extend(feature(part, kind=kind) for part in geometry.geoms)
        perimeter_metrics.append({'id': label, 'faces': len(faces.geoms), 'cutEdges': len(cuts.geoms),
                                  'dangles': len(dangles.geoms), 'invalidRings': len(invalid.geoms)})
    report = {'schemaVersion': 1, 'plan': plan, 'snapshot': source,
              'snapshotSha256': sha256(SNAPSHOT.read_bytes()).hexdigest(),
              'corridors': corridor_rows, 'segments': dict(metrics), 'roadWays': len({v[0] for v in segments.values()}),
              'interiorWays': len(inside_by_way), 'missingGeometrySegments': missing,
              'sectors': plan.get('sectors', []), 'segmentsBySector': dict(sector_counts),
              'sharedCorridorSegments': sum(len(keys) > 1 for keys in membership.values()),
              'missingTagsBySegment': dict(unknown), 'missingTagsInterior': dict(interior_unknown),
              'mappedNodes': dict(junction_count),
              'interiorComponents': weak_components(graph_neighbors),
              'perimeter': {key: sum(part[key] for part in perimeter_metrics)
                            for key in ('faces', 'cutEdges', 'dangles', 'invalidRings')},
              'roundaboutWays': rings,
              'restrictions': restriction_rows}
    if plan.get('auditBoundary'):
        # Directed round trips can include connector segments outside the polygon.
        for key in boundary_keys:
            if locations[key] == 'outside':
                locations[key] = 'boundary-route'
        groups, expanded = roundabout_selection(ways, segments, points, locations)
        selected_neighbors = defaultdict(set)
        for key, properties in road_properties.items():
            if locations[key] == 'boundary-route':
                properties['preserveFor'] = 'boundary-route'
            elif key in expanded:
                properties['preserveFor'] = 'roundabout-expansion'
            if locations[key] != 'outside' or key in expanded:
                _, a, b, _ = segments[key]
                selected_neighbors[a].add(b)
                selected_neighbors[b].add(a)
        report.update(
            perimeterGroups=perimeter_metrics,
            junctions=audit_joins(plan.get('junctions', []), by_id, segments, restriction_rows),
            roundabouts=groups,
            selection={'geometryOrBoundarySegments': sum(value != 'outside' for value in locations.values()),
                       'boundaryOnlySegments': sum(value == 'boundary-route' for value in locations.values()),
                       'extraRoundaboutSegments': len(expanded),
                       'boundaryRouteSegments': len(boundary_keys),
                       'totalSegments': sum(value != 'outside' for value in locations.values()) + len(expanded),
                       'weakComponents': weak_components(selected_neighbors)},
        )
    output.mkdir()
    for name, data in [('inventory.json', report), ('inventory.geojson', {'type': 'FeatureCollection',
                            'source': source, 'features': features})]:
        (output / name).write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def restriction_candidates(steps, segments, restrictions):
    turns = {(segments[left[0]][0], left[2], segments[right[0]][0]) for left, right in zip(steps, steps[1:])}
    used = {segments[step[0]][0] for step in steps}
    found = []
    for row in restrictions:
        members = defaultdict(list)
        for member in row['members']:
            members[member['role']].append(member)
        origins = {m['ref'] for m in members['from']}
        destinations = {m['ref'] for m in members['to']}
        if not (origins & used):
            continue
        via_nodes = {m['ref'] for m in members['via'] if m['type'] == 'node'}
        via_ways = {m['ref'] for m in members['via'] if m['type'] == 'way'}
        matched = [(a, v, b) for a, v, b in turns if a in origins and v in via_nodes]
        rule = row['tags'].get('restriction', '')
        if any((b in destinations if rule.startswith('no_') else b not in destinations)
               for _, _, b in matched) or via_ways & used or (matched and not rule.startswith(('no_', 'only_'))):
            found.append(row['osmRelation'])
    return sorted(found)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(json.loads(args.plan.read_text(encoding='utf-8')), args.output)


if __name__ == '__main__':
    main()
