"""Rebuild the bundled coastal road snapshot from a Geofabrik Uruguay .osm.pbf."""

import argparse
import gzip
from pathlib import Path
from xml.etree import ElementTree as ET

from .regional_map import SNAPSHOT, coverage, intersects
from .road_surfaces import surface_kind


def add_tags(element, tags):
    for tag in tags:
        ET.SubElement(element, 'tag', k=tag.k, v=tag.v)


def build(source):
    import osmium

    bounds = coverage()['sourceBounds']
    reader = osmium.io.Reader(str(source))
    timestamp = reader.header().get('osmosis_replication_timestamp')
    reader.close()
    ways = {}
    relations = []
    used_nodes = set()
    for obj in osmium.FileProcessor(source).with_locations():
        if obj.is_way() and (obj.tags.get('highway') or surface_kind(obj.tags)):
            if not all(node.location.valid() for node in obj.nodes):
                continue
            if not intersects([(node.lon, node.lat) for node in obj.nodes], bounds):
                continue
            way = ET.Element('way', id=str(obj.id))
            for node in obj.nodes:
                used_nodes.add(node.ref)
                ET.SubElement(way, 'nd', ref=str(node.ref))
            add_tags(way, obj.tags)
            ways[obj.id] = way
        elif obj.is_relation() and obj.tags.get('type', '').startswith('restriction'):
            members = list(obj.members)
            if not all(member.type == 'n' or member.type == 'w' and member.ref in ways for member in members):
                continue
            if not any(member.type == 'w' for member in members):
                continue
            relation = ET.Element('relation', id=str(obj.id))
            for member in members:
                if member.type == 'n':
                    used_nodes.add(member.ref)
                ET.SubElement(relation, 'member', type={'n': 'node', 'w': 'way'}[member.type],
                              ref=str(member.ref), role=member.role)
            add_tags(relation, obj.tags)
            relations.append(relation)

    root = ET.Element('osm', version='0.6', generator='UrbanFlow', snapshot=timestamp,
                      copyright='OpenStreetMap contributors', attribution='https://www.openstreetmap.org/copyright',
                      license='https://opendatacommons.org/licenses/odbl/1-0/')
    for node in osmium.FileProcessor(source, osmium.osm.NODE):
        if node.id in used_nodes:
            element = ET.SubElement(root, 'node', id=str(node.id), lon=str(node.location.lon), lat=str(node.location.lat))
            add_tags(element, node.tags)
    if len(root) != len(used_nodes) or not ways:
        raise ValueError('El PBF no contiene una red completa para la región.')
    root.extend(ways.values())
    root.extend(relations)
    with gzip.open(SNAPSHOT, 'wb', compresslevel=6) as stream:
        ET.ElementTree(root).write(stream, encoding='utf-8', xml_declaration=True)
    print(f'{timestamp}: {len(used_nodes)} nodos, {len(ways)} vías, {len(relations)} restricciones. {SNAPSHOT}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pbf', type=Path)
    build(parser.parse_args().pbf)
