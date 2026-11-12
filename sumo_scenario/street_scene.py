"""Expose street geometry and mapped markings from the files of a saved SUMO run."""

from xml.etree import ElementTree as ET

from .signal_replay import signal_links
from .study import tags


def shape(element):
    return [tuple(map(float, point.split(',')[:2])) for point in element.get('shape', '').split()]


def street_scene(directory):
    network = ET.parse(directory / 'network.net.xml')
    osm = ET.parse(directory / 'recorte.osm.xml')
    roads = {way.get('id'): tags(way) for way in osm.iterfind('way')}
    nodes = {node.get('id'): node for node in osm.iterfind('node')}
    junctions = [polygon for junction in network.iterfind('junction')
                 if junction.get('type') != 'internal' and len(polygon := shape(junction)) >= 3]
    widths = {lane.get('id'): float(lane.get('width')) for edge in network.iterfind('edge')
              for lane in edge.iterfind('lane[@width]') if float(lane.get('width')) > 0}
    pedestrian_lanes = {
        lane.get('id'): edge.get('function', 'sidewalk') for edge in network.iterfind('edge')
        for lane in edge.iterfind('lane[@allow="pedestrian"]')
    }
    waiting = directory / 'waiting.add.xml'
    sidewalk_areas = [shape(poly) for poly in ET.parse(waiting).iterfind('poly[@type="sidewalk"]')] if waiting.is_file() else []

    markings = {}
    for edge in network.iterfind('edge[@from]'):
        edge_id = edge.get('id')
        reverse = edge_id.startswith('-')
        source = roads.get(edge_id.lstrip('-').split('#', 1)[0], {})
        turns = source.get('turn:lanes:backward' if reverse else 'turn:lanes:forward')
        if not turns and not reverse and source.get('oneway') == 'yes':
            turns = source.get('turn:lanes')
        if turns or source.get('lane_markings') or source.get('sidewalk'):
            markings[edge_id] = {
                'turns': turns.split('|')[::-1] if turns else [],  # SUMO indexes lanes from the right.
                'laneMarkings': source.get('lane_markings'),
                'sidewalk': source.get('sidewalk'),
            }

    crossings = []
    for way in osm.iterfind('way'):
        source = roads[way.get('id')]
        if source.get('footway') != 'crossing':
            continue
        points = [nodes[ref.get('ref')] for ref in way.iterfind('nd') if ref.get('ref') in nodes]
        if len(points) < 2:
            continue
        values = [source.get('crossing:markings'), *(tags(node).get('crossing:markings') for node in points)]
        crossings.append({
            'points': [(float(node.get('lon')), float(node.get('lat'))) for node in points],
            'zebra': any(value and value.startswith('zebra') for value in values),
        })
    return {'junctions': junctions, 'widths': widths, 'markings': markings, 'crossings': crossings,
            'pedestrianLanes': pedestrian_lanes, 'sidewalkAreas': sidewalk_areas,
            'signalLinks': signal_links(network)}
