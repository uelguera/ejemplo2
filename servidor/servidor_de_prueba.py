"""Base para las pruebas: levanta el servidor en un puerto libre con archivos temporales.
No empieza con "test", así que unittest no lo ejecuta como prueba."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from caja import Caja, Cierres, GastosFijos
from productos import Productos
from servidor import crear_manejador


class ServidorDePrueba(unittest.TestCase):
    """Base sin pruebas propias: levanta el servidor con archivos temporales y ofrece pedir()."""

    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        carpeta = Path(self.carpeta.name)
        manejador = crear_manejador(Caja(carpeta / "movimientos.json"), Cierres(carpeta / "cierres.json"),
                                    GastosFijos(carpeta / "gastos_fijos.json"), Productos(carpeta / "productos.json"))
        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), manejador)
        self.base = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.carpeta.cleanup()

    def pedir(self, metodo, ruta, cuerpo=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        peticion = urllib.request.Request(self.base + ruta, data=datos, method=metodo)
        peticion.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(peticion) as r:
                texto = r.read()
                return r.status, json.loads(texto) if texto else None
        except urllib.error.HTTPError as e:
            with e:  # cierra la respuesta de error para evitar ResourceWarning
                return e.code, json.loads(e.read())

    def pagina(self, ruta):
        """Devuelve (estado, tipo de contenido, texto) de una página o archivo de la web."""
        with urllib.request.urlopen(self.base + ruta) as respuesta:
            return respuesta.status, respuesta.headers["Content-Type"], respuesta.read().decode("utf-8")

    def registrar(self, **cambios):
        movimiento = {"tipo": "ingreso", "monto": 150, "categoria": "consulta",
                      "medio": "yape", "fecha": "2026-10-05", **cambios}
        return self.pedir("POST", "/movimientos", movimiento)
