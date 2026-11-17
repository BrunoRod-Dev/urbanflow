"""Bundle a QA analysis and the recorded evidence needed to review it."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

PRIMARY = ('network.net.xml', 'map.nod.xml', 'routes.rou.xml', 'sector01.sumocfg', 'signals.add.xml',
           'trajectories.xml', 'trips.xml', 'summary.xml', 'collisions.xml', 'sumo.log', 'netconvert.log',
           'simulation-result.json')
STUDY_EVIDENCE = ('network-audit.json', 'lane-observations.json', 'semantic-comparison.json',
                  'simulation-comparison.json', 'sumo-version.txt', 'netconvert-version.txt')
ROOT = Path(__file__).resolve().parents[1]


def review_files(extras):
    """Map repository files and folders to review/ members that keep their relative links."""
    paths = {}
    for extra in extras:
        extra = extra.resolve()
        for path in sorted(extra.rglob('*')) if extra.is_dir() else [extra]:
            if path.is_file():
                paths[f'review/{path.relative_to(ROOT).as_posix()}'] = path
    return paths


def pack(study, qa, destination, extras=()):
    manifest = json.loads((study / 'manifest.json').read_bytes())
    run_id = manifest['replayId']
    run = study / run_id
    summary = json.loads((qa / 'qa-summary.json').read_bytes())
    if summary['studyId'] != run_id:
        raise ValueError('El informe QA y el manifiesto corresponden a estudios distintos.')
    paths = {name: qa / name for name in ('QA_REPORT.md', 'qa-summary.json', 'qa-events.json')}
    paths.update({f'evidence/run/{name}': run / name for name in PRIMARY})
    paths.update({f'evidence/{name}': study / name for name in STUDY_EVIDENCE})
    paths.update({f'evidence/verification/{path.name}': path for path in qa.glob('*.log')})
    paths.update({name: qa / name for name in ('qa-replay-geometry.json', 'qa-replay-geometry-before.json',
                                             'integridad.json', 'replay-qa-http.json',
                                             'browser-qa.json', 'browser-map-qa.json')
                  if (qa / name).is_file()})
    paths['evidence/control-negativo/sumo.log'] = study / 'control-negativo/sumo.log'
    paths.update(review_files(extras))
    files = {name: path.read_bytes() for name, path in paths.items()}
    for name in ('network.net.xml', 'map.nod.xml'):
        member = f'evidence/run/{name}'
        files[member] = re.sub(rb'<!--.*?-->', b'', files[member], count=1, flags=re.S)
    # Keep only signal records where the state changes. The raw SHA-256 is in the study manifest.
    states = ET.parse(run / 'signal-states.xml')
    compact = ET.Element('tlsStates')
    previous = {}
    for row in states.iterfind('tlsState'):
        controller = row.attrib['id']
        state = tuple(row.attrib[key] for key in ('programID', 'phase', 'state'))
        if previous.get(controller) != state:
            compact.append(row)
        previous[controller] = state
    files['evidence/run/signal-state-changes.xml'] = ET.tostring(compact, encoding='utf-8', xml_declaration=True)
    source = dict(manifest)
    source['snapshot'] = {**manifest['snapshot'], 'path': 'sumo_scenario/regional/maldonado.osm.gz'}
    source['tools'] = {key: {**row, 'path': f'bin/{key}.exe'} for key, row in manifest['tools'].items()}
    source['originalArtifacts'] = source.pop('artifacts')
    source['archiveFiles'] = {name: sha256(content).hexdigest() for name, content in sorted(files.items())}
    source['archiveNotes'] = {
        'network.net.xml and map.nod.xml': 'Se retiraron comentarios de generación con rutas locales. Se conservan los árboles XML.',
        'signal-state-changes.xml': 'Conserva cada cambio de programa, fase o estado y su tiempo original.',
        'repeatability': 'Se conservan las huellas normalizadas de A y B. Se incluye el FCD completo de A.',
        'geometry': 'Los intervalos FCD y las posiciones calculadas por el reproductor están en qa-replay-geometry.json.',
    }
    files['manifest.json'] = json.dumps(source, ensure_ascii=False, indent=2).encode()
    for name, content in files.items():
        if re.search(rb'[A-Za-z]:[\\/]+Users[\\/]', content, flags=re.I):
            raise ValueError(f'El archivo contiene una ruta personal: {name}')
    with ZipFile(destination, 'x', ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)
    with ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError('No se pudo verificar el ZIP.')
        for name, expected in source['archiveFiles'].items():
            if sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f'El contenido del ZIP difiere de su manifiesto: {name}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('qa', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--extra', type=Path, action='append', default=[],
                        help='Archivo o carpeta del repositorio que se agrega bajo review/.')
    args = parser.parse_args()
    pack(args.study, args.qa, args.destination, args.extra)
