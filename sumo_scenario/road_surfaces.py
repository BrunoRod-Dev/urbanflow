"""Physical features shared by the street renderer and the network audit."""

from collections import defaultdict


def surface_kind(tags):
    if tags.get('area') == 'no':
        return None
    if tags.get('area:highway') == 'traffic_island' or (
        tags.get('barrier') == 'kerb' and tags.get('kerb') == 'raised' and tags.get('area') == 'yes'
    ):
        return 'island'
    if tags.get('area:highway') in {'footway', 'pedestrian'} or (
        tags.get('highway') == 'footway' and tags.get('area') == 'yes' and tags.get('footway') == 'sidewalk'
    ):
        return 'sidewalk'
    return None


def physical_surfaces(osm, way_tags, nodes):
    for way in osm.iterfind('way'):
        identifier = way.get('id')
        attributes = way_tags[identifier]
        kind = surface_kind(attributes)
        if kind is None:
            continue
        refs = [node.get('ref') for node in way.iterfind('nd')]
        if len(set(refs)) < 3 or refs[0] != refs[-1] or not all(ref in nodes for ref in refs):
            continue
        yield {'kind': kind, 'id': identifier, 'source': 'OpenStreetMap', 'estimated': False,
               'layer': attributes.get('layer', '0'),
               'points': [[float(nodes[ref].get('lon')), float(nodes[ref].get('lat'))] for ref in refs[:-1]]}


def junction_groups(network, signal_links):
    """Group nearby components connected under the same signal controller."""
    edges = {edge.get('id'): edge for edge in network.iterfind('edge[@from]')}
    nodes_by_signal = defaultdict(set)
    lane_edges = {lane.get('id'): edge for edge in edges.values() for lane in edge.iterfind('lane')}
    for link in signal_links:
        edge = lane_edges.get(link['fromLane'])
        if edge is not None:
            nodes_by_signal[link['controller']].add(edge.get('to'))
    for nodes in nodes_by_signal.values():
        adjacent = defaultdict(set)
        for edge in edges.values():
            origin, destination = edge.get('from'), edge.get('to')
            if origin in nodes and destination in nodes and any(
                float(lane.get('length', 'inf')) <= 30 for lane in edge.iterfind('lane')
            ):
                adjacent[origin].add(destination)
                adjacent[destination].add(origin)
        visited = set()
        for origin in sorted(adjacent):
            if origin in visited:
                continue
            component = {origin}
            pending = [origin]
            while pending:
                for node in adjacent[pending.pop()] - component:
                    component.add(node)
                    pending.append(node)
            visited.update(component)
            yield sorted(component)


def roundabout_rings(network, junctions):
    edges = {edge.get('id'): edge for edge in network.iterfind('edge[@from]')}
    for roundabout in network.iterfind('roundabout'):
        edge_ids = roundabout.get('edges', '').split()
        if len(edge_ids) < 3 or not all(identifier in edges for identifier in edge_ids):
            continue
        following = {edges[key].get('from'): edges[key].get('to') for key in edge_ids}
        start = edges[edge_ids[0]].get('from')
        ring = [start]
        while (node := following.get(ring[-1])) in junctions and node not in ring:
            ring.append(node)
        if node == start and len(ring) == len(edge_ids):
            yield {'kind': 'island', 'id': ','.join(edge_ids), 'source': 'SUMO roundabout', 'estimated': True,
                   'points': [[float(junctions[key].get(axis)) for axis in ('x', 'y')] for key in ring]}
