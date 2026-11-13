"""Use the same OpenStreetMap snapshot for studies across the coastal region."""

from functools import lru_cache
import gzip
import json
from pathlib import Path
from xml.etree import ElementTree as ET


DATA = Path(__file__).resolve().parent / 'regional'
SNAPSHOT = DATA / 'maldonado.osm.gz'


def coverage():
    return {**json.loads((DATA / 'coverage.json').read_text(encoding='utf-8')), 'available': SNAPSHOT.is_file()}


def intersects(points, bounds):
    if not points:
        return False
    west, south, east, north = bounds
    return any(max(a[0], b[0]) >= west and min(a[0], b[0]) <= east
               and max(a[1], b[1]) >= south and min(a[1], b[1]) <= north
               for a, b in zip(points, points[1:]))


@lru_cache(maxsize=1)
def regional_network():
    with gzip.open(SNAPSHOT, 'rb') as stream:
        root = ET.parse(stream).getroot()
    nodes = {node.get('id'): node for node in root.findall('node')}
    points = {key: (float(node.get('lon')), float(node.get('lat'))) for key, node in nodes.items()}
    ways = {way.get('id'): (way, [ref.get('ref') for ref in way.findall('nd')]) for way in root.findall('way')}
    return root.attrib, nodes, points, ways, root.findall('relation')


def write_local_extract(bounds, destination):
    region = coverage()
    west, south, east, north = region['sourceBounds']
    if not region['available'] or not (west <= bounds[0] < bounds[2] <= east and south <= bounds[1] < bounds[3] <= north):
        return None
    attributes, nodes, points, ways, relations = regional_network()
    selected = {key for key, (_, refs) in ways.items() if intersects([points[ref] for ref in refs], bounds)}
    if not selected:
        return None
    relations_to_keep = []
    relation_nodes = set()
    for relation in relations:
        members = relation.findall('member')
        way_members = {member.get('ref') for member in members if member.get('type') == 'way'}
        if way_members & selected:
            relations_to_keep.append(relation)
            selected.update(way_members)
            relation_nodes.update(member.get('ref') for member in members if member.get('type') == 'node')
    used_nodes = relation_nodes | {ref for key in selected for ref in ways[key][1]}
    root = ET.Element('osm', attributes)
    ET.SubElement(root, 'bounds', minlon=str(bounds[0]), minlat=str(bounds[1]), maxlon=str(bounds[2]), maxlat=str(bounds[3]))
    root.extend(nodes[key] for key in sorted(used_nodes, key=int))
    root.extend(ways[key][0] for key in sorted(selected, key=int))
    root.extend(relations_to_keep)
    ET.ElementTree(root).write(destination, encoding='utf-8', xml_declaration=True)
    return {'name': region['name'], 'snapshot': attributes.get('snapshot'), 'source': region['source']}
