"""Start UrbanFlow on a loopback port and open the map in the default browser."""

import errno
import json
import os
import secrets
import socket
import sys
import traceback
import webbrowser
from datetime import datetime
from functools import partial
from http.client import HTTPConnection, HTTPException
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from src.study_server import API_VERSION, WORKER, StudyHandler


PROJECT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PREFERRED_PORTS = (8000, 8765)
LOG = PROJECT / "results" / "_tmp" / "inicio" / "urbanflow.log"
LOG_LIMIT = 48_000
REQUIRED = (
    ("la aplicación", PROJECT / "urbanflow-web" / "index.html"),
    ("el servidor", PROJECT / "src" / "study_server.py"),
)


class LocalServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR can let two different servers answer the same port.
    allow_reuse_address = False
    allow_reuse_port = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def log(message):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG.open("a", encoding="utf-8") as stream:
            stream.write(f"{stamp} {message}\n")
        if LOG.stat().st_size > LOG_LIMIT:
            LOG.write_text(LOG.read_text(encoding="utf-8", errors="replace")[-32_000:], encoding="utf-8")
    except OSError:
        pass


def console(message):
    if sys.stdout is None:
        return
    try:
        print(message, flush=True)
    except OSError:
        pass


def notify(message, *, error=False):
    log(message)
    console(message)
    if error and os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "UrbanFlow", 0x00000010)
        except Exception:
            pass


def missing_files():
    return [label for label, path in REQUIRED if not path.is_file()]


def requirement_message(missing=None):
    names = missing_files() if missing is None else missing
    return "Faltan archivos necesarios para iniciar UrbanFlow: " + ", ".join(names) + "."


def is_urbanflow(port):
    connection = HTTPConnection(HOST, port, timeout=0.6)
    try:
        connection.request("GET", "/api/health", headers={"Accept": "application/json"})
        response = connection.getresponse()
        if response.status != 200 or response.headers.get_content_type() != "application/json":
            return False
        health = json.loads(response.read(4096))
        if not isinstance(health, dict) or health.get("app") != "urbanflow" or health.get("apiVersion") != API_VERSION:
            return False
        workspace = health.get("workspace")
        return isinstance(workspace, str) and Path(workspace) == PROJECT
    except (OSError, HTTPException, ValueError):
        return False
    finally:
        connection.close()


def select_server(*, reuse):
    handler = partial(StudyHandler, directory=str(PROJECT / "urbanflow-web"))
    for port in PREFERRED_PORTS:
        try:
            return LocalServer((HOST, port), handler), port
        except OSError as error:
            unavailable = error.errno in {errno.EADDRINUSE, errno.EACCES}
            unavailable_on_windows = getattr(error, "winerror", None) in {10048, 10013}
            if not unavailable and not unavailable_on_windows:
                raise
            if reuse and is_urbanflow(port):
                return None, port
    server = LocalServer((HOST, 0), handler)
    return server, server.server_port


def create_server():
    server, _ = select_server(reuse=False)
    return server


def open_map(port):
    url = f"http://{HOST}:{port}/#mapa"
    try:
        opened = webbrowser.open(url, new=2)
    except Exception as error:
        log(f"No se pudo abrir el navegador: {error}")
        opened = False
    if not opened:
        notify(
            f"UrbanFlow está en {url}, pero no se pudo abrir el navegador predeterminado.",
            error=True,
        )
    return url


def serve():
    missing = missing_files()
    if missing:
        raise RuntimeError(requirement_message(missing))
    server, port = select_server(reuse=True)
    if server is None:
        log(f"Instancia existente en el puerto {port}.")
        console(f"UrbanFlow ya está abierto en http://{HOST}:{port}/")
        open_map(port)
        return 0
    server.control_token = secrets.token_urlsafe(18)
    if port != PREFERRED_PORTS[0]:
        log(f"El puerto {PREFERRED_PORTS[0]} está ocupado. UrbanFlow usa el puerto {port}.")
    log(f"Servidor listo en el puerto {port}.")
    console(f"UrbanFlow: http://{HOST}:{port}/")
    with server:
        Thread(target=open_map, args=(port,), daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            log("Cierre desde la consola.")
    log("Servidor detenido.")
    WORKER.shutdown(wait=False, cancel_futures=True)
    return 0


def main():
    try:
        return serve()
    except Exception as error:
        log(traceback.format_exc())
        message = str(error).strip() or "UrbanFlow no pudo iniciarse."
        if not message.startswith("Faltan archivos"):
            message = "UrbanFlow no pudo iniciarse. El detalle quedó en el registro de inicio."
        notify(message, error=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
