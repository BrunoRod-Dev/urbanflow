"""Rebuild verified single intersections that OSM represents with several nodes."""

from itertools import combinations
from math import ceil
from xml.etree import ElementTree as ET

from .lane_geometry import lane_links, lane_shapes


# The four signal nodes at Roosevelt and Honduras bound one open intersection.
# The input sources and the movement validation are documented with the pilot.
CROSSINGS = (('1360014840', '13966777057', '13966777058', '2375592994'),)
CROSSING_CONTROL_REVISION = 2
ROOSEVELT_APPROACHES = {'426635857', '426635855#0'}
HONDURAS_APPROACH = '1532518649#0'


def joined_id(nodes):
    return 'cluster_' + '_'.join(nodes)


def write_elements(path, root_name, elements):
    root = ET.Element(root_name)
    root.extend(elements)
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def through_movements(network, nodes, read_network):
    """Find the exterior movements of the cluster, without same-arm returns."""
    edges, forward, _ = read_network(network, 'passenger')
    entering = [key for key, edge in edges.items() if edge.destination in nodes and edge.origin not in nodes]
    leaving = {key for key, edge in edges.items() if edge.origin in nodes and edge.destination not in nodes}
    inside = {key for key, edge in edges.items() if edge.origin in nodes and edge.destination in nodes}
    result = set()
    for entry in entering:
        pending = list(forward[entry])
        visited = {entry}
        while pending:
            edge = pending.pop()
            if edge in visited:
                continue
            visited.add(edge)
            if edge in inside:
                pending.extend(forward[edge])
            elif edge in leaving and edges[edge].destination != edges[entry].origin:
                result.add((entry, edge))
    return result


def protected_program(network, identifier):
    """Use the observed turn phase and estimated through and side-street phases."""
    junction = network.find(f'junction[@id="{identifier}"]')
    requests = {int(item.get('index')): item.get('foes')[::-1] for item in junction.findall('request')}
    int_lanes = {lane: index for index, lane in enumerate(junction.get('intLanes').split())}
    connections = [link for link in network.findall('connection[@tl]') if link.get('tl') == identifier]
    lanes = lane_shapes(network)
    speeds = {lane.get('id'): float(lane.get('speed')) for lane in network.iterfind('edge/lane')}
    lane_graph = lane_links(network)
    request_by_link = {}
    clearance_by_link = {}
    avenue_through, observed_turns, side_streets, permissive = set(), set(), set(), set()
    for link in connections:
        index = int(link.get('linkIndex'))
        destination = f"{link.get('to')}_{link.get('toLane')}"
        lane = link.get('via')
        traveled = []
        while lane != destination and lane.startswith(':') and lane not in traveled:
            traveled.append(lane)
            successors = lane_graph.get(lane, [])
            if len(successors) != 1:
                break
            lane = successors[0]
        if lane != destination or not traveled or traveled[-1] not in int_lanes or index in request_by_link:
            raise ValueError(f'No se pudo verificar el movimiento {index} en {identifier}.')
        request_by_link[index] = int_lanes[traveled[-1]]
        clearance_by_link[index] = sum(lanes[key]['length'] / speeds[key] for key in traveled) + 12 / speeds[traveled[-1]]
        edge, direction = link.get('from'), link.get('dir', '').lower()
        if edge in ROOSEVELT_APPROACHES:
            (observed_turns if direction == 'l' else avenue_through).add(index)
        elif direction == 'l':
            permissive.add(index)
        else:
            side_streets.add(index)
            if edge == HONDURAS_APPROACH and direction == 'r':
                observed_turns.add(index)
    if not connections or set(request_by_link) != set(range(len(connections))) or set(request_by_link.values()) != set(requests):
        raise ValueError(f'El controlador {identifier} no coincide con su matriz de conflictos.')

    def conflict(first, second):
        a, b = request_by_link[first], request_by_link[second]
        return requests[a][b] == '1' or requests[b][a] == '1'

    program = ET.Element('tlLogic', id=identifier, type='static', programID='0', offset='0')
    for protected, yielding in [(avenue_through, set()), (observed_turns, set()), (side_streets, permissive)]:
        if not protected or any(conflict(a, b) for a, b in combinations(protected, 2)):
            raise ValueError(f'La fase protegida de {identifier} contiene movimientos incompatibles.')
        active = protected | yielding
        green = ''.join('G' if i in protected else 'g' if i in yielding else 'r' for i in range(len(connections)))
        yellow = ''.join('y' if i in active else 'r' for i in range(len(connections)))
        clearance = max(2, ceil(max(clearance_by_link[i] for i in active)))
        for state, seconds in [(green, 20), (yellow, 3), ('r' * len(connections), clearance)]:
            ET.SubElement(program, 'phase', duration=str(seconds), state=state)
    return program


def rebuild_crossings(directory, network, netconvert, env, run_tool, read_network):
    nodes = {node.get('id'): node.get('type') for node in network.findall('junction')}
    candidates = [group for group in CROSSINGS if all(nodes.get(key, '').startswith('traffic_light') for key in group)]
    if not candidates:
        return network
    expected = {joined_id(group): through_movements(network, set(group), read_network) for group in candidates}
    joins = [ET.Element('join', nodes=' '.join(group), id=joined_id(group), type='traffic_light') for group in candidates]
    write_elements(directory / 'crossing-joins.nod.xml', 'nodes', joins)
    convert = [netconvert, '--offset.disable-normalization', 'true', '--no-turnarounds', 'true']
    run_tool([*convert, '--sumo-net-file', 'network.net.xml', '--node-files', 'crossing-joins.nod.xml',
              '--output-file', 'crossings-joined.net.xml'], directory, env, 'La unión física de los cruces semaforizados')
    merged = ET.parse(directory / 'crossings-joined.net.xml')
    for link in merged.findall('connection[@tl]'):
        if link.get('tl') in expected and link.get('dir') in {'t', 'T'}:
            expected[link.get('tl')].discard((link.get('from'), link.get('to')))
    deletes = [ET.Element('delete', {key: link.get(key) for key in ('from', 'to', 'fromLane', 'toLane')})
               for link in merged.findall('connection[@tl]') if link.get('tl') in expected and
               (link.get('dir') in {'t', 'T'} or (link.get('from'), link.get('to')) not in expected[link.get('tl')])]
    # OSM assigns the two right-hand lanes to through traffic in both directions.
    through = {'from': '426635857', 'to': '228612646#0'}
    if ('426635857', '228612646#0') in expected.get(joined_id(CROSSINGS[0]), set()):
        deletes.append(ET.Element('delete', through))
        lane_overrides = [ET.Element('connection', through, fromLane=str(i), toLane=str(i)) for i in (0, 1)]
    else:
        lane_overrides = []
    write_elements(directory / 'crossing-connections.con.xml', 'connections', [*deletes, *lane_overrides])
    run_tool([*convert, '--sumo-net-file', 'crossings-joined.net.xml', '--connection-files', 'crossing-connections.con.xml',
              '--output-file', 'crossings-lanes.net.xml'], directory, env, 'La reconstrucción de los movimientos')
    network = ET.parse(directory / 'crossings-lanes.net.xml')
    programs = []
    for identifier, movements in expected.items():
        actual = through_movements(network, {identifier}, read_network)
        if not actual or movements != actual:
            raise ValueError(f'La unión física de {identifier} cambió sus movimientos exteriores.')
        programs.append(protected_program(network, identifier))
    write_elements(directory / 'crossing-programs.tll.xml', 'tlLogics', programs)
    run_tool([*convert, '--sumo-net-file', 'crossings-lanes.net.xml', '--tllogic-files', 'crossing-programs.tll.xml',
              '--output-file', 'network.net.xml', '--plain-output-prefix', 'map', '--proj.plain-geo', 'true',
              '--plain-output.lanes', 'true', '--precision.geo', '7'], directory, env, 'La compilación del programa de tres fases')
    return ET.parse(directory / 'network.net.xml')
