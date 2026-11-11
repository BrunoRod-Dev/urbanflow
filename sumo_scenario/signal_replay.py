"""Record the actual simulated signal states and locate them at the lane ends."""

from collections import defaultdict
from xml.etree import ElementTree as ET


def prepare_signal_recording(network, directory):
    if network.find('tlLogic') is None:
        return []
    additional = ET.Element('additional')
    ET.SubElement(additional, 'timedEvent', type='SaveTLSStates', dest='signal-states.xml')
    ET.ElementTree(additional).write(directory / 'signals.add.xml', encoding='utf-8', xml_declaration=True)
    return ['--additional-files', 'signals.add.xml']


def signal_replay(directory, network):
    states_file = directory / 'signal-states.xml'
    if not states_file.is_file():
        return None

    states = defaultdict(list)
    root = None
    for event, node in ET.iterparse(states_file, events=('start', 'end')):
        if root is None:
            root = node
        if event != 'end' or node.tag != 'tlsState':
            continue
        state = node.get('state')
        timeline = states[node.get('id')]
        if not timeline or timeline[-1][1] != state:
            timeline.append([float(node.get('time')), state])
        root.remove(node)

    positions = {}
    for edge in ET.parse(directory / 'map.edg.xml').findall('edge'):
        for lane in edge.findall('lane'):
            shape = lane.get('shape', '').split()
            if shape:
                positions[edge.get('id'), lane.get('index')] = [float(value) for value in shape[-1].split(',')[:2]]

    approaches = defaultdict(set)
    for link in network.findall('connection[@tl][@linkIndex]'):
        lane = (link.get('from'), link.get('fromLane'))
        controller = link.get('tl')
        if lane in positions and controller in states:
            approaches[(controller, lane)].add(int(link.get('linkIndex')))
    return {
        'states': dict(states),
        'approaches': [{'controller': controller, 'point': positions[lane], 'indices': sorted(indices)}
                       for (controller, lane), indices in approaches.items()],
    }
