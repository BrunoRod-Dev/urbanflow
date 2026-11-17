"""Open a recorded study in the existing player with a local QA overlay."""

import argparse
from functools import partial
import json
from pathlib import Path
import sys
from threading import Thread
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from abrir_urbanflow import LocalServer
from src import study_server


def create_server(studies, run_id, qa_directory, geojson):
    events = json.loads((qa_directory / 'qa-events.json').read_bytes())
    if events['studyId'] != run_id or not (studies / run_id / 'replay.json').is_file():
        raise ValueError('Las alertas deben corresponder a la corrida que se va a abrir.')
    overlay = json.loads(geojson.read_bytes())
    events['connections'] = {'type': 'FeatureCollection', 'features': [
        feature for feature in overlay['features'] if feature['properties']['kind'] == 'connection'
    ]}
    events.pop('geometryInvestigation', None)

    class QaHandler(study_server.StudyHandler):
        def do_GET(self):
            if self.path == '/qa-sector.json':
                self.respond(200, events)
            else:
                super().do_GET()

    study_server.STUDIES = studies
    study_server.PROJECTS = qa_directory / 'projects'
    return LocalServer(('127.0.0.1', 0), partial(QaHandler, directory=str(ROOT / 'urbanflow-web')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study_manifest', type=Path)
    parser.add_argument('qa_directory', type=Path)
    parser.add_argument('geojson', type=Path)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(args.study_manifest.read_bytes())
    run_id = manifest['replayId']
    with create_server(args.study_manifest.parent, run_id, args.qa_directory, args.geojson) as server:
        url = f'http://127.0.0.1:{server.server_port}/?qa=1#estudio/{run_id}'
        print(url, flush=True)
        if not args.no_browser:
            Thread(target=webbrowser.open, args=(url,), daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
