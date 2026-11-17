"""Abrir el Sector 01 certificado en la vista 3D, sin configuración manual."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from tools.open_replay_qa import create_server

CANDIDATE = ROOT / "results" / "etapa1c5-sector01" / "candidata"
QA = ROOT / "results" / "etapa1c5-sector01" / "qa"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def main():
    manifest_path = CANDIDATE / "manifest.json"
    geojson = CANDIDATE / "sector01.geojson"
    events = QA / "qa-events.json"
    if not manifest_path.is_file():
        fail("No se puede iniciar: falta la candidata certificada de 1C.5.")
    try:
        manifest = json.loads(manifest_path.read_bytes())
        run_id = manifest["replayId"]
    except (OSError, ValueError, KeyError):
        fail("No se puede iniciar: el manifiesto de la candidata no se puede leer.")
    replay = CANDIDATE / run_id
    required = {
        "el replay": replay / "replay.json",
        "el recorte para la vista 3D": replay / "recorte.osm.xml",
        "el mapa": geojson,
        "las alertas": events,
    }
    missing = [label for label, path in required.items() if not path.is_file()]
    if missing:
        fail("No se puede iniciar: falta " + ", ".join(missing) + ".")
    if not CHROME.is_file():
        fail("No se puede iniciar: no está Chrome en Program Files.")
    try:
        server = create_server(CANDIDATE, run_id, QA, geojson)
    except ValueError as error:
        fail(f"No se puede iniciar: {error}")
    except OSError as error:
        fail(f"No se pudo abrir el servidor local. {error}")
    url = f"http://127.0.0.1:{server.server_port}/?probar=1#estudio/{run_id}"
    try:
        subprocess.Popen([str(CHROME), "--new-window", url])
    except OSError as error:
        server.server_close()
        fail(f"No se pudo abrir Chrome. El servidor se cerró. {error}")
    print(f"Sector 01 en 3D: {url}", flush=True)
    print("Dejá esta ventana abierta. Ctrl+C cierra el servidor.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor cerrado.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
