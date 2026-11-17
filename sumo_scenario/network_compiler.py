"""Opt-in continuation of a frozen SUMO network package (manifest schema 1)."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET

from .compound_crossings import CROSSINGS, joined_id, rebuild_crossings
from .study import StudyError, read_network, run_tool, sumo_tools, write_json


OPERATIONS = ('geometry-adjustment', 'compound-crossings')
STAGES = {'intermediate': 1, 'final': 2}
FINAL_ARTIFACTS = {'network.net.xml', 'recorte.osm.xml', 'map.nod.xml', 'map.edg.xml',
                   'map.con.xml', 'map.tll.xml', 'map.typ.xml', 'crossing-joins.nod.xml',
                   'crossing-connections.con.xml', 'crossing-programs.tll.xml',
                   'crossings-joined.net.xml', 'crossings-lanes.net.xml'}


class PackageError(ValueError):
    """The package cannot be resumed with the declared inputs and stage."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackageError(f'Campo duplicado en el manifiesto: {key}')
        result[key] = value
    return result


def _digest(value, field):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise PackageError(f'SHA-256 inválido en {field}.')
    return value


def _load_package(manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
    if not isinstance(manifest, dict) or type(manifest.get('schemaVersion')) is not int or manifest['schemaVersion'] != 1:
        raise PackageError('Versión de manifiesto desconocida.')
    for key in ('packageId', 'revision'):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise PackageError(f'Falta {key} en el manifiesto.')
    stage = manifest.get('stage')
    if not isinstance(stage, str) or stage not in STAGES:
        raise PackageError('Etapa de red incompatible.')
    split = STAGES[stage]
    if (manifest.get('applied') != list(OPERATIONS[:split])
            or manifest.get('pending') != list(OPERATIONS[split:])):
        raise PackageError('Operaciones duplicadas o inconsistentes con la etapa de red.')
    artifacts = manifest.get('artifacts')
    if not isinstance(artifacts, dict) or 'network.net.xml' not in artifacts:
        raise PackageError('Falta el artefacto requerido network.net.xml.')

    contents = {}
    for name, spec in artifacts.items():
        if name not in FINAL_ARTIFACTS:
            raise PackageError(f'Nombre de artefacto inválido: {name}')
        if stage == 'intermediate' and name != 'network.net.xml':
            raise PackageError('La etapa intermedia solo admite la red completa. Las pasadas generan sus auxiliares.')
        if not isinstance(spec, dict) or not isinstance(spec.get('path'), str) or not spec['path']:
            raise PackageError(f'Falta la referencia de {name}.')
        path = Path(spec['path'])
        directory = manifest_path.parent
        if path.anchor or not (directory / path).resolve().is_relative_to(directory):
            raise PackageError(f'La referencia de {name} queda fuera del paquete.')
        data = (directory / path).read_bytes()
        if sha256(data).hexdigest() != _digest(spec.get('sha256'), name):
            raise PackageError(f'El SHA-256 de {name} no coincide.')
        contents[name] = data

    network = ET.ElementTree(ET.fromstring(contents['network.net.xml']))
    if network.getroot().tag != 'net' or network.find('location') is None or network.find('edge[@from]/lane') is None:
        raise PackageError('Se requiere una red SUMO completa con ubicación y carriles exteriores.')
    return manifest, contents, network


def _pending_crossings(network):
    nodes = {node.get('id'): node.get('type', '') for node in network.findall('junction')}
    return [group for group in CROSSINGS if all(nodes.get(key, '').startswith('traffic_light') for key in group)]


def compile_package(manifest_path, output):
    """Copy or resume a package. The receipt records execution, not baseline acceptance."""
    manifest_path = Path(manifest_path).resolve()
    output = Path(output).resolve()
    try:
        manifest, contents, network = _load_package(manifest_path)
        if output.is_relative_to(manifest_path.parent):
            raise PackageError('La salida debe quedar fuera del paquete fuente.')
        pending_crossings = _pending_crossings(network)
        if bool(pending_crossings) != bool(manifest['pending']):
            raise PackageError('La etapa declarada no coincide con los cruces pendientes de la red.')
        if any(network.find(f'junction[@id="{joined_id(group)}"]') is not None for group in pending_crossings):
            raise PackageError('La red ya contiene el resultado de una operación declarada pendiente.')
        if manifest['pending']:
            expected = _digest(manifest.get('netconvertSha256'), 'netconvertSha256')
            _, netconvert, env = sumo_tools()
            if sha256(Path(netconvert).read_bytes()).hexdigest() != expected:
                raise PackageError('El SHA-256 de netconvert no coincide con el manifiesto.')

        output.mkdir(exist_ok=False)
        for name, data in contents.items():
            (output / name).write_bytes(data)
        if manifest['pending']:
            final_network = rebuild_crossings(output, network, netconvert, env, run_tool, read_network)
            if (_pending_crossings(final_network)
                    or any(final_network.find(f'junction[@id="{joined_id(group)}"]') is None
                           for group in pending_crossings)
                    or not (output / 'crossing-programs.tll.xml').is_file()):
                raise PackageError('La operación pendiente no completó la reconstrucción declarada.')

        result = {
            'schemaVersion': 1,
            'packageId': manifest['packageId'],
            'revision': manifest['revision'],
            'sourceStage': manifest['stage'],
            'sourceNetworkSha256': sha256(contents['network.net.xml']).hexdigest(),
            'stage': 'final',
            'applied': list(OPERATIONS),
            'executed': manifest['pending'],
            'pending': [],
            'artifacts': {file.name: {'path': file.name, 'sha256': sha256(file.read_bytes()).hexdigest()}
                          for file in sorted(output.glob('*.xml'))},
        }
        if manifest['pending']:
            result['netconvertSha256'] = expected
        write_json(output / 'compilation-result.json', result)
        return output / 'network.net.xml'
    except (OSError, ET.ParseError, StudyError, ValueError) as error:
        if isinstance(error, PackageError):
            raise
        raise PackageError(str(error)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path, help='New directory with an existing parent')
    args = parser.parse_args()
    try:
        print(compile_package(args.manifest, args.output))
    except PackageError as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
