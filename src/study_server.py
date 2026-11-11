"""Serve the UrbanFlow web and run one local SUMO study at a time."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler
import json
import math
from pathlib import Path
import re
from threading import Lock
import traceback
from urllib.parse import urlsplit
from uuid import uuid4

from sumo_scenario.study import StudyError, generate_study, rerun_study, saved_traffic, write_json
from sumo_scenario.regional_map import coverage


WORKSPACE = Path(__file__).resolve().parents[1]
STUDIES = WORKSPACE / 'results' / 'studies'
STUDY_ID = r'[a-f0-9]{32}'
STUDY_ROUTE = re.compile(rf'/api/studies/({STUDY_ID})(/replay)?')
RUN_ROUTE = re.compile(rf'/api/studies/({STUDY_ID})/runs')
WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix='urbanflow-study')
STATUS_LOCK = Lock()
ACTIVE_RUNS = set()


def run_job(directory, build):
    def update(stage, message, target=None):
        with STATUS_LOCK:
            write_json(directory / 'status.json', {'stage': stage, 'message': message, 'target': target})

    try:
        data = build(update)
        update('ready', 'Estudio listo.', {key: data[key] for key in ('bounds', 'location', 'title')})
    except StudyError as error:
        update('error', str(error))
    except Exception:
        with (directory / 'sumo.log').open('a', encoding='utf-8') as log:
            log.write(traceback.format_exc())
        update('error', 'Ocurrió un error al preparar el estudio. Los detalles quedaron en sumo.log.')


def run_study(directory, lon, lat):
    run_job(directory, partial(generate_study, directory, lon, lat, cache=directory.parent / 'osm-cache'))


def read_json(file):
    data = json.loads(file.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'{file.name} debe contener un objeto JSON.')
    return data


def run_info(directory, fallback_file):
    try:
        return read_json(directory / 'run-info.json')
    except FileNotFoundError:
        return {
            'parentId': None,
            'createdAt': datetime.fromtimestamp(fallback_file.stat().st_mtime, timezone.utc).isoformat(),
        }


def list_studies():
    if not STUDIES.is_dir():
        return []
    entries = []
    for directory in STUDIES.iterdir():
        if not re.fullmatch(STUDY_ID, directory.name) or not (directory / 'replay.json').is_file():
            continue
        file = directory / 'metadata.json'
        if not file.is_file():
            file = directory / 'replay.json'
        try:
            data = read_json(file)
            info = run_info(directory, file)
            traffic = data.get('traffic') or {
                'source': 'sample',
                'durationMinutes': max(1, math.ceil(data.get('seconds', 240) / 60)),
            }
            entries.append({
                'id': directory.name, 'title': data['title'], 'location': data.get('location'),
                'traffic': {key: traffic[key] for key in ('source', 'durationMinutes')},
                'parentId': info.get('parentId'), 'createdAt': info['createdAt'],
                'trips': data.get('trips'), 'inserted': data.get('inserted'), 'arrived': data.get('arrived'),
            })
        except (OSError, ValueError, KeyError, TypeError, OverflowError):
            # A missing or damaged run should not hide the other saved studies.
            continue
    return sorted(entries, key=lambda entry: (entry['createdAt'], entry['id']), reverse=True)


class StudyHandler(SimpleHTTPRequestHandler):
    def respond(self, status, data):
        payload = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            return self.respond(200, {'app': 'urbanflow', 'apiVersion': 3, 'workspace': str(WORKSPACE)})
        if path == '/api/region':
            return self.respond(200, coverage())
        if path == '/api/studies':
            return self.respond(200, {'studies': list_studies()})
        if not path.startswith('/api/'):
            return super().do_GET()
        match = STUDY_ROUTE.fullmatch(path)
        if not match:
            return self.respond(404, {'message': 'Estudio no encontrado.'})
        directory = STUDIES / match[1]
        file = directory / ('replay.json' if match[2] else 'status.json')
        try:
            if match[2]:
                payload = read_json(file)
                payload.update(run_info(directory, file))
                if not payload.get('traffic'):
                    try:
                        payload['traffic'] = saved_traffic(directory, payload)
                    except StudyError as error:
                        payload['trafficMessage'] = str(error)
            else:
                with STATUS_LOCK:
                    payload = read_json(file)
                    if payload.get('stage') not in ('ready', 'error') and match[1] not in ACTIVE_RUNS:
                        payload.update(stage='error', message='El servidor se cerró antes de terminar esta corrida. Iniciá una nueva.')
            return self.respond(200, payload)
        except FileNotFoundError:
            return self.respond(404, {'message': 'El estudio todavía no está disponible.'})
        except (OSError, ValueError):
            return self.respond(500, {'message': 'No se pudo leer el estudio guardado.'})

    def read_payload(self, max_length):
        length = int(self.headers.get('Content-Length', 0))
        if not 0 < length <= max_length:
            raise ValueError
        return json.loads(self.rfile.read(length))

    def start_study(self):
        try:
            point = self.read_payload(1024)
            lon, lat = float(point['lng']), float(point['lat'])
            if not math.isfinite(lon) or not math.isfinite(lat) or abs(lon) > 180 or abs(lat) > 85:
                raise ValueError
        except (ValueError, KeyError, TypeError, OverflowError):
            return self.respond(400, {'message': 'El punto seleccionado no es válido.'})
        return self.queue_study(partial(run_study, lon=lon, lat=lat))

    def start_rerun(self, base_id):
        base_directory = STUDIES / base_id
        if not (base_directory / 'replay.json').is_file():
            return self.respond(404, {'message': 'El escenario de origen no está disponible.'})
        try:
            traffic = self.read_payload(128 * 1024)
            duration, source, counts = traffic['durationMinutes'], traffic['source'], traffic['counts']
            if (type(duration) is not int or not 1 <= duration <= 60
                    or source not in ('sample', 'observed') or not isinstance(counts, dict)
                    or not counts or not all(type(count) is int and count >= 0 for count in counts.values())
                    or not any(counts.values())):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self.respond(400, {'message': 'Ingresá un período de 1 a 60 minutos y conteos enteros, con al menos un vehículo.'})

        def run(directory):
            run_job(directory, partial(rerun_study, directory, base_directory, traffic))

        return self.queue_study(run, parent_id=base_id)

    def queue_study(self, build, parent_id=None):
        identifier = uuid4().hex
        directory = STUDIES / identifier
        try:
            directory.mkdir(parents=True)
            write_json(directory / 'run-info.json', {
                'parentId': parent_id, 'createdAt': datetime.now(timezone.utc).isoformat(),
            })
            with STATUS_LOCK:
                write_json(directory / 'status.json', {'stage': 'queued', 'message': 'Preparando el estudio…', 'target': None})
                ACTIVE_RUNS.add(identifier)
        except OSError:
            return self.respond(500, {'message': 'No se pudo guardar el estudio. Revisá que la carpeta del proyecto permita escritura.'})

        def execute():
            try:
                build(directory)
            finally:
                with STATUS_LOCK:
                    ACTIVE_RUNS.discard(identifier)

        try:
            WORKER.submit(execute)
        except RuntimeError:
            with STATUS_LOCK:
                ACTIVE_RUNS.discard(identifier)
            return self.respond(503, {'message': 'UrbanFlow se está cerrando. Volvé a abrirlo para iniciar el estudio.'})
        return self.respond(202, {'id': identifier})

    def do_POST(self):
        path = urlsplit(self.path).path
        run = RUN_ROUTE.fullmatch(path)
        if path != '/api/studies' and not run:
            return self.respond(404, {'message': 'Acción no disponible.'})
        if self.headers.get_content_type() != 'application/json':
            return self.respond(415, {'message': 'Los datos deben enviarse como JSON.'})
        return self.start_rerun(run[1]) if run else self.start_study()
