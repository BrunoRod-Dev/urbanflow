"""SUMO lane geometry for import diagnostics and geographic replay."""

from collections import defaultdict
from math import cos, dist, radians
from xml.etree import ElementTree as ET


def lane_shapes(network):
    return {lane.get('id'): {
        'edge': edge.get('id'), 'length': float(lane.get('length')),
        'points': [tuple(map(float, point.split(',')[:2])) for point in lane.get('shape', '').split()],
    } for edge in network.findall('edge') for lane in edge.findall('lane') if lane.get('shape')}


def lane_links(network):
    links = defaultdict(set)
    for link in network.findall('connection'):
        origin = f"{link.get('from')}_{link.get('fromLane')}"
        destination = link.get('via') or f"{link.get('to')}_{link.get('toLane')}"
        links[origin].add(destination)
    return {origin: sorted(destinations) for origin, destinations in links.items()}


def vector(first, last):
    return last[0] - first[0], last[1] - first[1]


def dot(first, second):
    return first[0] * second[0] + first[1] * second[1]


def cross(first, second):
    return first[0] * second[1] - first[1] * second[0]


def unit(direction):
    length = dist((0, 0), direction)
    return (direction[0] / length, direction[1] / length) if length else (0, 0)


def reversed_straights(network):
    lanes = lane_shapes(network)
    edge_nodes = {edge.get('id'): edge.get('to') for edge in network.findall('edge[@to]')}
    warnings = []
    for connection in network.findall('connection[@dir="s"][@via]'):
        start, end = (f"{connection.get(side)}_{connection.get(side + 'Lane')}" for side in ('from', 'to'))
        internal = connection.get('via')
        if any(len(lanes.get(key, {}).get('points', ())) < 2 for key in (start, end, internal)):
            continue
        incoming, outgoing, shape = (lanes[key]['points'] for key in (start, end, internal))
        first = unit(vector(*incoming[-2:]))
        last = unit(vector(*outgoing[:2]))
        if dot(first, last) < .5:
            continue
        heading = unit((first[0] + last[0], first[1] + last[1]))
        backwards = sum(max(0, -dot(vector(left, right), heading)) for left, right in zip(shape, shape[1:]))
        if backwards >= 1:
            warnings.append({'junction': edge_nodes.get(connection.get('from')), 'fromLane': start,
                             'toLane': end, 'via': internal, 'backwardsMeters': round(backwards, 2)})
    return warnings


def geographic_transform(network, node_file):
    """Fit a local projection from SUMO's own Cartesian and geographic node outputs."""
    if not node_file.is_file():
        return None
    geo = {node.get('id'): (float(node.get('x')), float(node.get('y')))
           for node in ET.parse(node_file).findall('node')}
    pairs = [((float(node.get('x')), float(node.get('y'))), geo[node.get('id')])
             for node in network.findall('junction') if node.get('id') in geo]
    if len(pairs) < 3:
        return None
    origin, location = pairs[0]
    far, far_geo = max(pairs, key=lambda pair: dist(origin, pair[0]))
    basis = vector(origin, far)
    side, side_geo = max(pairs, key=lambda pair: abs(cross(basis, vector(origin, pair[0]))))
    other = vector(origin, side)
    determinant = cross(basis, other)
    if abs(determinant) < 1:
        return None
    first, second = vector(location, far_geo), vector(location, side_geo)
    east = [(first[i] * other[1] - second[i] * basis[1]) / determinant for i in range(2)]
    north = [(second[i] * basis[0] - first[i] * other[0]) / determinant for i in range(2)]
    for point, actual in pairs:
        x, y = vector(origin, point)
        lng, lat = (location[i] + x * east[i] + y * north[i] for i in range(2))
        error = dist((0, 0), ((lng - actual[0]) * cos(radians(lat)), lat - actual[1])) * 111_320
        if error > .15:
            return None
    return {'origin': origin, 'location': location, 'east': east, 'north': north}


def replay_geometry(network, node_file):
    projection = geographic_transform(network, node_file)
    if projection is None:
        return None
    return {'projection': projection, 'lanes': lane_shapes(network), 'links': lane_links(network)}
