"""Cierre local de UrbanFlow y mensajes de inicio, sin ocupar los puertos habituales."""

from functools import partial
from http.client import HTTPConnection
import json
from pathlib import Path
import socket
import threading
import time
import unittest

import abrir_urbanflow
from src.study_server import StudyHandler


PROJECT = Path(__file__).resolve().parents[1]


class InicioTests(unittest.TestCase):
    def test_missing_files_message_names_what_is_absent(self):
        message = abrir_urbanflow.requirement_message(["la aplicación", "el servidor"])
        self.assertIn("Faltan archivos necesarios", message)
        self.assertIn("la aplicación", message)
        self.assertIn("el servidor", message)

    def test_shutdown_requires_the_local_token_and_frees_the_port(self):
        handler = partial(StudyHandler, directory=str(PROJECT / "urbanflow-web"))
        server = abrir_urbanflow.LocalServer(("127.0.0.1", 0), handler)
        server.control_token = "token-de-prueba"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port
        try:
            self.assertTrue(abrir_urbanflow.is_urbanflow(port))
            health = self.request(port, "GET", "/api/health")
            self.assertEqual(health["status"], 200)
            self.assertEqual(health["body"]["controlToken"], "token-de-prueba")
            denied = self.request(port, "POST", "/api/shutdown", token="otro")
            self.assertEqual(denied["status"], 403)
            closed = self.request(port, "POST", "/api/shutdown", token="token-de-prueba")
            self.assertEqual(closed["status"], 200)
            self.assertEqual(closed["body"].get("closed"), True)
            self.wait_until_closed(port)
        finally:
            server.shutdown()
            server.server_close()

    def request(self, port, method, path, token=None):
        headers = {}
        if token is not None:
            headers["X-UrbanFlow-Token"] = token
        connection = HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            connection.request(method, path, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            body = json.loads(raw) if raw else {}
            return {"status": response.status, "body": body}
        finally:
            connection.close()

    def wait_until_closed(self, port):
        for _ in range(40):
            try:
                probe = socket.create_connection(("127.0.0.1", port), timeout=0.2)
            except OSError:
                return
            probe.close()
            time.sleep(0.1)
        self.fail("el puerto de prueba sigue ocupado")


if __name__ == "__main__":
    unittest.main()
