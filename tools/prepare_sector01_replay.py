"""Package the recorded 1C.3 same-demand run for replay without invoking SUMO."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sumo_scenario.study import write_json
from tools.sector01_reproducir import make_replay

RESULTS = ROOT / 'results'
SOURCE = RESULTS / 'etapa1c3-sector01/candidato-local/a'
ORIGINAL = RESULTS / 'etapa1c-sector01-validacion'
REPLAY_ID = '01c32026111300000000000000000001'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    out = args.destination.resolve()
    if not out.is_relative_to(RESULTS) or out == RESULTS:
        parser.error('La salida debe ser una carpeta nueva dentro de results/.')
    out.mkdir()
    study = out / REPLAY_ID
    study.mkdir()
    source_files = {name: SOURCE / name for name in ('network.net.xml', 'recorte.osm.xml')}
    source_files.update({f'map.{suffix}.xml': SOURCE / f'final.{suffix}.xml' for suffix in ('edg', 'nod')})
    source_files.update({name: SOURCE / 'same-demand' / name for name in (
        'trajectories.xml', 'routes.rou.xml', 'signal-states.xml', 'summary.xml',
        'collisions.xml', 'trips.xml', 'sumo.log',
    )})
    manifest = json.loads((ORIGINAL / 'manifest.json').read_bytes())
    assert source_files['routes.rou.xml'].read_bytes() == (
        ORIGINAL / manifest['replayId'] / 'routes.rou.xml').read_bytes()
    hashes = {}
    for name, source in source_files.items():
        shutil.copyfile(source, study / name)
        hashes[source.relative_to(ROOT).as_posix()] = sha256((study / name).read_bytes()).hexdigest()

    routes = ET.parse(study / 'routes.rou.xml').findall('route')
    probes = [(route.get('id'), route.get('edges').split(), None) for route in routes]
    summary = ET.parse(study / 'summary.xml').findall('step')[-1].attrib
    make_replay(study, out, ET.parse(study / 'network.net.xml'), probes, {'summary': summary})
    write_json(out / 'manifest.json', {
        'schemaVersion': 1, 'replayId': REPLAY_ID, 'sourceFiles': hashes,
        'revision': '1C.3 same-demand', 'fieldValidated': False, 'sumoRerun': False,
        'artifacts': {file.relative_to(out).as_posix(): sha256(file.read_bytes()).hexdigest()
                      for file in sorted(out.rglob('*')) if file.is_file()},
    })


if __name__ == '__main__':
    main()
