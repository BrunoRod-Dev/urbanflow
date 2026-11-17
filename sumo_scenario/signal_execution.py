"""Run one experimental signal program beside an independent control.

SUMO 1.26 rejects a second tlLogic that repeats programID and activates the
last program loaded when that id differs. A 30 s probe on the published
static controller showed programID "experimental" active from t=0, with the
edited phase lasting its proposed duration. The same id "0" aborted.
"""

import json
import math
import subprocess
import traceback
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

from sumo_scenario.export_web import fcd_frames
from sumo_scenario.lane_geometry import replay_geometry
from sumo_scenario.signal_replay import prepare_signal_recording, signal_replay
from sumo_scenario.signal_variant import (
    ERROR_STATUS, EXPERIMENTAL_PROGRAM_ID, LOCK, RUNNING_STATUS, STATUS, TIME_FIELDS,
    SignalVariantError, _base_directory, _differences, _integrity, _integrity_status,
    _now, _relative, _sha256, execution_contract, read_program, read_variant, validate_proposed,
)
from sumo_scenario.study import (
    SEED, VEHICLE_LENGTHS, VEHICLE_TYPES, StudyError, map_network, saved_catalog, sumo_tools, write_json,
)


RUNS = Path(__file__).resolve().parents[1] / 'results' / 'signal-runs'
SUMO_TIMEOUT = 120
MAX_SECONDS = 360
MAX_ROUTES_BYTES = 1_000_000
RUNNING = set()
# Ampliación posterior, no implementada: un actuado necesita detectores y min/max;
# uno inferido, una fuente verificada; un desfase distinto de 0 cambia la fase activa
# en t=0; otro programID vuelve ambiguo el último programa cargado. compare_studies()
# sigue sin mirar el programa adicional y no se afloja.


def recover_interrupted(identifier):
    """A running mark left by a closed process is an error, not another simulation."""
    with LOCK:
        variant = read_variant(identifier)
        if variant.get('status') != RUNNING_STATUS or identifier in RUNNING:
            return variant
        return _mark_interrupted(variant)


def _mark_interrupted(variant):
    message = 'La ejecución se interrumpió antes de terminar. No se publicaron métricas.'
    execution = variant.get('execution') if isinstance(variant.get('execution'), dict) else {}
    execution['error'] = message
    execution['finishedAt'] = _now()
    execution['resultsValid'] = False
    comparison = execution.get('comparison') if isinstance(execution.get('comparison'), dict) else {}
    comparison['available'] = False
    comparison['reason'] = message
    execution['comparison'] = comparison
    variant['execution'] = execution
    variant['status'] = ERROR_STATUS
    variant['updatedAt'] = execution['finishedAt']
    write_json(_variant_path_for(variant['id']), variant)
    return variant


def begin_execution(identifier):
    """Validate a draft and mark it running. This does not start SUMO."""
    with LOCK:
        variant = read_variant(identifier)
        if variant.get('status') == RUNNING_STATUS and identifier not in RUNNING:
            _mark_interrupted(variant)
            raise SignalVariantError(
                'La ejecución se interrumpió antes de terminar. No se inició otra simulación.',
                http_status=409)
        if variant.get('status') == RUNNING_STATUS and identifier in RUNNING:
            raise SignalVariantError('Ya hay una ejecución de esta variante.', http_status=409)
        if variant.get('status') not in {STATUS, ERROR_STATUS, RUNNING_STATUS}:
            raise SignalVariantError(
                'Esta variante ya fue ejecutada. Creá otra para un experimento nuevo.', http_status=409)
        directory = _base_directory(variant)
        variant['contract'] = execution_contract(variant, directory)
        _validate_request(variant, directory)
        variant['status'] = RUNNING_STATUS
        variant['updatedAt'] = _now()
        variant['execution'] = {
            'startedAt': variant['updatedAt'], 'resultsValid': False,
            'comparison': {'available': False, 'reason': 'La ejecución todavía no terminó.'},
        }
        write_json(_variant_path_for(identifier), variant)
        RUNNING.add(identifier)
        return {'id': identifier, 'status': RUNNING_STATUS}


def run_execution(identifier):
    """Run the control and the variant. Publish metrics only after both programs match."""
    try:
        with LOCK:
            variant = read_variant(identifier)
            if variant.get('status') != RUNNING_STATUS:
                return None
            snapshot = json.loads(json.dumps(variant))
            directory = _base_directory(variant)
        outcome = _execute_pair(snapshot, directory)
        with LOCK:
            current = read_variant(identifier)
            if current.get('status') != RUNNING_STATUS:
                return None
            current['execution'] = outcome
            current['status'] = _finished_status(outcome)
            current['updatedAt'] = _now()
            contract = execution_contract(current, directory)
            if outcome.get('resultsValid') and outcome.get('variantRun'):
                contract['childRun']['directory'] = outcome['variantRun']['directory']
            current['contract'] = contract
            write_json(_variant_path_for(identifier), current)
            return current
    except (SignalVariantError, StudyError) as error:
        fail_execution(identifier, str(error))
        return None
    except Exception:
        _write_unexpected(identifier)
        fail_execution(identifier, 'Ocurrió un error al ejecutar la variante. No se publicaron métricas.')
        return None
    finally:
        RUNNING.discard(identifier)


def fail_execution(identifier, message):
    with LOCK:
        RUNNING.discard(identifier)
        try:
            variant = read_variant(identifier)
        except (OSError, SignalVariantError, ValueError):
            return
        if variant.get('status') != RUNNING_STATUS:
            return
        execution = variant.get('execution') if isinstance(variant.get('execution'), dict) else {}
        execution['error'] = message
        execution['finishedAt'] = _now()
        execution['resultsValid'] = False
        comparison = execution.get('comparison') if isinstance(execution.get('comparison'), dict) else {}
        comparison['available'] = False
        comparison.setdefault('reason', message)
        execution['comparison'] = comparison
        variant['execution'] = execution
        variant['status'] = ERROR_STATUS
        variant['updatedAt'] = execution['finishedAt']
        write_json(_variant_path_for(identifier), variant)


def read_experimental_replay(identifier, role):
    if role not in {'control', 'variant'}:
        raise SignalVariantError('Elegí el control o la variante experimental.')
    variant = read_variant(identifier)
    execution = variant.get('execution') if isinstance(variant.get('execution'), dict) else {}
    if not execution.get('resultsValid'):
        raise SignalVariantError('El replay experimental se abre cuando la comparación está publicada.')
    info = execution.get('control' if role == 'control' else 'variantRun') or {}
    if not info.get('replay'):
        raise SignalVariantError('Esa corrida no tiene un replay experimental.')
    directory = _run_directory(info.get('id'))
    replay_path = directory / 'replay.json'
    if not replay_path.is_file():
        raise FileNotFoundError(replay_path)
    replay = json.loads(replay_path.read_text(encoding='utf-8'))
    if replay.get('experimental') is not True or replay.get('experimentalRole') != role:
        raise SignalVariantError('El replay no está identificado como experimental.')
    return replay


def _finished_status(outcome):
    if outcome.get('resultsValid') or outcome.get('programActive'):
        return 'finalizado'
    return ERROR_STATUS


def _execute_pair(variant, directory):
    before = _integrity(directory)
    if not _integrity_status(directory, variant.get('integrity') or {})['matches']:
        raise SignalVariantError('Los archivos de la corrida base cambiaron. No se ejecutó la variante.')
    sumo, env, version = _sumo_runtime()
    conditions = _conditions(directory)
    control_id, variant_id = _new_run_id(), _new_run_id()
    control_dir = _prepare_run(directory, control_id)
    variant_dir = _prepare_run(directory, variant_id)
    program_path = variant_dir / variant['contract']['apply']['fileName']
    _write_program(program_path, variant['controllerId'], variant['proposed'])
    program_hash = _sha256(program_path)
    period = max(.5, math.ceil(conditions['seconds'] / 1_500 * 2) / 2)
    shared = {
        'seed': conditions['seed'], 'seconds': conditions['seconds'], 'stepLength': 0.5,
        'timeToTeleport': -1, 'fcdPeriod': period, 'sumoVersion': version,
    }
    try:
        control_manifest = _simulate(control_dir, sumo, env, shared, variant, program_file=None)
        variant_manifest = _simulate(variant_dir, sumo, env, shared, variant, program_file=program_path.name)
    except SignalVariantError as error:
        _assert_base_unchanged(directory, before)
        return _blocked(variant, version, control_id, variant_id, program_hash, str(error))
    _assert_base_unchanged(directory, before)
    try:
        control_cycle = _assert_cycle(
            control_dir / 'signal-states.xml', variant['controllerId'], variant['original']['phases'], '0', 'El control')
        variant_cycle = _assert_cycle(
            variant_dir / 'signal-states.xml', variant['controllerId'], variant['proposed']['phases'],
            EXPERIMENTAL_PROGRAM_ID, 'La variante')
    except SignalVariantError as error:
        return _blocked(variant, version, control_id, variant_id, program_hash, str(error),
                        control_manifest, variant_manifest)
    compatible, reason = _compatible(control_manifest, variant_manifest, before, program_hash)
    outcome = _base_outcome(variant, version, control_id, variant_id, program_hash, control_manifest, variant_manifest)
    try:
        if not compatible:
            raise SignalVariantError(reason)
        comparison = _comparison(directory, control_dir, variant_dir, variant, conditions)
    except SignalVariantError as error:
        outcome['programActive'] = True
        outcome['evidence'] = {
            'controlProgramID': '0', 'variantProgramID': EXPERIMENTAL_PROGRAM_ID,
            'controlPhaseSeconds': control_cycle, 'variantPhaseSeconds': variant_cycle,
        }
        outcome['error'] = str(error)
        outcome['comparison'] = {'available': False, 'reason': str(error)}
        outcome['resultsValid'] = False
        return outcome
    outcome['programActive'] = True
    outcome['evidence'] = {
        'controlProgramID': '0', 'variantProgramID': EXPERIMENTAL_PROGRAM_ID,
        'controlPhaseSeconds': control_cycle, 'variantPhaseSeconds': variant_cycle,
    }
    outcome['publishedReproduction'] = comparison.pop('publishedReproduction')
    outcome['comparison'] = comparison
    outcome['resultsValid'] = comparison['available']
    if comparison['available']:
        outcome['replays'] = {
            'control': _try_replay(control_dir, directory, 'control', conditions),
            'variant': _try_replay(variant_dir, directory, 'variant', conditions),
        }
        outcome['control']['replay'] = outcome['replays']['control']
        outcome['variantRun']['replay'] = outcome['replays']['variant']
    return outcome


def _validate_request(variant, directory):
    if variant.get('programId') != '0':
        raise SignalVariantError('Solo se ejecuta el programa 0. No se elige otro programa de la red.')
    contract = variant.get('contract') or {}
    apply = contract.get('apply') or {}
    if (contract.get('contractVersion') != 1 or contract.get('action') != 'sumo-signal-variant'
            or apply.get('method') != 'additional-tlLogic' or apply.get('fileName') != 'signal-variant.tll.xml'
            or apply.get('loadedProgramID') != EXPERIMENTAL_PROGRAM_ID
            or apply.get('activation') != 'last-loaded-program'
            or apply.get('networkMustRemain') != 'identical'):
        raise SignalVariantError('El contrato de la variante no es el de sumo-signal-variant versión 1.')
    if variant.get('provenance') == 'inferred':
        raise SignalVariantError('Este controlador tiene un programa inferido. Esta etapa no lo ejecuta.')
    program = read_program(directory, variant['controllerId'])
    if not program['editable']:
        raise SignalVariantError(program['reason'] or 'El controlador no tiene una configuración verificable.')
    if program['program'] != variant['original']:
        raise SignalVariantError('El programa publicado ya no coincide con el que guardó la variante. No se ejecutó.')
    if program['program']['type'] != 'static':
        raise SignalVariantError('Esta ejecución admite el programa static verificado. Los controladores actuados quedan fuera.')
    if program['otherProgramIds']:
        raise SignalVariantError('El controlador tiene más de un programa. No está definido cuál quedaría activo.')
    if EXPERIMENTAL_PROGRAM_ID in program['otherProgramIds'] or EXPERIMENTAL_PROGRAM_ID == '0':
        raise SignalVariantError('El programID experimental ya existe en el controlador. No se ejecutó.')
    offset = program['program'].get('offset', '0')
    if not _same(offset, '0'):
        raise SignalVariantError('El desfase publicado no es 0. Esta etapa no ejecuta un programa desfasado.')
    proposed = validate_proposed(variant['original'], variant['proposed'])
    if proposed != variant['proposed']:
        raise SignalVariantError('Los tiempos guardados no pasaron la validación del programa. No se ejecutó.')
    differences = _differences(variant['original'], proposed)
    if not differences:
        raise SignalVariantError('La variante no tiene cambios respecto del programa publicado.')
    for row in differences:
        if row['field'] not in TIME_FIELDS and row['field'] != 'offset':
            raise SignalVariantError('La variante cambia un parámetro que no es un tiempo. No se ejecutó.')
    for phase in proposed['phases']:
        if not _aligned(phase['duration']):
            raise SignalVariantError('Una duración no coincide con el paso de 0,5 s. La activación quedaría ambigua.')
    if not _integrity_status(directory, variant.get('integrity') or {})['matches']:
        raise SignalVariantError('Los archivos de la corrida base cambiaron. No se ejecutó la variante.')
    _conditions(directory)
    _sumo_runtime()


def _conditions(directory):
    metadata_path = directory / 'metadata.json'
    if not metadata_path.is_file():
        raise SignalVariantError('La corrida publicada no tiene metadata.json. No se puede repetir sus condiciones.')
    try:
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        replay = json.loads((directory / 'replay.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise SignalVariantError('No se pudieron leer las condiciones de la corrida publicada.') from error
    seconds, seed = metadata.get('seconds'), metadata.get('seed')
    if replay.get('seconds') != seconds or replay.get('seed') != seed:
        raise SignalVariantError('El horizonte o la semilla no coinciden entre la metadata y el replay. No se ejecutó.')
    if type(seed) is not int or seed != SEED:
        raise SignalVariantError('La semilla publicada no es la semilla del pipeline de estudios. No se ejecutó.')
    if type(seconds) is not int or not 1 <= seconds <= MAX_SECONDS:
        raise SignalVariantError('Esta etapa solo ejecuta una corrida corta, de hasta 360 segundos.')
    routes = directory / 'routes.rou.xml'
    if not routes.is_file() or routes.stat().st_size > MAX_ROUTES_BYTES:
        raise SignalVariantError('La demanda publicada no está disponible dentro del límite de esta etapa.')
    if not (directory / 'network.net.xml').is_file():
        raise SignalVariantError('La corrida publicada no tiene network.net.xml.')
    return {'seconds': seconds, 'seed': seed}


def _sumo_runtime():
    try:
        sumo, _, env = sumo_tools()
        result = subprocess.run([sumo, '--version'], capture_output=True, text=True, env=env,
                                encoding='utf-8', errors='replace', timeout=30)
    except (OSError, subprocess.TimeoutExpired, StudyError) as error:
        raise SignalVariantError('SUMO 1.26 no está disponible para ejecutar la variante.') from error
    version = next((line.strip() for line in (result.stdout + result.stderr).splitlines() if line.strip()), '')
    if 'sumo 1.26.' not in version:
        raise SignalVariantError(f'La ejecución exige SUMO 1.26. La versión disponible es: {version or "desconocida"}.')
    return sumo, env, version


def _prepare_run(base, identifier):
    directory = _run_directory(identifier)
    if directory.exists():
        raise SignalVariantError('La carpeta de la corrida hija ya existe. No se reemplazó.')
    directory.mkdir(parents=True)
    for name in ('network.net.xml', 'routes.rou.xml', 'map.edg.xml', 'map.nod.xml'):
        source = base / name
        if name.startswith('map.') and not source.is_file():
            continue
        if not source.is_file():
            raise SignalVariantError(f'Falta {name} en la corrida publicada.')
        target = directory / name
        target.write_bytes(source.read_bytes())
        if _sha256(target) != _sha256(source):
            raise SignalVariantError(f'No se pudo copiar {name} sin alterarlo.')
    return directory


def _write_program(path, controller_id, program):
    additional = ET.Element('additional')
    attributes = {'id': controller_id, 'type': program['type'], 'programID': EXPERIMENTAL_PROGRAM_ID}
    if 'offset' in program:
        attributes['offset'] = program['offset']
    logic = ET.SubElement(additional, 'tlLogic', attributes)
    for phase in program['phases']:
        ET.SubElement(logic, 'phase', {key: str(value) for key, value in phase.items()})
    for param in program.get('params') or []:
        if not param.get('key'):
            raise SignalVariantError('El programa tiene un parámetro sin clave. No se ejecutó.')
        ET.SubElement(logic, 'param', key=str(param['key']), value='' if param.get('value') is None else str(param['value']))
    if logic.get('programID') == '0':
        raise SignalVariantError('El programa experimental no puede repetir el programID 0.')
    ET.indent(additional)
    ET.ElementTree(additional).write(path, encoding='utf-8', xml_declaration=True)


def _simulate(directory, sumo, env, shared, variant, program_file):
    network = ET.parse(directory / 'network.net.xml')
    signal_args = prepare_signal_recording(network, directory)
    if signal_args != ['--additional-files', 'signals.add.xml']:
        raise SignalVariantError('No se pudo preparar el registro de estados semafóricos.')
    additional = 'signals.add.xml' if program_file is None else f'signals.add.xml,{program_file}'
    command = [
        sumo, '--net-file', 'network.net.xml', '--route-files', 'routes.rou.xml', '--end', str(shared['seconds']),
        '--step-length', '0.5', '--seed', str(shared['seed']), '--time-to-teleport', '-1', '--no-step-log', 'true',
        '--fcd-output', 'trajectories.xml', '--fcd-output.geo', 'true', '--precision.geo', '7',
        '--device.fcd.period', str(shared['fcdPeriod']), '--summary-output', 'summary.xml',
        '--tripinfo-output', 'trips.xml', '--additional-files', additional,
    ]
    manifest = {
        'role': 'control' if program_file is None else 'variant',
        'variantId': variant['id'], 'baseRunId': variant['baseRunId'], 'controllerId': variant['controllerId'],
        'createdAt': _now(), 'command': command, 'conditions': shared,
        'networkSha256': _sha256(directory / 'network.net.xml'),
        'routesSha256': _sha256(directory / 'routes.rou.xml'),
        'additionalProgramSha256': None if program_file is None else _sha256(directory / program_file),
        'additionalFiles': additional,
    }
    write_json(directory / 'manifest.json', manifest)
    try:
        result = subprocess.run(command, cwd=directory, env=env, capture_output=True, encoding='utf-8',
                                errors='replace', timeout=SUMO_TIMEOUT)
    except subprocess.TimeoutExpired as error:
        (directory / 'sumo.log').write_text(f'{error}\n', encoding='utf-8')
        raise SignalVariantError(
            f'La corrida {manifest["role"]} superó {SUMO_TIMEOUT} segundos. No se publican métricas.') from error
    except OSError as error:
        raise SignalVariantError(f'No se pudo iniciar SUMO para la corrida {manifest["role"]}.') from error
    (directory / 'sumo.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    manifest['returnCode'] = result.returncode
    write_json(directory / 'manifest.json', manifest)
    if result.returncode:
        raise SignalVariantError(
            f'SUMO no terminó la corrida {manifest["role"]}. El detalle quedó en su sumo.log y no se publican métricas.')
    for name in ('summary.xml', 'trips.xml', 'signal-states.xml', 'trajectories.xml'):
        if not (directory / name).is_file():
            raise SignalVariantError(f'SUMO no escribió {name} en la corrida {manifest["role"]}.')
    if _sha256(directory / 'network.net.xml') != manifest['networkSha256'] or _sha256(directory / 'routes.rou.xml') != manifest['routesSha256']:
        raise SignalVariantError('SUMO alteró la copia de la red o de las rutas. No se publican métricas.')
    return manifest


def _assert_cycle(path, controller_id, phases, program_id, label):
    changes = _signal_changes(path, controller_id)
    if not changes:
        raise SignalVariantError(f'{label} no registró estados del controlador. No se publican métricas.')
    if abs(changes[0][3]) > 0.01:
        raise SignalVariantError(f'{label} no tiene el programa activo en el segundo 0. No se publican métricas.')
    measured = []
    for cursor, current in enumerate(changes):
        index = cursor % len(phases)
        program, phase_index, state, time = current
        phase = phases[index]
        if program != program_id or phase_index != str(index) or state != phase['state']:
            raise SignalVariantError(
                f'{label} no conservó el programa en el segundo {_num(time, 2)}. '
                f'Quedó activo el programa {program or "sin id"}. No se publican métricas.')
        if cursor + 1 == len(changes):
            continue
        duration = round(changes[cursor + 1][3] - time, 2)
        if abs(duration - float(phase['duration'])) > 0.01:
            raise SignalVariantError(
                f'{label} sostuvo la fase {index + 1} durante {_num(duration, 2)} s. '
                f'El programa pedido dura {phase["duration"]} s. No se publican métricas.')
        if cursor < len(phases):
            measured.append(duration)
    if len(measured) < len(phases):
        raise SignalVariantError(f'{label} no completó un ciclo del programa. No se publican métricas.')
    return measured


def _signal_changes(path, controller_id):
    changes = []
    previous = None
    for _, node in ET.iterparse(path, events=('end',)):
        if node.tag != 'tlsState' or node.get('id') != controller_id:
            continue
        current = (node.get('programID'), node.get('phase'), node.get('state'), float(node.get('time')))
        if previous is None or previous[:3] != current[:3]:
            changes.append(current)
            previous = current
    return changes


def _compatible(control, variant, base_hashes, program_hash):
    for key in ('seed', 'seconds', 'stepLength', 'timeToTeleport', 'fcdPeriod', 'sumoVersion'):
        if control['conditions'][key] != variant['conditions'][key]:
            return False, f'La condición {key} no coincide entre el control y la variante. La comparación no está disponible.'
    if control['networkSha256'] != variant['networkSha256'] or control['networkSha256'] != base_hashes.get('network.net.xml'):
        return False, 'La red de las corridas hijas no coincide con la publicada. La comparación no está disponible.'
    if control['routesSha256'] != variant['routesSha256'] or control['routesSha256'] != base_hashes.get('routes.rou.xml'):
        return False, 'Las rutas de las corridas hijas no coinciden con la demanda publicada. La comparación no está disponible.'
    if control.get('additionalProgramSha256') or control.get('additionalFiles') != 'signals.add.xml':
        return False, 'El control cargó un programa adicional. La comparación no está disponible.'
    if variant.get('additionalProgramSha256') != program_hash or variant.get('additionalFiles') != 'signals.add.xml,signal-variant.tll.xml':
        return False, 'El hash del programa experimental no coincide con el archivo ejecutado. La comparación no está disponible.'
    return True, None


def _comparison(base, control_dir, variant_dir, variant, conditions):
    horizon = conditions['seconds']
    demand_end = _demand_end(control_dir / 'routes.rou.xml')
    if _demand_end(variant_dir / 'routes.rou.xml') != demand_end:
        return _unavailable('El fin de la demanda no coincide entre el control y la variante.')
    control_trips = _measure_trips(control_dir / 'trips.xml', horizon)
    variant_trips = _measure_trips(variant_dir / 'trips.xml', horizon)
    control_summary = _summary_end(control_dir / 'summary.xml')
    variant_summary = _summary_end(variant_dir / 'summary.xml')
    control_incomplete = control_summary['inserted'] - control_trips['completed']
    variant_incomplete = variant_summary['inserted'] - variant_trips['completed']
    if control_incomplete < 0 or variant_incomplete < 0:
        return _unavailable('Hay más viajes completados que vehículos insertados. La comparación no está disponible.')
    indicators = {
        'completed': {'label': 'Vehículos completados', **_pair(control_trips['completed'], variant_trips['completed'], None)},
        'meanTravelSeconds': {'label': 'Tiempo medio de viaje', 'unit': 's',
                              **_pair(control_trips['meanTravelSeconds'], variant_trips['meanTravelSeconds'], 2)},
        'meanWaitSeconds': {'label': 'Tiempo de espera', 'unit': 's',
                            **_pair(control_trips['meanWaitSeconds'], variant_trips['meanWaitSeconds'], 2)},
    }
    clearance = {
        'control': _clearance(control_dir / 'summary.xml', demand_end),
        'variant': _clearance(variant_dir / 'summary.xml', demand_end),
    }
    warning = None
    if control_trips['completed'] != variant_trips['completed']:
        warning = (f"El viaje medio y la espera salen de {control_trips['completed']} vehículos en el control "
                   f"y de {variant_trips['completed']} en la variante.")
    reproduction = _published_reproduction(base / 'trips.xml', control_dir / 'trips.xml')
    return {
        'available': True, 'reason': None, 'horizonSeconds': horizon, 'demandEndSeconds': demand_end,
        'populationWarning': warning, 'indicators': indicators,
        'incomplete': {'control': control_incomplete, 'variant': variant_incomplete},
        'summaryArrived': {'control': control_summary['arrived'], 'variant': variant_summary['arrived']},
        'inserted': {'control': control_summary['inserted'], 'variant': variant_summary['inserted']},
        'clearanceSeconds': clearance, 'publishedReproduction': reproduction,
        'summary': _comparison_text(variant, indicators, warning, clearance, reproduction),
    }


def _measure_trips(path, horizon):
    durations, waits = [], []
    for trip in ET.parse(path).iter('tripinfo'):
        arrival = trip.get('arrival')
        if arrival is None:
            continue
        try:
            arrival_time = float(arrival)
            duration = float(trip.get('duration'))
            waiting = float(trip.get('waitingTime'))
        except (TypeError, ValueError) as error:
            raise SignalVariantError('Un viaje de SUMO no tiene duración o espera legible.') from error
        if not 0 <= arrival_time < horizon or trip.get('vaporized') not in (None, '', 'false', '0'):
            continue
        durations.append(duration)
        waits.append(waiting)
    completed = len(durations)
    return {
        'completed': completed,
        'meanTravelSeconds': None if not completed else round(sum(durations) / completed, 2),
        'meanWaitSeconds': None if not completed else round(sum(waits) / completed, 2),
    }


def _summary_end(path):
    steps = [step for step in ET.parse(path).getroot() if step.tag == 'step']
    if not steps:
        raise SignalVariantError('SUMO no escribió el resumen de la corrida.')
    last = steps[-1]
    try:
        return {'inserted': int(last.get('inserted')), 'arrived': int(last.get('arrived')),
                'running': int(last.get('running')), 'time': float(last.get('time'))}
    except (TypeError, ValueError) as error:
        raise SignalVariantError('El resumen de SUMO no tiene los conteos de vehículos.') from error


def _clearance(path, demand_end):
    for step in ET.parse(path).getroot():
        if step.tag != 'step':
            continue
        time = float(step.get('time'))
        if time + 1e-9 < demand_end:
            continue
        if (int(step.get('running')) == 0 and int(step.get('waiting')) == 0
                and int(step.get('inserted')) == int(step.get('arrived'))):
            return round(time - demand_end, 2)
    return None


def _demand_end(path):
    ends = []
    for flow in ET.parse(path).iter('flow'):
        if flow.get('end') is None:
            raise SignalVariantError('Una ruta no declara el fin de la demanda.')
        ends.append(float(flow.get('end')))
    if not ends:
        raise SignalVariantError('La demanda no tiene flujos.')
    return max(ends)


def _published_reproduction(published, control):
    left, right = _trip_rows(published), _trip_rows(control)
    if left == right:
        return {'matches': True, 'note': 'El control reprodujo los viajes de la corrida publicada.'}
    return {
        'matches': False,
        'note': ('El control usa los mismos insumos, pero sus viajes no coinciden con el replay publicado. '
                 'La comparación usa el control y la variante.'),
    }


def _trip_rows(path):
    return tuple(tuple(trip.get(key) for key in ('id', 'depart', 'arrival', 'duration', 'waitingTime', 'vaporized'))
                 for trip in ET.parse(path).iter('tripinfo'))


def _comparison_text(variant, indicators, warning, clearance, reproduction):
    changes = []
    for row in _differences(variant['original'], variant['proposed']):
        if 'phase' in row:
            changes.append(f"La fase {row['phase'] + 1} cambia {_field_name(row['field'])} de {row['original']} s a {row['proposed']} s")
        else:
            changes.append(f"el desfase cambia de {row['original']} s a {row['proposed']} s")
    completed, travel, wait = indicators['completed'], indicators['meanTravelSeconds'], indicators['meanWaitSeconds']
    sentences = [
        f"Misma red, mismas rutas y misma semilla. {'; '.join(changes)}.",
        f"Completaron {_num(completed['control'], 0)} vehículos en el control y {_num(completed['variant'], 0)} en la variante ({_delta(completed, 0)}).",
        f"El viaje medio pasa de {_num(travel['control'], 2)} s a {_num(travel['variant'], 2)} s ({_delta(travel, 2)}).",
        f"La espera media pasa de {_num(wait['control'], 2)} s a {_num(wait['variant'], 2)} s ({_delta(wait, 2)}).",
        'Cada indicador se lee por separado.',
    ]
    if warning:
        sentences.append(warning)
    if clearance['control'] is not None and clearance['variant'] is not None:
        sentences.append(
            f"El despeje después de la demanda es de {_num(clearance['control'], 2)} s en el control "
            f"y de {_num(clearance['variant'], 2)} s en la variante.")
    elif clearance['control'] is None and clearance['variant'] is None:
        sentences.append('La red no quedó despejada dentro del horizonte.')
    sentences.append(reproduction['note'])
    return ' '.join(sentences)


def _try_replay(child, base, role, conditions):
    try:
        metadata = json.loads((base / 'metadata.json').read_text(encoding='utf-8'))
        network = ET.parse(child / 'network.net.xml')
        motion = replay_geometry(network, child / 'map.nod.xml')
        catalog, _counts = saved_catalog(base, metadata)
        approaches = {movement['entry']: movement['from'] for movement in catalog}
        vehicles = []
        frames = fcd_frames(
            child / 'trajectories.xml', {'incoming': {key: key for key in approaches}}, geographic=True,
            vehicle_lengths=VEHICLE_LENGTHS if motion.get('projection') else None, vehicle_index=vehicles)
        summary = _summary_end(child / 'summary.xml')
        label = 'REPLAY EXPERIMENTAL · control' if role == 'control' else 'REPLAY EXPERIMENTAL · variante'
        replay = {
            **metadata, 'network': map_network(child, set(metadata.get('usedEdges') or [])), 'approaches': approaches,
            'frames': frames, 'laneMotion': motion, 'vehicleTypes': VEHICLE_TYPES, 'vehicleIndex': vehicles,
            'signalReplay': signal_replay(child, network), 'source': 'sumo-signal-variant', 'geographic': True,
            'experimental': True, 'experimentalRole': role, 'experimentalLabel': label,
            'arrived': summary['arrived'], 'inserted': summary['inserted'], 'seed': conditions['seed'],
            'seconds': conditions['seconds'],
        }
        write_json(child / 'replay.json', replay)
        return True
    except (OSError, ValueError, KeyError, StudyError, ET.ParseError):
        return False


def _blocked(variant, version, control_id, variant_id, program_hash, message, control_manifest=None, variant_manifest=None):
    outcome = _base_outcome(variant, version, control_id, variant_id, program_hash, control_manifest, variant_manifest)
    outcome['error'] = message
    outcome['programActive'] = False
    outcome['resultsValid'] = False
    outcome['comparison'] = {'available': False, 'reason': message}
    return outcome


def _base_outcome(variant, version, control_id, variant_id, program_hash, control_manifest, variant_manifest):
    def pointer(identifier, manifest):
        info = {'id': identifier, 'directory': _relative(_run_directory(identifier)), 'replay': False}
        if manifest:
            info['networkSha256'] = manifest.get('networkSha256')
            info['routesSha256'] = manifest.get('routesSha256')
        return info

    variant_info = pointer(variant_id, variant_manifest)
    variant_info['programSha256'] = program_hash
    variant_info['programFile'] = 'signal-variant.tll.xml'
    return {
        'startedAt': variant.get('execution', {}).get('startedAt'), 'finishedAt': _now(),
        'sumoVersion': version, 'loadedProgramID': EXPERIMENTAL_PROGRAM_ID, 'activation': 'last-loaded-program',
        'resultsValid': False, 'programActive': False, 'error': None,
        'control': pointer(control_id, control_manifest), 'variantRun': variant_info,
        'differences': _differences(variant['original'], variant['proposed']),
        'replays': {'control': False, 'variant': False},
    }


def _unavailable(reason):
    return {'available': False, 'reason': reason, 'publishedReproduction': {'matches': False, 'note': reason}}


def _pair(control, variant, digits):
    if control is None or variant is None:
        return {'control': control, 'variant': variant, 'absolute': None, 'percent': None}
    absolute = variant - control if digits is None else round(variant - control, digits)
    percent = None if control == 0 else round((variant - control) / control * 100, 1)
    return {'control': control, 'variant': variant, 'absolute': absolute, 'percent': percent}


def _assert_base_unchanged(directory, before):
    if not _integrity_status(directory, before)['matches']:
        raise SignalVariantError('Los archivos publicados cambiaron durante la ejecución. No se publican métricas.')


def _run_directory(identifier):
    if not isinstance(identifier, str) or len(identifier) != 32 or any(character not in '0123456789abcdef' for character in identifier):
        raise SignalVariantError('La corrida experimental no está disponible.')
    path = (RUNS / identifier).resolve()
    try:
        path.relative_to(RUNS.resolve())
    except ValueError as error:
        raise SignalVariantError('La corrida experimental no está disponible.') from error
    return path


def _new_run_id():
    RUNS.mkdir(parents=True, exist_ok=True)
    for _ in range(5):
        identifier = uuid4().hex
        if not (RUNS / identifier).exists():
            return identifier
    raise SignalVariantError('No se pudo reservar una carpeta para la corrida hija.')


def _variant_path_for(identifier):
    from sumo_scenario.signal_variant import _variant_path
    return _variant_path(identifier)


def _write_unexpected(identifier):
    RUNS.mkdir(parents=True, exist_ok=True)
    with (RUNS / '_execution-error.log').open('a', encoding='utf-8') as handle:
        handle.write(f'{identifier}\n{traceback.format_exc()}\n')


def _aligned(value):
    number = float(value)
    return math.isfinite(number) and abs(number * 2 - round(number * 2)) < 1e-6


def _same(left, right):
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return False


def _field_name(field):
    return {'duration': 'la duración', 'minDur': 'el mínimo', 'maxDur': 'el máximo', 'offset': 'el desfase'}.get(field, field)


def _num(value, digits):
    if value is None:
        return '—'
    if digits == 0:
        return str(int(value))
    return f'{value:.{digits}f}'.replace('.', ',')


def _delta(item, digits):
    if item['absolute'] is None:
        return 'sin diferencia calculable'
    text = _num(item['absolute'], digits)
    if item['absolute'] > 0:
        text = f'+{text}'
    if item['percent'] is None:
        return text
    percent = _num(item['percent'], 1)
    if item['percent'] > 0:
        percent = f'+{percent}'
    return f'{text} · {percent} %'
