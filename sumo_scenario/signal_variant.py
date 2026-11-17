"""Read a run's real tlLogic and keep experimental drafts away from that run."""

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from threading import Lock
from uuid import uuid4
from xml.etree import ElementTree as ET

from sumo_scenario.study import write_json


WORKSPACE = Path(__file__).resolve().parents[1]
VARIANTS = WORKSPACE / 'results' / 'signal-variants'
STATUS = 'borrador experimental'
RUNNING_STATUS = 'ejecutando'
DONE_STATUS = 'finalizado'
ERROR_STATUS = 'error'
KNOWN_STATUSES = {STATUS, RUNNING_STATUS, DONE_STATUS, ERROR_STATUS}
EXPERIMENTAL_PROGRAM_ID = 'experimental'
CONTROLLER_ID = re.compile(r'[A-Za-z0-9_.:-]{1,160}')
TIME_FIELDS = {
    'duration': 'non-negative',
    'minDur': 'sentinel',
    'maxDur': 'sentinel',
    'earliestEnd': 'sentinel',
    'latestEnd': 'sentinel',
    'yellow': 'non-negative',
    'red': 'non-negative',
    'vehext': 'non-negative',
}
LOCKED_FIELDS = {'state', 'name', 'next', 'earlyTarget', 'finalTarget'}
KNOWN_FIELDS = TIME_FIELDS.keys() | LOCKED_FIELDS
PROVENANCE = {'inferred': 'Inferida', 'validated': 'Validada', 'partial': 'Parcial'}
LOCK = Lock()


class SignalVariantError(ValueError):
    def __init__(self, message, *, http_status=422):
        super().__init__(message)
        self.http_status = http_status


def read_program(directory, controller_id):
    if not CONTROLLER_ID.fullmatch(controller_id or ''):
        raise SignalVariantError('El identificador del controlador no es válido.')
    inspected, programs = _load_programs(directory, controller_id)
    provenance = _provenance(controller_id)
    if isinstance(programs, str):
        return _blocked(directory, controller_id, programs, inspected, provenance)
    active = programs.get('0')
    if active is None:
        reason = (f'El controlador {controller_id} no tiene un programa con programID 0. '
                  'No se elige otro programa en su lugar.')
        return _blocked(directory, controller_id, reason, inspected, provenance)
    return {
        'editable': True,
        'reason': None,
        'runId': directory.name,
        'controllerId': controller_id,
        'provenance': provenance,
        'provenanceLabel': PROVENANCE.get(provenance, 'Desconocida'),
        'sources': inspected,
        'program': active,
        'otherProgramIds': sorted(program_id for program_id in programs if program_id != '0'),
        'editableFields': _editable_fields(active),
    }


def create_variant(directory, controller_id):
    program = read_program(directory, controller_id)
    if not program['editable']:
        raise SignalVariantError(program['reason'])
    now = _now()
    identifier = _new_id()
    variant = {
        'id': identifier,
        'status': STATUS,
        'createdAt': now,
        'updatedAt': now,
        'baseRunId': directory.name,
        'baseDirectory': _relative(directory),
        'controllerId': controller_id,
        'programId': '0',
        'provenance': program['provenance'],
        'provenanceLabel': program['provenanceLabel'],
        'sources': program['sources'],
        'integrity': _integrity(directory),
        'original': program['program'],
        'proposed': json.loads(json.dumps(program['program'])),
    }
    variant['contract'] = execution_contract(variant, directory)
    with LOCK:
        path = _variant_path(identifier)
        if path.exists():
            raise SignalVariantError('Ya existe una variante con ese identificador. No se reemplazó.')
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, variant)
    return variant


def read_variant(identifier):
    return json.loads(_variant_path(identifier).read_text(encoding='utf-8'))


def list_variants(run_id, controller_id):
    if not CONTROLLER_ID.fullmatch(controller_id or ''):
        raise SignalVariantError('El identificador del controlador no es válido.')
    found = []
    root = VARIANTS
    if not root.is_dir():
        return []
    for path in root.glob('*.json'):
        if not re.fullmatch(r'[a-f0-9]{32}', path.stem):
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if (data.get('baseRunId') == run_id and data.get('controllerId') == controller_id
                and data.get('status') in KNOWN_STATUSES):
            found.append({'id': data['id'], 'createdAt': data.get('createdAt'), 'updatedAt': data.get('updatedAt'),
                          'status': data['status']})
    return sorted(found, key=lambda item: (item.get('updatedAt') or '', item['id']), reverse=True)


def update_variant(identifier, proposed):
    with LOCK:
        variant = read_variant(identifier)
        _require_draft(variant)
        directory = _base_directory(variant)
        _require_same_base(directory, variant)
        variant['proposed'] = validate_proposed(variant['original'], proposed)
        if variant.get('status') == ERROR_STATUS:
            variant['status'] = STATUS
            variant.pop('execution', None)
        variant['updatedAt'] = _now()
        variant['contract'] = execution_contract(variant, directory)
        write_json(_variant_path(identifier), variant)
        return variant


def reset_variant(identifier):
    with LOCK:
        variant = read_variant(identifier)
        _require_draft(variant)
        directory = _base_directory(variant)
        _require_same_base(directory, variant)
        variant['proposed'] = json.loads(json.dumps(variant['original']))
        if variant.get('status') == ERROR_STATUS:
            variant['status'] = STATUS
            variant.pop('execution', None)
        variant['updatedAt'] = _now()
        variant['contract'] = execution_contract(variant, directory)
        write_json(_variant_path(identifier), variant)
        return variant


def validate_proposed(original, proposed):
    if not isinstance(proposed, dict):
        raise SignalVariantError('La variante tiene que repetir el programa original con sus tiempos modificados.')
    allowed = {'phases', 'type', 'programID', 'source'}
    if 'offset' in original:
        allowed.add('offset')
    if 'params' in original:
        allowed.add('params')
    for key in ('type', 'programID', 'source'):
        if key in proposed and proposed[key] != original[key]:
            raise SignalVariantError('La variante no puede cambiar el tipo, el programa o la fuente del tlLogic.')
    unknown = set(proposed) - allowed
    if unknown:
        raise SignalVariantError(f'La variante incluye datos que el programa no tiene: {", ".join(sorted(unknown))}.')
    result = {'type': original['type'], 'programID': original['programID'], 'source': original['source'], 'phases': []}
    if 'offset' in original:
        result['offset'] = _time(proposed.get('offset'), 'float', 'desfase')
        if _same_number(result['offset'], original['offset']) or result['offset'] == original['offset']:
            result['offset'] = original['offset']
    if 'params' in original:
        if proposed.get('params') != original['params']:
            raise SignalVariantError('Los parámetros auxiliares del programa no se modifican en esta etapa.')
        result['params'] = json.loads(json.dumps(original['params']))
    phases = proposed.get('phases')
    if not isinstance(phases, list) or len(phases) != len(original['phases']):
        raise SignalVariantError('La variante tiene que conservar la cantidad de fases del programa original.')
    for index, (current, incoming) in enumerate(zip(original['phases'], phases), start=1):
        if not isinstance(incoming, dict):
            raise SignalVariantError(f'La fase {index} no tiene el formato del programa original.')
        if set(incoming) != set(current):
            raise SignalVariantError(f'La fase {index} no conserva los parámetros del programa original.')
        phase = {}
        for field, value in current.items():
            if field in LOCKED_FIELDS:
                if incoming.get(field) != value:
                    raise SignalVariantError(f'La fase {index} no puede cambiar { _field_label(field) }.')
                phase[field] = value
            elif field in TIME_FIELDS:
                updated = _time(incoming.get(field), TIME_FIELDS[field], f'{_field_label(field)} de la fase {index}')
                phase[field] = value if _same_number(updated, value) else updated
            else:
                raise SignalVariantError(f'La fase {index} tiene un parámetro no admitido.')
        _check_bounds(phase, index)
        result['phases'].append(phase)
    return result


def execution_contract(variant, directory):
    """Describe a future child run without starting SUMO or relaxing comparison."""
    differences = _differences(variant['original'], variant['proposed'])
    integrity = _integrity_status(directory, variant.get('integrity') or {})
    reasons = [
        'start_rerun() exige conteos de tránsito y no recibe un programa semafórico. Esta ejecución no lo usa.',
        'compare_studies() solo acepta dos corridas cuya network.net.xml sea idéntica en bytes o en XML canónico, con los mismos osmNodes. Esa regla no se afloja.',
        'SUMO 1.26 rechaza otro tlLogic con el mismo programID y activa el último programa cargado si el programID es distinto.',
    ]
    if not integrity['matches']:
        reasons.append('Los archivos de la corrida base ya no coinciden con los registrados en la variante.')
    if not (directory / 'routes.rou.xml').is_file():
        reasons.append('La corrida base no tiene routes.rou.xml para repetir la demanda.')
    return {
        'contractVersion': 1,
        'action': 'sumo-signal-variant',
        'simulate': False,
        'comparisonEnabled': False,
        'baseRunId': variant['baseRunId'],
        'baseDirectory': variant['baseDirectory'],
        'variantId': variant['id'],
        'controllerId': variant['controllerId'],
        'programId': variant['programId'],
        'apply': {
            'method': 'additional-tlLogic',
            'fileName': 'signal-variant.tll.xml',
            'loadedProgramID': EXPERIMENTAL_PROGRAM_ID,
            'activation': 'last-loaded-program',
            'networkFile': 'network.net.xml',
            'networkMustRemain': 'identical',
            'routesFile': 'routes.rou.xml',
            'preserve': ['network.net.xml', 'routes.rou.xml', 'seed', 'traffic'],
        },
        'childRun': {'independent': True, 'parentId': variant['baseRunId'], 'directory': None},
        'differences': differences,
        'integrity': integrity,
        'summary': ('El borrador no modifica la corrida publicada. '
                    'Ejecutar la variante crea corridas hijas con la misma red, la misma demanda y la misma semilla.'),
        'reasons': reasons,
    }


def _load_programs(directory, controller_id):
    try:
        listed = _input_files(directory)
    except (OSError, ET.ParseError, SignalVariantError) as error:
        return [], str(error)
    inspected = []
    programs = {}
    for name, role in listed:
        path = directory / name
        if not path.is_file():
            return inspected, f'Falta {name}, declarado como archivo de entrada de la corrida.'
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            return inspected, f'{name} no tiene un XML legible.'
        found = False
        for logic in root.iter('tlLogic'):
            if logic.get('id') != controller_id:
                continue
            parsed = _parse_logic(logic, name)
            if isinstance(parsed, str):
                return inspected, parsed
            found = True
            programs[parsed['programID']] = parsed
        inspected.append({'file': name, 'role': role, 'sha256': _sha256(path), 'definesProgram': found})
    if not programs:
        names = ' y '.join(item['file'] for item in inspected) or 'ningún archivo de entrada'
        return inspected, (f'El controlador {controller_id} no tiene un tlLogic en {names}. '
                           'Los estados del replay no se usan como programa.')
    return inspected, programs


def _input_files(directory):
    configs = sorted(path for path in directory.glob('*.sumocfg') if path.is_file())
    if configs:
        return _files_from_config(directory, configs[0])
    files = [('network.net.xml', 'net-file')]
    if (directory / 'signals.add.xml').is_file():
        files.append(('signals.add.xml', 'additional-file'))
    return files


def _files_from_config(directory, config):
    try:
        root = ET.parse(config).getroot()
    except (OSError, ET.ParseError) as error:
        raise SignalVariantError(f'{config.name} no tiene un XML legible.') from error
    files = []
    net = root.find('./input/net-file')
    if net is not None and net.get('value'):
        files.append((_safe_input(directory, net.get('value')), 'net-file'))
    additional = root.find('./input/additional-files')
    if additional is not None and additional.get('value'):
        for name in additional.get('value').split(','):
            if name.strip():
                files.append((_safe_input(directory, name.strip()), 'additional-file'))
    if not files:
        raise SignalVariantError(f'{config.name} no declara la red ni archivos adicionales.')
    return files


def _safe_input(directory, value):
    path = Path(value)
    if path.is_absolute() or any(part in {'', '.', '..'} for part in path.parts):
        raise SignalVariantError('La configuración de la corrida apunta fuera de su carpeta.')
    try:
        (directory / path).resolve().relative_to(directory.resolve())
    except ValueError as error:
        raise SignalVariantError('La configuración de la corrida apunta fuera de su carpeta.') from error
    return path.as_posix()


def _parse_logic(logic, source):
    program_id = logic.get('programID')
    kind = logic.get('type')
    if not program_id or kind not in {'static', 'actuated', 'delay_based', 'NEMA'}:
        return f'El tlLogic de {logic.get("id")} no tiene un tipo o programID verificable.'
    phases = []
    params = []
    for child in list(logic):
        if child.tag == 'phase':
            unknown = set(child.attrib) - KNOWN_FIELDS
            if unknown or 'duration' not in child.attrib or 'state' not in child.attrib:
                names = ', '.join(sorted(unknown or {'duration', 'state'} - set(child.attrib)))
                return f'Una fase de {logic.get("id")} tiene una forma que esta etapa no puede editar ({names}).'
            phases.append(dict(child.attrib))
        elif child.tag == 'param':
            params.append({'key': child.get('key'), 'value': child.get('value')})
        else:
            return (f'El programa de {logic.get("id")} incluye {child.tag}. '
                    'Esta etapa no lo convierte en tiempos editables.')
    if not phases:
        return f'El programa de {logic.get("id")} no tiene fases.'
    parsed = {'type': kind, 'programID': program_id, 'source': source, 'phases': phases}
    if 'offset' in logic.attrib:
        parsed['offset'] = logic.get('offset')
    if params:
        parsed['params'] = params
    return parsed


def _editable_fields(program):
    fields = []
    if 'offset' in program:
        fields.append({'phase': None, 'field': 'offset'})
    for index, phase in enumerate(program['phases']):
        for field in phase:
            if field in TIME_FIELDS:
                fields.append({'phase': index, 'field': field})
    return fields


def _blocked(directory, controller_id, reason, inspected, provenance):
    return {
        'editable': False,
        'reason': reason,
        'runId': directory.name,
        'controllerId': controller_id,
        'provenance': provenance,
        'provenanceLabel': PROVENANCE.get(provenance, 'Desconocida'),
        'sources': inspected,
        'program': None,
        'otherProgramIds': [],
        'editableFields': [],
    }


def _provenance(controller_id):
    catalog = WORKSPACE / 'urbanflow-web' / 'sectors' / 'index.json'
    try:
        names = json.loads(catalog.read_text(encoding='utf-8')).get('sectors')
    except (OSError, ValueError):
        return None
    if not isinstance(names, list):
        return None
    for name in names:
        if not isinstance(name, str) or name != Path(name).name or not name.endswith('.json'):
            continue
        try:
            data = json.loads((WORKSPACE / 'urbanflow-web' / 'sectors' / name).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        for signal in data.get('signals') or []:
            if isinstance(signal, dict) and signal.get('id') == controller_id and signal.get('program') in PROVENANCE:
                return signal['program']
    return None


def _time(value, kind, label):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise SignalVariantError(f'{label} tiene que ser un número del programa SUMO.')
    if isinstance(value, str):
        text = value.strip()
        if kind == 'float' and text == 'begin':
            return 'begin'
        try:
            number = float(text)
        except ValueError as error:
            raise SignalVariantError(f'{label} tiene que ser un número del programa SUMO.') from error
    else:
        number = float(value)
    if not math.isfinite(number):
        raise SignalVariantError(f'{label} tiene que ser un número finito.')
    if kind == 'non-negative' and number < 0:
        raise SignalVariantError(f'{label} no admite un valor negativo.')
    if kind == 'sentinel' and not (number >= 0 or number == -1):
        raise SignalVariantError(f'{label} tiene que ser cero o mayor, o -1 si el programa lo deja sin límite.')
    if kind == 'float' and isinstance(value, str) and value.strip() == 'begin':
        return 'begin'
    return _format_number(number)


def _format_number(number):
    if number == -1:
        return '-1'
    text = format(number, '.10f').rstrip('0').rstrip('.')
    return text or '0'


def _same_number(left, right):
    if left == 'begin' or right == 'begin':
        return left == right
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return False


def _check_bounds(phase, index):
    pairs = (('minDur', 'maxDur', 'mínimo', 'máximo'), ('earliestEnd', 'latestEnd', 'fin más temprano', 'fin más tardío'))
    for low, high, low_label, high_label in pairs:
        if low in phase and high in phase and phase[low] != '-1' and phase[high] != '-1' and float(phase[low]) > float(phase[high]):
            raise SignalVariantError(f'En la fase {index} el {low_label} es mayor que el {high_label}.')


def _field_label(field):
    return {
        'duration': 'la duración', 'minDur': 'el mínimo', 'maxDur': 'el máximo', 'state': 'el estado',
        'offset': 'el desfase', 'earliestEnd': 'el fin más temprano', 'latestEnd': 'el fin más tardío',
        'yellow': 'el amarillo', 'red': 'el rojo', 'vehext': 'la extensión', 'name': 'el nombre', 'next': 'el enlace',
    }.get(field, field)


def _differences(original, proposed):
    rows = []
    if original.get('offset') != proposed.get('offset'):
        rows.append({'field': 'offset', 'original': original.get('offset'), 'proposed': proposed.get('offset')})
    for index, (left, right) in enumerate(zip(original['phases'], proposed['phases'])):
        for field in left:
            if left[field] != right[field]:
                rows.append({'phase': index, 'field': field, 'original': left[field], 'proposed': right[field]})
    return rows


def _integrity(directory):
    result = {}
    for name in ('network.net.xml', 'routes.rou.xml', 'replay.json'):
        path = directory / name
        result[name] = _sha256(path) if path.is_file() else None
    return result


def _integrity_status(directory, recorded):
    current = _integrity(directory)
    mismatched = sorted(name for name, digest in recorded.items() if current.get(name) != digest)
    return {'matches': not mismatched, 'mismatched': mismatched}


def _require_draft(variant):
    if variant.get('status') not in {STATUS, ERROR_STATUS}:
        raise SignalVariantError('Esta variante ya tiene una ejecución. Creá otra para modificar los tiempos.')


def _require_same_base(directory, variant):
    status = _integrity_status(directory, variant.get('integrity') or {})
    if not status['matches']:
        names = ', '.join(status['mismatched'])
        raise SignalVariantError(f'La corrida base cambió en {names}. No se guardó la variante.')


def _base_directory(variant):
    relative = variant.get('baseDirectory')
    parts = Path(relative).parts if isinstance(relative, str) else ()
    if not parts or any(part in {'', '.', '..'} for part in parts):
        raise SignalVariantError('La variante no apunta a una corrida de este proyecto.')
    path = WORKSPACE.joinpath(*parts).resolve()
    try:
        path.relative_to(WORKSPACE.resolve())
    except ValueError as error:
        raise SignalVariantError('La variante no apunta a una corrida de este proyecto.') from error
    if not (path / 'replay.json').is_file():
        raise SignalVariantError('La corrida base de la variante ya no está disponible.')
    return path


def _variant_path(identifier):
    if not re.fullmatch(r'[a-f0-9]{32}', identifier or ''):
        raise SignalVariantError('La variante indicada no existe.')
    path = (VARIANTS / f'{identifier}.json').resolve()
    try:
        path.relative_to(VARIANTS.resolve())
    except ValueError as error:
        raise SignalVariantError('La variante indicada no existe.') from error
    return path


def _new_id():
    for _ in range(5):
        identifier = uuid4().hex
        if not _variant_path(identifier).exists():
            return identifier
    raise SignalVariantError('No se pudo reservar un identificador nuevo para la variante.')


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path):
    return path.resolve().relative_to(WORKSPACE.resolve()).as_posix()


def _now():
    return datetime.now(timezone.utc).isoformat()
