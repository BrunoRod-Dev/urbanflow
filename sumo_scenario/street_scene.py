"""Expose street geometry and mapped markings from the files of a saved SUMO run."""

from xml.etree import ElementTree as ET

from .compound_crossings import CROSSINGS, joined_id
from .road_surfaces import junction_groups, physical_surfaces, roundabout_rings, surface_kind
from .signal_replay import signal_links
from .study import tags


def shape(element):
    return [tuple(map(float, point.split(',')[:2])) for point in element.get('shape', '').split()]


def street_scene(directory, network=None, osm=None):
    if network is None:
        network = ET.parse(directory / 'network.net.xml')
    if osm is None:
        osm = ET.parse(directory / 'recorte.osm.xml')
    roads = {way.get('id'): tags(way) for way in osm.iterfind('way')}
    way_nodes = {way.get('id'): {ref.get('ref') for ref in way.iterfind('nd')} for way in osm.iterfind('way')}
    nodes = {node.get('id'): node for node in osm.iterfind('node')}
    junctions = {junction.get('id'): junction for junction in network.iterfind('junction')
                 if junction.get('type') not in {'internal', 'dead_end'} and junction.get('x') and junction.get('y')}
    junction_shapes = {key: shape(junction) for key, junction in junctions.items()}
    links = signal_links(network)
    groups = list(junction_groups(network, links))
    joined_junctions = [[point for key in group for point in junction_shapes.get(key, [])]
                        for group in groups]
    component = {key: index for index, group in enumerate(groups) for key in group}
    merged_nodes = {joined_id(group): set(group) for group in CROSSINGS}
    approaches = {lane.get('id'): edge for edge in network.iterfind('edge[@from]') for lane in edge.iterfind('lane')}
    for link in links:
        edge = approaches.get(link['fromLane'])
        if edge is None:
            link['insideJunction'] = True
            continue
        origin, destination = edge.get('from'), edge.get('to')
        link['insideJunction'] = origin in component and component[origin] == component.get(destination)
        node = nodes.get(destination)
        if node is not None and tags(node).get('highway') == 'traffic_signals':
            link['osmSignalNode'] = destination
        elif destination in merged_nodes:
            osm_way = edge.get('id').lstrip('-').split('#', 1)[0]
            references = merged_nodes[destination] & way_nodes.get(osm_way, set())
            if len(references) == 1:
                link['osmSignalNode'] = next(iter(references))
    widths = {lane.get('id'): float(lane.get('width')) for edge in network.iterfind('edge')
              for lane in edge.iterfind('lane[@width]') if float(lane.get('width')) > 0}
    pedestrian_lanes = {
        lane.get('id'): edge.get('function', 'sidewalk') for edge in network.iterfind('edge')
        for lane in edge.iterfind('lane[@allow="pedestrian"]')
    }
    waiting = directory / 'waiting.add.xml'
    sidewalk_areas = [shape(poly) for poly in ET.parse(waiting).iterfind('poly[@type="sidewalk"]')] if waiting.is_file() else []

    markings = {}
    grades = {}
    for edge in network.iterfind('edge[@from]'):
        edge_id = edge.get('id')
        reverse = edge_id.startswith('-')
        source = roads.get(edge_id.lstrip('-').split('#', 1)[0], {})
        layer = source.get('layer', '1' if source.get('bridge', 'no') != 'no' else
                           '-1' if source.get('tunnel', 'no') != 'no' else '0')
        if layer != '0':
            grades[edge_id] = layer
        turns = source.get('turn:lanes:backward' if reverse else 'turn:lanes:forward')
        if not turns and not reverse and source.get('oneway') == 'yes':
            turns = source.get('turn:lanes')
        sidewalk = source.get('sidewalk')
        sides = {side for side in ('left', 'right') if source.get(f'sidewalk:{side}',
                 'yes' if sidewalk in ('yes', 'both', side) else 'no') == 'yes'}
        if reverse:
            sides = {'left' if side == 'right' else 'right' for side in sides}
        if turns or source.get('lane_markings') or sidewalk or sides:
            markings[edge_id] = {
                'turns': turns.split('|')[::-1] if turns else [],  # SUMO indexes lanes from the right.
                'laneMarkings': source.get('lane_markings'),
                'sidewalk': sidewalk, 'sidewalkSides': sorted(sides),
            }

    crossings = []
    sidewalks = []
    mapped_crossing_nodes = {edge.get('id').split('_c', 1)[0].lstrip(':')
                             for edge in network.iterfind('edge[@function="crossing"]')}
    zebra_nodes = {key for key, node in nodes.items() if tags(node).get('crossing:markings', '').startswith('zebra')}
    for way in osm.iterfind('way'):
        identifier = way.get('id')
        source = roads[identifier]
        if source.get('footway') == 'sidewalk' and surface_kind(source) is None:
            points = [nodes[ref.get('ref')] for ref in way.iterfind('nd') if ref.get('ref') in nodes]
            if len(points) >= 2:
                sidewalks.append({'id': identifier, 'source': 'OpenStreetMap', 'estimated': True,
                                  'points': [[float(node.get(axis)) for axis in ('lon', 'lat')] for node in points]})
        if source.get('footway') != 'crossing':
            continue
        points = [nodes[ref.get('ref')] for ref in way.iterfind('nd') if ref.get('ref') in nodes]
        if len(points) < 2:
            continue
        values = [source.get('crossing:markings'), *(tags(node).get('crossing:markings') for node in points)]
        mapped_crossing_nodes.update(node.get('id') for node in points)
        crossings.append({
            'id': identifier, 'source': 'OpenStreetMap',
            'points': [(float(node.get('lon')), float(node.get('lat'))) for node in points],
            'zebra': any(value and value.startswith('zebra') for value in values),
        })
    node_crossings = [{'id': key, 'point': [float(nodes[key].get(axis)) for axis in ('lon', 'lat')],
                       'source': 'OpenStreetMap', 'estimated': True}
                      for key in sorted(zebra_nodes - mapped_crossing_nodes)]
    return {'junctions': [polygon for polygon in junction_shapes.values() if len(polygon) >= 3],
            'junctionGroups': [group for group in joined_junctions if len(group) >= 3],
            'widths': widths, 'markings': markings, 'crossings': crossings, 'nodeCrossings': node_crossings,
            'sidewalkLines': sidewalks,
            'physicalSurfaces': list(physical_surfaces(osm, roads, nodes)),
            'roundabouts': list(roundabout_rings(network, junctions)),
            'edgeGrades': grades,
            'pedestrianLanes': pedestrian_lanes, 'sidewalkAreas': sidewalk_areas,
            'signalLinks': links}
