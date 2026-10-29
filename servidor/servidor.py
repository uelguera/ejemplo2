"""Servidor del consultorio: HTTP mínimo con la librería estándar de Python.

Sirve las páginas web y pasa cada petición a los módulos hasta que uno la atienda:
    caja.py       -> /movimientos, /resumen, /cierre(s), /gastos-fijos   (ver su docstring)
    productos.py  -> /productos                                          (ver su docstring)

Páginas: / y /caja (caja), /inventario (productos). Archivos comunes de la web: /comun.css y /comun.js.
Las páginas no usan las mismas rutas que la API: /productos devuelve los datos, /inventario la página.

Para agregar un módulo: créalo con una clase que tenga atender(peticion) -> (estado, cuerpo) | None
(ver comun.Peticion) y agrégalo a la lista "modulos" de crear_manejador().

Variables de entorno opcionales:
    CAJA_PUERTO           -> puerto (por defecto 8001; 0 = uno libre cualquiera)
    CAJA_ARCHIVO          -> archivo JSON de movimientos (por defecto servidor/movimientos.json)
    CIERRES_ARCHIVO       -> archivo JSON de cierres (por defecto servidor/cierres.json)
    GASTOS_FIJOS_ARCHIVO  -> archivo JSON de gastos fijos (por defecto servidor/gastos_fijos.json)
    PRODUCTOS_ARCHIVO     -> archivo JSON de productos (por defecto servidor/productos.json)
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from caja import Caja, Cierres, GastosFijos, ModuloCaja
from comun import Peticion, ruta_no_encontrada
from productos import ModuloProductos, Productos

CARPETA = Path(__file__).parent
CARPETA_WEB = CARPETA / "web"
# Ruta -> (archivo en web/, tipo de contenido)
ARCHIVOS_WEB = {
    "/": ("caja.html", "text/html; charset=utf-8"),
    "/caja": ("caja.html", "text/html; charset=utf-8"),
    "/inventario": ("productos.html", "text/html; charset=utf-8"),  # /productos es la API de productos
    "/comun.css": ("comun.css", "text/css; charset=utf-8"),
    "/comun.js": ("comun.js", "text/javascript; charset=utf-8"),
}


def crear_manejador(caja: Caja, cierres: Cierres, gastos_fijos: GastosFijos, productos: Productos):
    """Devuelve una clase de manejador HTTP que usa los almacenes de datos dados."""
    modulo_caja = ModuloCaja(caja, cierres, gastos_fijos)
    modulos = [modulo_caja, ModuloProductos(productos, modulo_caja)]

    class Manejador(BaseHTTPRequestHandler):
        def _enviar(self, estado: int, datos: bytes, tipo: str) -> None:
            self.send_response(estado)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def _responder(self, estado: int, cuerpo=None) -> None:
            datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8") if cuerpo is not None else b""
            self._enviar(estado, datos, "application/json; charset=utf-8")

        def _leer_cuerpo(self) -> dict | None:
            """Devuelve el cuerpo JSON como diccionario ({} si viene vacío) o None si no es válido."""
            largo = int(self.headers.get("Content-Length", 0))
            try:
                cuerpo = json.loads(self.rfile.read(largo) or b"{}")
            except json.JSONDecodeError:
                return None
            return cuerpo if isinstance(cuerpo, dict) else None

        def _atender(self) -> None:
            url = urlsplit(self.path)
            if self.command == "GET" and url.path in ARCHIVOS_WEB:
                archivo, tipo = ARCHIVOS_WEB[url.path]
                return self._enviar(200, (CARPETA_WEB / archivo).read_bytes(), tipo)
            peticion = Peticion(self.command, url.path, parse_qs(url.query), self._leer_cuerpo)
            for modulo in modulos:
                respuesta = modulo.atender(peticion)
                if respuesta is not None:
                    return self._responder(*respuesta)
            self._responder(*ruta_no_encontrada())

        do_GET = do_POST = do_PATCH = do_DELETE = _atender

        def log_message(self, formato, *args):
            print(f"[servidor] {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    return Manejador


def main() -> None:
    def archivo(variable: str, nombre: str) -> Path:
        return Path(os.environ.get(variable, CARPETA / nombre))

    manejador = crear_manejador(
        Caja(archivo("CAJA_ARCHIVO", "movimientos.json")),
        Cierres(archivo("CIERRES_ARCHIVO", "cierres.json")),
        GastosFijos(archivo("GASTOS_FIJOS_ARCHIVO", "gastos_fijos.json")),
        Productos(archivo("PRODUCTOS_ARCHIVO", "productos.json")),
    )
    servidor = ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("CAJA_PUERTO", 8001))), manejador)
    puerto = servidor.server_address[1]  # el real, por si el puerto era 0
    print(f"Consultorio escuchando en http://127.0.0.1:{puerto}  (Ctrl+C para detener)", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    main()
