"""Start UrbanFlow on a loopback port and open its address in the browser."""

import errno
import json
import socket
import webbrowser
from functools import partial
from http.client import HTTPConnection, HTTPException
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from src.study_server import API_VERSION, StudyHandler


PROJECT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PREFERRED_PORTS = (8000, 8765)


class LocalServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR can let two different servers answer the same port.
    allow_reuse_address = False
    allow_reuse_port = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


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


def main():
    server, port = select_server(reuse=True)
    url = f"http://{HOST}:{port}/"
    if server is None:
        print(f"UrbanFlow ya está abierto en {url}", flush=True)
        webbrowser.open(url, new=2)
        return

    with server:
        if port != PREFERRED_PORTS[0]:
            print("El puerto 8000 está ocupado. Usá la dirección de UrbanFlow que aparece abajo.", flush=True)
        print(f"UrbanFlow: {url}\nDejá esta ventana abierta mientras uses la web.", flush=True)
        Thread(target=webbrowser.open, args=(url,), kwargs={"new": 2}, daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
