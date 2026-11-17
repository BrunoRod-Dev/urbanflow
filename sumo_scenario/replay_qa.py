"""Audit a recorded SUMO study and optionally compare it with a second run."""

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from hashlib import file_digest, sha256
import json
from math import cos, hypot, radians
from pathlib import Path
import re
from statistics import median
from xml.etree import ElementTree as ET

from .geo_projection import linear_axes
from .lane_geometry import dot, lane_links, lane_shapes, replay_geometry, reversed_straights, unit, vector
from .study import permits


COMPARABLE = ('trajectories.xml', 'trips.xml', 'summary.xml', 'signal-states.xml', 'collisions.xml')
STOP_SPEED = .1
STOP_SECONDS = 30
REVERSE_METERS = .35
HEADING_DEGREES = 75
POSITION_MARGIN = 5


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def number(value):
    result = float(value) if value is not None else -1
    return result if result >= 0 else None


def digest(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


@dataclass(frozen=True)
class Sample:
    time: float
    lane: str
    position: float
    speed: float
    angle: float
    x: float
    y: float

    def evidence(self, geographic):
        return {'time': self.time, 'lane': self.lane, 'positionMeters': self.position,
                'speedMetersPerSecond': self.speed, 'angleDegrees': self.angle,
                'coordinates' if geographic else 'networkXY': [self.x, self.y]}


def read_samples(path):
    vehicles = defaultdict(list)
    times = []
    with path.open('rb') as stream:
        parser = ET.iterparse(stream, events=('start', 'end'))
        _, root = next(parser)
        for event, step in parser:
            if event != 'end' or step.tag != 'timestep':
                continue
            time = float(step.attrib['time'])
            times.append(time)
            for vehicle in step.findall('vehicle'):
                vehicles[vehicle.attrib['id']].append(Sample(time, vehicle.attrib['lane'], *(
                    float(vehicle.attrib[key]) for key in ('pos', 'speed', 'angle', 'x', 'y')
                )))
            root.remove(step)
    return vehicles, times


def signed_turn(first, last):
    return (last - first + 180) % 360 - 180


def displacement(first, last, geographic):
    x, y = last.x - first.x, last.y - first.y
    return (x * 111320 * cos(radians((first.y + last.y) / 2)), y * 111320) if geographic else (x, y)


def corridor_heading(shape, lanes, projection):
    before = unit(vector(*lanes[shape['fromLane']]['points'][-2:]))
    after = unit(vector(*lanes[shape['toLane']]['points'][:2]))
    x, y = unit((before[0] + after[0], before[1] + after[1]))
    if not projection:
        return x, y
    east, north, latitude = linear_axes(projection)
    return unit(((x * east[0] + y * north[0]) * cos(radians(latitude)),
                 x * east[1] + y * north[1]))


def lane_path_exists(origin, destination, links, allowed_edges, lanes, change_allowed):
    """Search sampled transitions only over the recorded route, plus internal lanes."""
    queue = deque([origin])
    seen = {origin}
    while queue:
        current = queue.popleft()
        if current == destination:
            return True
        for following in (*links.get(current, ()), *change_allowed.get(current, ())):
            edge = lanes[following]['edge']
            if following not in seen and (edge.startswith(':') or edge in allowed_edges):
                seen.add(following)
                queue.append(following)
    return False


def route_definitions(path):
    root = ET.parse(path)
    paths = {r.get('id'): r.attrib['edges'].split() for r in root.findall('route')}
    types = {t.get('id'): t.get('vClass', 'passenger') for t in root.findall('vType')}
    planned = {}
    for vehicle in root.findall('vehicle'):
        inline = vehicle.find('route')
        route = inline.attrib['edges'].split() if inline is not None and inline.get('edges') else paths.get(vehicle.get('route'))
        planned[vehicle.attrib['id']] = (route, types.get(vehicle.get('type'), 'passenger'))
    limitations = [tag for tag in ('flow', 'trip', 'routeDistribution') if root.findall(tag)]
    return planned, limitations


def compare_runs(run, other):
    files = {}
    for name in COMPARABLE:
        if not (run / name).is_file() or not (other / name).is_file():
            files[name] = {'status': 'missing'}
            continue
        roots = [ET.parse(directory / name).getroot() for directory in (run, other)]
        if name == 'summary.xml':
            for root in roots:
                for step in root.findall('step'):
                    step.attrib.pop('duration', None)
        left, right = (ET.tostring(root) for root in roots)
        files[name] = {'status': 'match' if left == right else 'different',
                       'normalizedSha256': [sha256(data).hexdigest() for data in (left, right)]}
    return files


class Audit:
    def __init__(self, run, physical, coordinates):
        self.run = run
        self.physical = physical
        self.network = ET.parse(run / 'network.net.xml')
        self.lanes = lane_shapes(self.network)
        self.links = lane_links(self.network)
        self.edges = {edge.attrib['id']: edge for edge in self.network.findall('edge')}
        self.lane_elements = {lane.attrib['id']: lane for lane in self.network.findall('edge/lane')}
        self.positions = {n.attrib['id']: [float(n.attrib['x']), float(n.attrib['y'])]
                          for n in ET.parse(run / 'map.nod.xml').findall('node')}
        self.internal_nodes = {}
        self.internal_destinations = {}
        for junction in self.network.findall('junction'):
            if not junction.attrib['id'].startswith(':'):
                self.internal_nodes.update({lane: junction.attrib['id'] for lane in junction.get('intLanes', '').split()})
        for link in self.network.findall('connection[@via]'):
            edge = self.edges[link.attrib['from']]
            if edge.get('to'):
                self.internal_nodes[link.attrib['via']] = edge.attrib['to']
        for link in self.network.findall('connection'):
            origin, target = link.attrib['from'], link.attrib['to']
            if origin.startswith(':') and not target.startswith(':'):
                lane = f"{origin}_{link.attrib['fromLane']}"
                self.internal_destinations[lane] = target
                if link.get('via'):
                    self.internal_destinations[link.attrib['via']] = target
        configurations = list(run.glob('*.sumocfg'))
        replay = run / 'replay.json'
        if coordinates == 'auto':
            if len(configurations) == 1:
                config = ET.parse(configurations[0])
                coordinates = 'geo' if config.find('.//fcd-output.geo[@value="true"]') is not None else 'xy'
            elif replay.is_file() and isinstance(read_json(replay).get('geographic'), bool):
                coordinates = 'geo' if read_json(replay)['geographic'] else 'xy'
            else:
                raise ValueError('Indicá --fcd-coordinates geo o xy para interpretar las muestras.')
        self.geo = coordinates == 'geo'
        motion = replay_geometry(self.network, run / 'map.nod.xml')
        self.projection = motion['projection'] if motion else None
        if not self.projection:
            self.positions = {}
        self.vehicles, self.times = read_samples(run / 'trajectories.xml')
        self.step = median(b - a for a, b in zip(self.times, self.times[1:])) if len(self.times) > 1 else None
        self.events = []
        self.geometry = []
        self.runs = {}

    def location(self, lane, node=None):
        edge = self.lanes.get(lane, {}).get('edge')
        if node is None and edge:
            node = self.internal_nodes.get(lane) if edge.startswith(':') else self.edges[edge].get('to')
        return edge, node

    def add(self, kind, severity, validation, label, evidence, *, vehicle=None, sample=None,
            lane=None, node=None, time=None, coordinates=None):
        if sample:
            time, lane = sample.time, sample.lane
            if self.geo:
                coordinates = [sample.x, sample.y]
        edge, node = self.location(lane, node)
        if coordinates is None and sample is None and node:
            coordinates = self.positions.get(node)
        event = {'id': f'qa-{len(self.events) + 1:04}', 'kind': kind, 'severity': severity, 'validation': validation,
                 'label': label, 'vehicleId': vehicle, 'time': time, 'coordinates': coordinates,
                 'edge': edge, 'lane': lane, 'node': node, 'evidence': evidence}
        self.events.append(event)
        return event

    def audit_recorded_outcomes(self, planned):
        trip_rows = {r.attrib['id']: r.attrib for r in ET.parse(self.run / 'trips.xml').findall('tripinfo')}
        summary = ET.parse(self.run / 'summary.xml').getroot()
        final = summary[-1].attrib
        log = (self.run / 'sumo.log').read_text(encoding='utf-8', errors='replace').splitlines()
        collisions = ET.parse(self.run / 'collisions.xml').findall('collision')
        for row in collisions:
            vehicle, time, lane = row.get('collider'), number(row.get('time')), row.get('lane')
            sample = next((sample for sample in self.vehicles.get(vehicle, ())
                           if sample.time == time and sample.lane == lane), None)
            self.add('collision', 'error', 'recorded', 'Colisión registrada',
                     {'source': 'collisions.xml', 'record': row.attrib,
                      'coincidentFcdSample': sample.evidence(self.geo) if sample else None},
                     vehicle=vehicle, lane=lane, time=time, sample=sample)
        for kind, pattern in [('teleport', r'\bteleport(?:ing|ed)\b'),
                              ('route_error', r'no valid route|has no connection|not connected|invalid route|unknown edge')]:
            matching = [line for line in log if re.search(pattern, line, re.I)]
            self.runs[kind + 'LogLines'] = len(matching)
            for line in matching:
                vehicle = re.search(r"\bvehicle\s+'([^']+)'", line, re.I)
                time = re.search(r'\btime[=\s]+(\d+(?:\.\d+)?)', line, re.I)
                self.add(kind, 'error', 'recorded', 'Teletransporte registrado' if kind == 'teleport' else 'Error de ruta',
                         {'source': 'sumo.log', 'line': line}, vehicle=vehicle[1] if vehicle else None,
                         time=float(time[1]) if time else None)
        for kind, count in [('teleport', int(final['teleports'])), ('collision', int(final['collisions']))]:
            if count and not (self.runs.get('teleportLogLines') if kind == 'teleport' else collisions):
                self.add(kind, 'error', 'aggregate_only', 'Incidencias en el resumen de SUMO',
                         {'source': 'summary.xml', 'count': count})
        for vehicle in sorted(planned.keys() | trip_rows.keys()):
            trip = trip_rows.get(vehicle, {})
            if number(trip.get('arrival')) is None:
                self.add('incomplete_trip', 'error', 'recorded', 'Viaje sin llegada registrada',
                         {'sources': ['routes.rou.xml', 'trips.xml', 'summary.xml'], 'trip': trip or None,
                          'runEndTime': float(final['time'])}, vehicle=vehicle)
        self.runs.update({key: int(final[key]) for key in ('loaded', 'inserted', 'arrived', 'running', 'waiting',
                                                          'collisions', 'teleports', 'discarded')})
        self.runs.update(explicitVehicles=len(planned), tripRows=len(trip_rows), collisionRecords=len(collisions))

    def audit_trajectories(self, planned):
        neighbors = defaultdict(list)
        for edge in self.edges.values():
            ids = [lane.attrib['id'] for lane in edge.findall('lane')]
            for right, left in zip(ids, ids[1:]):
                neighbors[right].append((left, 'changeLeft'))
                neighbors[left].append((right, 'changeRight'))
        pairs = {(c.attrib['from'], c.attrib['to']) for c in self.network.findall('connection')
                 if not c.attrib['from'].startswith(':') and not c.attrib['to'].startswith(':')}
        for vehicle, (route, _) in sorted(planned.items()):
            if route:
                self.check_planned_route(vehicle, route, pairs)
        for vehicle, samples in sorted(self.vehicles.items()):
            route, vehicle_class = planned.get(vehicle, (None, 'passenger'))
            allowed = {}
            for lane, options in neighbors.items():
                origin = self.lane_elements[lane]
                allowed[lane] = [n for n, side in options if (origin.get(side) is None or
                                 'all' in origin.get(side).split() or vehicle_class in origin.get(side).split())
                                 and permits(self.lane_elements[n], vehicle_class)]
            index = 0
            stop_start = None
            for i, sample in enumerate(samples):
                prior = samples[i - 1] if i else None
                gap = prior is not None and not self.adjacent(prior, sample)
                if sample.speed >= STOP_SPEED or gap:
                    self.stop_event(vehicle, stop_start, prior)
                    stop_start = None
                if sample.speed < STOP_SPEED and stop_start is None:
                    stop_start = sample
                if sample.lane not in self.lanes:
                    self.add('unknown_lane', 'error', 'recorded', 'Carril de FCD ausente en la red',
                             self.pair_evidence(sample), vehicle=vehicle, sample=sample)
                    continue
                edge = self.lanes[sample.lane]['edge']
                if not permits(self.lane_elements[sample.lane], vehicle_class):
                    self.add('lane_permission', 'error', 'recorded', 'Clase incompatible con carril registrado',
                             {**self.pair_evidence(sample), 'vehicleClass': vehicle_class}, vehicle=vehicle, sample=sample)
                previous_index = index
                route_edge = self.internal_destinations.get(sample.lane) if edge.startswith(':') else edge
                if route and route_edge:
                    try:
                        index = route.index(route_edge, index)
                    except ValueError:
                        self.add('route_deviation', 'warning', 'review', 'Arista fuera del orden de la ruta de entrada',
                                 {**self.pair_evidence(sample), 'route': route}, vehicle=vehicle, sample=sample)
                        continue
                if route and prior and not gap and prior.lane in self.lanes and prior.lane != sample.lane:
                    # Internal samples may sit between successive exterior edges of the plan.
                    route_edges = set(route[max(0, previous_index - 1):index + 1])
                    if not lane_path_exists(prior.lane, sample.lane, self.links, route_edges, self.lanes, allowed):
                        self.add('lane_continuity', 'warning', 'review', 'Sin cadena de carriles en la ruta de entrada',
                                 self.pair_evidence(prior, sample), vehicle=vehicle, sample=sample)
                if prior and not gap:
                    self.check_sample_pair(vehicle, prior, sample)
            self.stop_event(vehicle, stop_start, samples[-1])

    def adjacent(self, before, after):
        return self.step is not None and 0 < after.time - before.time <= self.step * 1.1

    def pair_evidence(self, *samples):
        return {'source': 'trajectories.xml', 'samples': [s.evidence(self.geo) for s in samples]}

    def stop_event(self, vehicle, start, end):
        if start is None or end is None or end.time - start.time < STOP_SECONDS:
            return
        self.add('prolonged_stop', 'info', 'observed', 'Detención prolongada muestreada',
                 {**self.pair_evidence(start, end), 'sampledSeconds': round(end.time - start.time, 3)},
                 vehicle=vehicle, sample=start)

    def check_sample_pair(self, vehicle, prior, sample):
        delta = sample.time - prior.time
        distance = hypot(*displacement(prior, sample, self.geo))
        budget = max(prior.speed, sample.speed) * delta + POSITION_MARGIN
        turn = abs(signed_turn(prior.angle, sample.angle))
        evidence = self.pair_evidence(prior, sample)
        if distance > budget:
            self.add('position_jump', 'warning', 'review', 'Desplazamiento mayor al esperado entre muestras',
                     {**evidence, 'distanceMeters': round(distance, 3), 'thresholdMeters': round(budget, 3)},
                     vehicle=vehicle, sample=sample)
        if turn >= HEADING_DEGREES and max(prior.speed, sample.speed) >= 1:
            self.add('heading_change', 'warning', 'review', 'Cambio brusco de orientación en FCD',
                     {**evidence, 'headingChangeDegrees': round(turn, 2)}, vehicle=vehicle, sample=sample)
        if prior.lane == sample.lane and prior.position - sample.position >= REVERSE_METERS:
            self.add('lane_position_reverse', 'warning', 'observed', 'La posición longitudinal disminuye en el mismo carril',
                     {**evidence, 'reverseMeters': round(prior.position - sample.position, 3)},
                     vehicle=vehicle, sample=sample)

    def check_planned_route(self, vehicle, route, pairs):
        missing = sorted(set(zip(route, route[1:])) - pairs)
        unknown = sorted(set(route) - self.edges.keys())
        if missing or unknown:
            self.add('planned_route_gap', 'error', 'recorded', 'Ruta de entrada con aristas o enlaces ausentes',
                     {'sources': ['routes.rou.xml', 'network.net.xml'], 'missingPairs': missing,
                      'unknownEdges': unknown}, vehicle=vehicle)

    def audit_reverse_shapes(self):
        for shape in reversed_straights(self.network):
            via = shape['via']
            static = self.add('reverse_geometry', 'warning', 'static', 'Retroceso en la geometría de un carril interno',
                              {'source': 'network.net.xml', **shape}, lane=via, node=shape['junction'])
            heading = (corridor_heading(shape, self.lanes, self.projection if self.geo else None)
                       if not self.geo or self.projection else None)
            observed, windows = 0, []
            for vehicle, samples in sorted(self.vehicles.items()):
                indices = [i for i, s in enumerate(samples) if s.lane == via]
                if not indices:
                    continue
                observed += len(indices)
                pairs = sorted({j for i in indices for j in (i - 1, i) if 0 <= j < len(samples) - 1})
                windows.append({'vehicleId': vehicle, 'samples': [samples[i].evidence(self.geo)
                                for i in sorted(set(indices) | {j for k in pairs for j in (k, k + 1)})]})
                for i in pairs:
                    before, after = samples[i:i + 2]
                    if heading is None or not self.adjacent(before, after):
                        continue
                    signed = dot(heading, displacement(before, after, self.geo))
                    if signed <= -REVERSE_METERS:
                        self.add('trajectory_reverse_projection', 'warning', 'observed',
                                 'Desplazamiento FCD opuesto al eje de la conexión',
                                 {**self.pair_evidence(before, after), 'geometryEventId': static['id'],
                                  'signedMeters': round(signed, 3), 'heading': heading},
                                 vehicle=vehicle, sample=after, node=shape['junction'])
            static['evidence'].update(fcdSamples=observed, observedVehicles=len(windows))
            self.geometry.append({'eventId': static['id'], **shape, 'heading': heading,
                                  'fcdSamples': observed, 'windows': windows})

    def audit_controls(self):
        recorded = Counter(row.attrib['id'] for row in ET.parse(self.run / 'signal-states.xml').findall('tlsState'))
        controllers = {p.attrib['id']: p for p in self.network.findall('tlLogic')}
        nodes_by_controller = defaultdict(set)
        for link in self.network.findall('connection[@tl]'):
            node = self.edges[link.attrib['from']].get('to')
            if node is not None:
                nodes_by_controller[link.attrib['tl']].add(node)
        if self.physical == 'inferred':
            for controller, program in sorted(controllers.items()):
                nodes = sorted(nodes_by_controller[controller])
                self.add('inferred_signal', 'info', 'field_unverified', f'Programa inferido · {controller}',
                         {'sources': ['network.net.xml', 'signal-states.xml'], 'controller': controller,
                          'nodes': nodes, 'program': program.attrib, 'recordedSamples': recorded[controller]},
                         node=nodes[0] if len(nodes) == 1 else None,
                         coordinates=next((self.positions[n] for n in nodes if n in self.positions), None))
        priorities = Counter(j.attrib['type'] for j in self.network.findall('junction')
                             if j.get('type') in ('priority', 'right_before_left', 'priority_stop'))
        if self.physical == 'inferred' and priorities:
            self.add('inferred_priority', 'info', 'field_unverified', 'Prioridades sin corroboración física',
                     {'source': 'network.net.xml', 'junctionTypes': dict(priorities),
                      'scope': 'aggregate; some constraints may be sourced from OSM'})
        return {'controllers': len(controllers), 'recordedControllers': len(recorded),
                'phaseSamples': sum(recorded.values()), 'priorityTypes': dict(priorities),
                'fieldEvidence': self.physical}


def report(summary, geometry):
    counts = summary['eventCounts']
    run = summary['run']
    lines = ['# UrbanFlow · Informe QA', '',
             f"SUMO registró **{run['arrived']}/{run['inserted']} llegadas**, {run['collisions']} colisiones y "
             f"{run['teleports']} teletransportes. Se leyeron {summary['trajectorySamples']} muestras de vehículos.",
             f"Viajes incompletos detectados: {counts.get('incomplete_trip', 0)}. "
             f"Alertas de ruta o continuidad: {sum(counts.get(kind, 0) for kind in ('route_error', 'planned_route_gap', 'route_deviation', 'lane_continuity', 'lane_permission', 'unknown_lane'))}.",
             '', '## Eventos', '']
    lines.extend(f'- `{kind}` · {count}' for kind, count in sorted(counts.items()))
    lines.extend(['', '## Geometría, trayectoria y reproducción', ''])
    for item in geometry:
        lines.append(f"- `{item['via']}` · Retroceso estático de {item['backwardsMeters']:.2f} m. "
                     f"Muestras en el carril interno ({item['fcdSamples']}) y vehículos observados ({len(item['windows'])}).")
    lines.extend(['', 'El desplazamiento proyectado usa dos muestras de FCD en el eje de la conexión. '
                  'La velocidad registrada, el ángulo y la posición sobre el carril se conservan por separado. '
                  'Un carril sin muestras directas tiene cobertura insuficiente para atribuir un movimiento.',
                  '', 'La simulación registra el frente del vehículo. El reproductor reconstruye su centro y usa '
                  'la geometría para interpolar.'])
    if summary['replayGeometryAudited']:
        lines.extend(['', f"El cálculo de posiciones del reproductor arrojó "
                      f"{counts.get('replay_position_reverse', 0)} retrocesos adicionales entre los mismos instantes "
                      "de FCD. La evidencia se calculó con el código 2D en Node y conserva también la posición del "
                      "centro reconstruida con el rumbo de SUMO. Los resultados están en `qa-replay-geometry.json`."])
    if summary['previousReplayGeometryAudited']:
        lines.extend(['', f"La revisión anterior registró "
                      f"{summary['previousReplayReverseEvents']} retrocesos adicionales en el cálculo del reproductor. "
                      "Se conserva esa evidencia en `qa-replay-geometry-before.json`. Las alertas geométricas de la red "
                      "y los desplazamientos FCD pertenecen a la corrida original."])
    lines.extend(['', '## Repetición y controles', ''])
    lines.extend(f"- `{name}` · {item['status']}" for name, item in summary['repeatability'].items())
    control = summary['controls']
    lines.extend(['', f"{control['recordedControllers']} de {control['controllers']} controladores con estados "
                  f"registrados. Procedencia de validación física: `{control['fieldEvidence']}`.", '',
                  'Las alertas heurísticas requieren revisión. Las detenciones pueden corresponder a fases normales. '
                  'Los cambios de carril y enlaces más cortos que el paso FCD limitan la reconstrucción entre muestras.',
                  '', 'Los datos, umbrales y referencias están en `qa-summary.json` y `qa-events.json`.'])
    return '\n'.join(lines) + '\n'


def analyze(run, output, *, compare=None, physical='unknown', study_id=None, coordinates='auto',
            replay_geometry=None, previous_replay_geometry=None):
    audit = Audit(run, physical, coordinates)
    planned, limitations = route_definitions(run / 'routes.rou.xml')
    audit.audit_recorded_outcomes(planned)
    audit.audit_trajectories(planned)
    audit.audit_reverse_shapes()
    controls = audit.audit_controls()
    identifier = study_id or run.name
    def player_evidence(path):
        result = read_json(path)
        if (result['studyId'] != identifier or result['trajectoriesSha256'] != digest(run / 'trajectories.xml')
                or result['replaySha256'] != digest(run / 'replay.json')
                or {(item['geometryEventId'], item['via']) for item in result['connections']} !=
                {(item['eventId'], item['via']) for item in audit.geometry}):
            raise ValueError('La comparación visual corresponde a otro estudio o conjunto de alertas.')
        return result

    previous_player = player_evidence(previous_replay_geometry) if previous_replay_geometry else None
    if replay_geometry:
        audit.events.extend(player_evidence(replay_geometry)['events'])
    comparison = compare_runs(run, compare) if compare else {}
    for file, result in comparison.items():
        if result['status'] != 'match':
            audit.add('repeatability_difference', 'warning', 'recorded' if result['status'] == 'different' else 'missing',
                      f'Repetición · {file}', {'source': file, **result})
    summary = {
        'schemaVersion': 1, 'studyId': identifier, 'run': audit.runs,
        'thresholds': {'stoppedBelowMetersPerSecond': STOP_SPEED, 'stopSampleSpanSeconds': STOP_SECONDS,
                       'reverseMeters': REVERSE_METERS, 'headingChangeDegrees': HEADING_DEGREES,
                       'positionJumpMarginMeters': POSITION_MARGIN},
        'trajectorySamples': sum(map(len, audit.vehicles.values())), 'sampleStepSeconds': audit.step,
        'coordinateSystem': 'WGS84' if audit.geo else 'network XY',
        'controls': controls, 'repeatability': comparison, 'unsupportedDemandForms': limitations,
        'replayGeometryAudited': replay_geometry is not None,
        'previousReplayGeometryAudited': previous_player is not None,
        'previousReplayReverseEvents': len(previous_player['events']) if previous_player else None,
        'eventCounts': dict(Counter(event['kind'] for event in audit.events)),
        'sourceHashes': {name: digest(run / name) for name in (
            'network.net.xml', 'map.nod.xml', 'routes.rou.xml', 'sumo.log', *COMPARABLE)},
    }
    output.mkdir()
    if replay_geometry:
        (output / 'qa-replay-geometry.json').write_bytes(replay_geometry.read_bytes())
    if previous_replay_geometry:
        (output / 'qa-replay-geometry-before.json').write_bytes(previous_replay_geometry.read_bytes())
    save_json(output / 'qa-summary.json', summary)
    save_json(output / 'qa-events.json', {'schemaVersion': 1, 'studyId': summary['studyId'],
                                         'sourceHashes': summary['sourceHashes'],
                                         'events': audit.events, 'geometryInvestigation': audit.geometry})
    (output / 'QA_REPORT.md').write_text(report(summary, audit.geometry), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--physical', choices=('unknown', 'inferred'), default='unknown')
    parser.add_argument('--fcd-coordinates', choices=('auto', 'geo', 'xy'), default='auto')
    parser.add_argument('--study-id')
    parser.add_argument('--replay-geometry', type=Path)
    parser.add_argument('--previous-replay-geometry', type=Path)
    args = parser.parse_args()
    analyze(args.run, args.output, compare=args.compare, physical=args.physical, study_id=args.study_id,
            coordinates=args.fcd_coordinates, replay_geometry=args.replay_geometry,
            previous_replay_geometry=args.previous_replay_geometry)


if __name__ == '__main__':
    main()
