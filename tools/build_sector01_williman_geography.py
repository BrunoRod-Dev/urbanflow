"""Build the Sector 01 Williman dressing layer from a live OSM map call.

The output is a static asset. It is not an input to netconvert and it does not
replace the certified road snapshot.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / 'urbanflow-web' / 'assets' / 'sector01-williman-geography.json'
SOURCE = ROOT / 'urbanflow-web' / 'assets' / 'sector01-williman-osm.xml'

# West, south, east, north. Covers the 241 m rambla, the beach to the west
# and the buildings beside the road. It is not the Sector 01 rectangle.
BOUNDS = (-54.94225, -34.95265, -54.93815, -34.94975)
ROAD_POINT = (-54.94002, -34.95110)
SEA_POINT = (-54.94205, -34.95110)
SAND_POINT = (-54.94105, -34.95110)
USER_AGENT = 'UrbanFlow-research/1.0 (Sector 01 Williman pilot)'


def fetch(url):
    request = Request(url, headers={'User-Agent': USER_AGENT})
    with urlopen(request, timeout=60) as response:
        return response.read()


def bounds_text(bounds):
    west, south, east, north = bounds
    return f'{west},{south},{east},{north}'


def tags_of(element):
    return {child.attrib['k']: child.attrib['v'] for child in element.findall('tag')}


def ring_of(way, nodes):
    points = [nodes[node.get('ref')] for node in way.findall('nd') if node.get('ref') in nodes]
    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]
    return points


def closed(points):
    return len(points) >= 4 and points[0] == points[-1]


def shoelace(points):
    area = 0
    for start, end in zip(points, points[1:] + points[:1]):
        area += start[0] * end[1] - end[0] * start[1]
    return area / 2


def area_m2(points):
    ring = points[:-1] if closed(points) else points
    if len(ring) < 3:
        return 0
    return abs(shoelace(ring)) * (111_320 * 0.8192) * 110_574


def inside(point, ring):
    x, y = point
    contained = False
    previous = ring[-1]
    for current in ring:
        if (current[1] > y) != (previous[1] > y):
            cross = (previous[0] - current[0]) * (y - current[1]) / (previous[1] - current[1]) + current[0]
            if x < cross:
                contained = not contained
        previous = current
    return contained


def clip_ring(points, bounds):
    west, south, east, north = bounds

    def cut(source, contains, border):
        if not source:
            return []
        output = []
        previous = source[-1]
        previous_inside = contains(previous)
        for current in source:
            current_inside = contains(current)
            if current_inside:
                if not previous_inside:
                    output.append(border(previous, current))
                output.append(current)
            elif previous_inside:
                output.append(border(previous, current))
            previous = current
            previous_inside = current_inside
        return output

    def at_x(value):
        def border(start, end):
            delta = end[0] - start[0]
            ratio = 0 if abs(delta) < 1e-15 else (value - start[0]) / delta
            return (value, start[1] + ratio * (end[1] - start[1]))
        return border

    def at_y(value):
        def border(start, end):
            delta = end[1] - start[1]
            ratio = 0 if abs(delta) < 1e-15 else (value - start[1]) / delta
            return (start[0] + ratio * (end[0] - start[0]), value)
        return border

    ring = points[:-1] if closed(points) else list(points)
    ring = cut(ring, lambda point: point[0] >= west, at_x(west))
    ring = cut(ring, lambda point: point[0] <= east, at_x(east))
    ring = cut(ring, lambda point: point[1] >= south, at_y(south))
    ring = cut(ring, lambda point: point[1] <= north, at_y(north))
    return ring


def clip_line(points, bounds):
    west, south, east, north = bounds

    def clip_segment(start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        p = (-dx, dx, -dy, dy)
        q = (start[0] - west, east - start[0], start[1] - south, north - start[1])
        u0, u1 = 0, 1
        for velocity, distance in zip(p, q):
            if abs(velocity) < 1e-15:
                if distance < 0:
                    return None
                continue
            ratio = distance / velocity
            if velocity < 0:
                if ratio > u1:
                    return None
                u0 = max(u0, ratio)
            else:
                if ratio < u0:
                    return None
                u1 = min(u1, ratio)
        return (start[0] + u0 * dx, start[1] + u0 * dy), (start[0] + u1 * dx, start[1] + u1 * dy)

    pieces = []
    current = []
    for start, end in zip(points, points[1:]):
        clipped = clip_segment(start, end)
        if clipped is None:
            if len(current) >= 2:
                pieces.append(current)
            current = []
            continue
        if not current:
            current = [clipped[0], clipped[1]]
        elif abs(current[-1][0] - clipped[0][0]) < 1e-9 and abs(current[-1][1] - clipped[0][1]) < 1e-9:
            current.append(clipped[1])
        else:
            if len(current) >= 2:
                pieces.append(current)
            current = [clipped[0], clipped[1]]
    if len(current) >= 2:
        pieces.append(current)
    return pieces


def perimeter(point, bounds):
    west, south, east, north = bounds
    width, height = east - west, north - south
    on_south = abs(point[1] - south) <= 1e-7
    on_north = abs(point[1] - north) <= 1e-7
    on_east = abs(point[0] - east) <= 1e-7
    on_west = abs(point[0] - west) <= 1e-7
    if on_south and on_west:
        return 0
    if on_south and on_east:
        return 1
    if on_north and on_east:
        return 2
    if on_north and on_west:
        return 3
    if on_south:
        return (point[0] - west) / width
    if on_east:
        return 1 + (point[1] - south) / height
    if on_north:
        return 2 + (east - point[0]) / width
    if on_west:
        return 3 + (north - point[1]) / height
    raise ValueError(f'El extremo {point} no toca el borde de la ventana.')


def boundary_arc(start, end, bounds, clockwise):
    west, south, east, north = bounds
    corners = [(west, south), (east, south), (east, north), (west, north)]
    begin, finish = perimeter(start, bounds), perimeter(end, bounds)
    points = []
    cursor = begin
    remaining = (finish - begin) % 4 if clockwise else (begin - finish) % 4
    while remaining > 1e-7:
        if clockwise:
            nxt = (int(cursor) + 1) % 4
            step = (nxt - cursor) % 4
        else:
            nxt = int(cursor) % 4
            if abs(cursor - nxt) <= 1e-9:
                nxt = (nxt - 1) % 4
            step = (cursor - nxt) % 4
        if step <= 1e-9:
            step = 4
        if step >= remaining - 1e-8:
            break
        points.append(corners[nxt])
        cursor = nxt
        remaining = (finish - cursor) % 4 if clockwise else (cursor - finish) % 4
    points.append(end)
    return points


def close_with_boundary(line, bounds, contains):
    for clockwise in (False, True):
        arc = boundary_arc(line[-1], line[0], bounds, clockwise)
        polygon = line + arc[:-1]
        if contains(SEA_POINT, polygon) and not contains(ROAD_POINT, polygon) and area_m2(polygon) < 80_000:
            return polygon
    raise RuntimeError('La costa recortada no separa el mar de la rambla.')


def same_border(point, other, bounds):
    west, south, east, north = bounds
    borders = (
        abs(point[1] - south) <= 1e-7 and abs(other[1] - south) <= 1e-7,
        abs(point[1] - north) <= 1e-7 and abs(other[1] - north) <= 1e-7,
        abs(point[0] - west) <= 1e-7 and abs(other[0] - west) <= 1e-7,
        abs(point[0] - east) <= 1e-7 and abs(other[0] - east) <= 1e-7,
    )
    return any(borders)


def sand_strip(coast, land, bounds):
    pairings = (
        (coast, land),
        (coast, list(reversed(land))),
    )
    for left, right in pairings:
        if not (same_border(left[0], right[0], bounds) and same_border(left[-1], right[-1], bounds)):
            continue
        polygon = left + list(reversed(right))
        if inside(SAND_POINT, polygon) and not inside(SEA_POINT, polygon) and not inside(ROAD_POINT, polygon):
            return polygon
    raise RuntimeError('El borde de Playa Mansa no cierra una franja de arena dentro de la ventana.')


def feature(kind, osm_id, geometry, properties):
    return {
        'type': 'Feature',
        'id': f'{kind}/{osm_id}',
        'properties': {'class': kind, 'osmId': osm_id, **properties},
        'geometry': geometry,
    }


def polygon_geometry(points):
    ring = [[round(lon, 7), round(lat, 7)] for lon, lat in points]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {'type': 'Polygon', 'coordinates': [ring]}


def line_geometry(points):
    return {'type': 'LineString', 'coordinates': [[round(lon, 7), round(lat, 7)] for lon, lat in points]}


def write_source(path, nodes, ways, relation):
    root = ET.Element('osm', version='0.6', generator='UrbanFlow sector01 Williman geography')
    for identifier in sorted(nodes, key=int):
        lon, lat = nodes[identifier]
        ET.SubElement(root, 'node', id=identifier, lat=f'{lat:.7f}', lon=f'{lon:.7f}')
    for way in ways:
        element = ET.SubElement(root, 'way', id=way.get('id'))
        for node in way.findall('nd'):
            ET.SubElement(element, 'nd', ref=node.get('ref'))
        for tag in way.findall('tag'):
            ET.SubElement(element, 'tag', k=tag.get('k'), v=tag.get('v'))
    if relation is not None:
        element = ET.SubElement(root, 'relation', id=relation.get('id'))
        for member in relation.findall('member'):
            ET.SubElement(element, 'member', **member.attrib)
        for tag in relation.findall('tag'):
            ET.SubElement(element, 'tag', k=tag.get('k'), v=tag.get('v'))
    path.write_bytes(ET.tostring(root, encoding='utf-8', xml_declaration=True))


def main():
    url = 'https://api.openstreetmap.org/api/0.6/map?bbox=' + bounds_text(BOUNDS)
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    root = ET.fromstring(fetch(url))
    nodes = {node.get('id'): (float(node.get('lon')), float(node.get('lat'))) for node in root.findall('node')}
    ways = {way.get('id'): way for way in root.findall('way')}
    beach = next(
        (relation for relation in root.findall('relation')
         if tags_of(relation).get('name') == 'Playa Mansa' and tags_of(relation).get('natural') == 'beach'),
        None,
    )
    if beach is None:
        raise RuntimeError('La relación Playa Mansa no está en la ventana.')

    coast_ids = [
        member.get('ref') for member in beach.findall('member')
        if member.get('type') == 'way' and tags_of(ways.get(member.get('ref'), ET.Element('way'))).get('natural') == 'coastline'
    ]
    land_ids = [
        member.get('ref') for member in beach.findall('member')
        if member.get('type') == 'way' and member.get('role') == 'outer' and member.get('ref') not in coast_ids
        and member.get('ref') in ways and len(ring_of(ways[member.get('ref')], nodes)) > 8
    ]
    if len(coast_ids) != 1 or len(land_ids) != 1:
        raise RuntimeError(f'Bordes de playa inesperados: costa {coast_ids}, tierra {land_ids}.')
    coast_line = clip_line(ring_of(ways[coast_ids[0]], nodes), BOUNDS)
    land_line = clip_line(ring_of(ways[land_ids[0]], nodes), BOUNDS)
    coast_line.sort(key=len, reverse=True)
    land_line.sort(key=len, reverse=True)
    water = close_with_boundary(coast_line[0], BOUNDS, inside)
    sand = sand_strip(coast_line[0], land_line[0], BOUNDS)

    kept = []
    incomplete = []
    features = [
        feature('water', coast_ids[0], polygon_geometry(water), {
            'name': 'Lado del mar de la línea de costa',
            'derived': True,
            'source': 'natural=coastline',
        }),
        feature('sand', beach.get('id'), polygon_geometry(sand), {
            'name': 'Playa Mansa',
            'natural': 'beach',
            'surface': 'sand',
            'derived': True,
            'sourceWays': [coast_ids[0], land_ids[0]],
        }),
        feature('coastline', coast_ids[0], line_geometry(coast_line[0]), {'natural': 'coastline'}),
    ]
    kept.extend([ways[coast_ids[0]], ways[land_ids[0]]])

    for way in ways.values():
        attributes = tags_of(way)
        points = ring_of(way, nodes)
        if points[:1] != points[-1:] and way.find('nd') is not None and way.findall('nd')[0].get('ref') == way.findall('nd')[-1].get('ref'):
            pass
        raw = [nodes[node.get('ref')] for node in way.findall('nd') if node.get('ref') in nodes]
        is_closed = len(raw) >= 4 and raw[0] == raw[-1]
        if not is_closed:
            continue
        kind = None
        properties = {}
        if 'building' in attributes:
            kind = 'building'
            levels = attributes.get('building:levels')
            height = attributes.get('height')
            properties = {
                'name': attributes.get('name'),
                'building': attributes['building'],
                'levels': int(levels) if levels and levels.isdigit() else None,
                'height': float(height) if height and height.replace('.', '', 1).isdigit() else None,
            }
        elif attributes.get('landuse') == 'grass':
            kind = 'grass'
            properties = {'landuse': 'grass'}
        elif attributes.get('natural') == 'scrub':
            kind = 'scrub'
            properties = {'natural': 'scrub'}
        if kind is None:
            continue
        if kind == 'building':
            refs = [node.get('ref') for node in way.findall('nd')]
            missing = [ref for ref in refs if ref not in nodes]
            closed_way = len(refs) >= 4 and refs[0] == refs[-1]
            if missing or not closed_way:
                incomplete.append({
                    'osmId': way.get('id'),
                    'missingNodes': missing,
                    'closed': closed_way,
                    'note': 'No se reconstruyó la huella: faltan nodos en el extracto o la vía no cierra.',
                })
                continue
            ring = [nodes[ref] for ref in refs[:-1]]
            known_inside = clip_ring(ring, BOUNDS)
            if len(known_inside) < 3 or area_m2(known_inside) < 12:
                continue
            properties['footprint'] = 'complete'
            features.append(feature(kind, way.get('id'), polygon_geometry(ring), properties))
            kept.append(way)
            continue
        clipped = clip_ring(raw[:-1], BOUNDS)
        if len(clipped) < 3 or area_m2(clipped) < 12:
            continue
        features.append(feature(kind, way.get('id'), polygon_geometry(clipped), properties))
        kept.append(way)

    used_nodes = {}
    for way in kept:
        for node in way.findall('nd'):
            identifier = node.get('ref')
            if identifier in nodes:
                used_nodes[identifier] = nodes[identifier]
    for relation_member in beach.findall('member'):
        pass
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    write_source(SOURCE, used_nodes, kept, beach)
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    counts = {}
    for item in features:
        counts[item['properties']['class']] = counts.get(item['properties']['class'], 0) + 1
    collection = {
        'type': 'FeatureCollection',
        'meta': {
            'name': 'Piloto Rambla Williman, Sector 01',
            'retrievedAt': retrieved,
            'source': url,
            'license': 'https://www.openstreetmap.org/copyright',
            'licenseName': 'Open Database License (ODbL)',
            'attribution': '© colaboradores de OpenStreetMap',
            'roadSnapshot': 'No reemplaza sumo_scenario/regional/maldonado.osm.gz ni el recorte vial certificado.',
            'segment': {
                'name': 'Rambla Doctor Claudio Williman',
                'way': '482520536',
                'fromNode': '840834845',
                'toNode': '2480679874',
                'lengthMeters': 241.2,
            },
            'bounds': list(BOUNDS),
            'heightRule': {
                'metersPerLevel': 3.1,
                'provisionalMeters': None,
                'measured': 'Solo una etiqueta height numérica. Este recorte no trae ninguna.',
                'estimated': 'building:levels por metersPerLevel. Es una altura visual, no una medición.',
                'provisional': 'Sin height ni plantas: huella y contorno, sin altura inventada.',
            },
            'buildings': {
                'identity': 'properties.osmId. La misma vía no se dibuja dos veces.',
                'footprint': 'Anillo completo de la vía cerrada cuando todos sus nodos están en el extracto. No se recorta contra la ventana.',
                'incomplete': incomplete,
            },
            'vegetationRule': {
                'appliesTo': 'scrub',
                'spacingMeters': 7,
                'seed': 41,
                'minHeightMeters': 0.7,
                'maxHeightMeters': 1.4,
                'jitter': 0.35,
                'declared': 'Arbustos de una grilla sembrada dentro de natural=scrub. No son posiciones de árboles relevados.',
                'drawing': 'Dos conos superpuestos. El radio sale de la altura ya sorteada con la semilla y de la posición, sin mover el punto.',
            },
            'classes': {
                'earth': 'Rectángulo de la ventana, generado al dibujar. No es césped.',
                'water': 'Lado del mar de la costa, recortado a la ventana. Superficie derivada.',
                'sand': 'Franja entre la costa y el borde terrestre de la relación Playa Mansa.',
                'grass': 'Polígonos landuse=grass recortados a la ventana.',
                'scrub': 'Polígonos natural=scrub recortados a la ventana.',
            },
            'osmExtract': SOURCE.name,
            'osmExtractSha256': source_hash,
        },
        'demo': {
            'ways': ['482520536', '164559876'],
            'west': -54.94055,
            'south': -34.952177,
            'east': -54.93970,
            'north': -34.950015,
            'minSpeed': 6,
        },
        'features': features,
    }
    text = json.dumps(collection, ensure_ascii=False, indent=2)
    ASSET.write_text(text + '\n', encoding='utf-8')
    asset_hash = hashlib.sha256(ASSET.read_bytes()).hexdigest()
    print('retrieved', retrieved)
    print('counts', counts)
    print('source', source_hash)
    print('asset', asset_hash)
    print('features', len(features))
    for item in features:
        if item['properties']['class'] != 'building':
            continue
        props = item['properties']
        print(props['osmId'], props.get('name'), props['building'], 'levels', props['levels'], 'height', props['height'])


if __name__ == '__main__':
    main()
