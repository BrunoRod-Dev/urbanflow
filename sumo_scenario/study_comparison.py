"""Measure two completed SUMO runs over the same observation window."""

from collections import defaultdict
import json
import xml.etree.ElementTree as ET

from .study import StudyError, saved_catalog, traffic_details


STOPPED_SPEED = 0.1  # m/s, same as SUMO TripInfo waitingTime
QUEUE_GAP = 8.0  # metres, from stop line to head and between stopped bumpers


class ComparisonError(ValueError):
    pass


def queue_on_lane(length, vehicles):
    """Return the distance from the end of a lane to its last queued bumper."""
    tail = length
    queued = False
    for position, vehicle_length, speed in sorted(vehicles, reverse=True):
        if speed > STOPPED_SPEED or tail - position > QUEUE_GAP:
            break
        tail = min(tail, position - vehicle_length)
        queued = True
    return (length - max(0, tail), tail <= QUEUE_GAP) if queued else (0, False)


def queue_peaks(path, lanes, lengths, horizon, accesses):
    steps = ET.iterparse(path, events=('start', 'end'))
    _, root = next(steps)
    sampled = False
    for event, step in steps:
        if event != 'end' or step.tag != 'timestep':
            continue
        time = float(step.attrib['time'])
        if time >= horizon:
            break
        sampled = True
        by_lane = defaultdict(list)
        for car in step.iterfind('vehicle'):
            lane = car.get('lane')
            if lane in lanes:
                by_lane[lane].append((float(car.attrib['pos']), lengths[car.attrib['type']], float(car.attrib['speed'])))
        for lane, vehicles in by_lane.items():
            entry, length = lanes[lane]
            distance, reached_start = queue_on_lane(length, vehicles)
            access = accesses[entry]
            distance = round(distance, 1)
            if distance > access['peakQueueMeters']:
                access.update(peakQueueMeters=distance, peakQueueSeconds=time)
            access['queueReachedStart'] |= reached_start
        root.remove(step)
    if not sampled:
        raise ValueError('No samples in the observation window')


def measure_run(directory, metadata, network, horizon):
    catalog, counts = saved_catalog(directory, metadata)
    traffic = metadata.get('traffic') or traffic_details(catalog, counts, (metadata['seconds'] + 59) // 60, 'sample')
    demand = ET.parse(directory / 'routes.rou.xml')
    lengths = {item.attrib['id']: float(item.attrib['length']) for item in demand.iterfind('vType')}
    routes = {item.attrib['id']: tuple(item.attrib['edges'].split()) for item in demand.iterfind('route')}
    route_entries = {(tuple(route), move['kind']): move['entry'] for move in catalog for route in move['routes']}
    flows = {flow.attrib['id']: route_entries[(routes[flow.attrib['route']], flow.attrib['type'])]
             for flow in demand.iterfind('flow')}
    accesses = {}
    for move in catalog:
        access = accesses.setdefault(move['entry'], {
            'id': move['entry'], 'name': move['from'], 'planned': 0, 'completed': 0,
            'meanWaitSeconds': None, 'peakQueueMeters': 0, 'peakQueueSeconds': None, 'queueReachedStart': False,
        })
        access['planned'] += counts[move['id']]

    waited = defaultdict(float)
    for trip in ET.parse(directory / 'trips.xml').iterfind('tripinfo'):
        if not 0 <= float(trip.attrib['arrival']) < horizon or trip.get('vaporized') not in (None, '', 'false', '0'):
            continue
        entry = flows[trip.attrib['id'].rsplit('.', 1)[0]]
        accesses[entry]['completed'] += 1
        waited[entry] += float(trip.attrib['waitingTime'])
    for entry, access in accesses.items():
        if access['completed']:
            access['meanWaitSeconds'] = round(waited[entry] / access['completed'], 1)

    lanes = {lane.attrib['id']: (edge.attrib['id'], float(lane.attrib['length']))
             for edge in network.iterfind('edge') if edge.get('id') in accesses for lane in edge.iterfind('lane')}
    if not flows or not lanes:
        raise ValueError('Missing approach data')
    with (directory / 'trajectories.xml').open('rb') as trace:
        queue_peaks(trace, lanes, lengths, horizon, accesses)
    return {
        'id': directory.name,
        'traffic': {key: traffic[key] for key in ('source', 'durationMinutes')},
        'planned': sum(access['planned'] for access in accesses.values()),
        'completed': sum(access['completed'] for access in accesses.values()),
        'accesses': list(accesses.values()),
    }


def compare_studies(first, second):
    if first == second:
        raise ComparisonError('Elegí dos corridas distintas.')
    try:
        metadata = []
        for run in (first, second):
            file = run / 'metadata.json'
            metadata.append(json.loads((file if file.is_file() else run / 'replay.json').read_text(encoding='utf-8')))
        network_files = [run / 'network.net.xml' for run in (first, second)]
        if not metadata[0]['osmNodes'] or sorted(metadata[0]['osmNodes']) != sorted(metadata[1]['osmNodes']):
            raise ComparisonError('Estas corridas corresponden a cruces distintos. Elegí dos del mismo estudio.')
        if (network_files[0].read_bytes() != network_files[1].read_bytes()
                and ET.canonicalize(from_file=network_files[0]) != ET.canonicalize(from_file=network_files[1])):
            raise ComparisonError('Estas corridas usan redes distintas. Elegí dos corridas del mismo estudio.')
        network = ET.parse(network_files[0])
        horizon = min(data['seconds'] for data in metadata)
        if horizon <= 0:
            raise ValueError('Invalid observation window')
        return {'title': metadata[0]['title'], 'seconds': horizon,
                'runs': [measure_run(run, data, network, horizon) for run, data in zip((first, second), metadata)]}
    except ComparisonError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration, ET.ParseError, StudyError) as error:
        raise ComparisonError('Faltan datos de SUMO en una de las corridas. Elegí otra o generá una nueva.') from error
