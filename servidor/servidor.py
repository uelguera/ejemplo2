"""API de la caja del consultorio (ingresos y gastos en soles): servidor HTTP mínimo con la librería estándar.

Endpoints:
    GET    /                  -> página web de la caja
    GET    /movimientos       -> movimientos de un mes, por fecha (?mes=AAAA-MM; por defecto el actual;
                                 ?mes=todos devuelve todos, para las copias de seguridad)
    POST   /movimientos       -> registra un movimiento (cuerpo: {"tipo": "ingreso"|"gasto",
                                 "monto": 150, "categoria": "...", "medio": "efectivo"|"yape",
                                 "fecha": "AAAA-MM-DD" (opcional, hoy), "descripcion": "..." (opcional)})
    DELETE /movimientos/<id>  -> elimina un movimiento
    GET    /resumen           -> totales de un mes (?mes=AAAA-MM; por defecto el actual)

Variables de entorno opcionales:
    CAJA_PUERTO   -> puerto (por defecto 8001; 0 = uno libre cualquiera)
    CAJA_ARCHIVO  -> archivo JSON de movimientos (por defecto servidor/movimientos.json)
"""

import json
import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PUERTO = int(os.environ.get("CAJA_PUERTO", 8001))
ARCHIVO_DATOS = Path(os.environ.get("CAJA_ARCHIVO", Path(__file__).parent / "movimientos.json"))
PAGINA_WEB = Path(__file__).parent / "web" / "index.html"

# Cambia estas listas para usar otras categorías o medios de pago
# (las categorías están repetidas en web/index.html: cambia ambas).
CATEGORIAS = {
    "ingreso": ("consulta", "procedimiento", "certificado", "otro"),
    "gasto": ("alquiler", "insumos", "servicios", "sueldos", "otro"),
}
MEDIOS = ("efectivo", "yape")
MONTO_MAXIMO = Decimal("1000000")


def validar_fecha(texto: str, patron: str, relleno: str) -> bool:
    """Comprueba el formato exacto y que la fecha exista (relleno completa un mes hasta un día)."""
    if not re.fullmatch(patron, texto):
        return False
    try:
        date.fromisoformat(texto + relleno)
    except ValueError:
        return False
    return True


def validar_movimiento(cuerpo: dict) -> dict:
    """Devuelve el movimiento limpio (sin id) o lanza ValueError con un mensaje para el usuario."""
    tipo = str(cuerpo.get("tipo", "")).strip().lower()
    if tipo not in CATEGORIAS:
        raise ValueError("El campo 'tipo' debe ser 'ingreso' o 'gasto'")

    valor = cuerpo.get("monto")
    try:
        if isinstance(valor, bool) or valor is None:
            raise InvalidOperation
        monto = Decimal(str(valor).strip())
    except InvalidOperation:
        raise ValueError("El campo 'monto' debe ser un número, por ejemplo 150 o 35.50") from None
    if not monto.is_finite() or monto <= 0 or monto > MONTO_MAXIMO:
        raise ValueError(f"El campo 'monto' debe ser mayor que 0 y como máximo {MONTO_MAXIMO}")
    if monto.as_tuple().exponent < -2:
        raise ValueError("El campo 'monto' admite como máximo 2 decimales")

    categoria = str(cuerpo.get("categoria", "")).strip().lower()
    if categoria not in CATEGORIAS[tipo]:
        raise ValueError(f"La categoría de un {tipo} debe ser una de: {', '.join(CATEGORIAS[tipo])}")

    medio = str(cuerpo.get("medio", "")).strip().lower()
    if medio not in MEDIOS:
        raise ValueError(f"El campo 'medio' debe ser uno de: {', '.join(MEDIOS)}")

    fecha = cuerpo.get("fecha") or date.today().isoformat()
    if not validar_fecha(str(fecha), r"\d{4}-\d{2}-\d{2}", ""):
        raise ValueError("El campo 'fecha' debe tener el formato AAAA-MM-DD, por ejemplo 2026-10-29")

    return {
        "tipo": tipo,
        "monto": float(monto),
        "fecha": str(fecha),
        "categoria": categoria,
        "medio": medio,
        "descripcion": str(cuerpo.get("descripcion") or "").strip(),
    }


class Caja:
    """Guarda los ingresos y gastos del consultorio en un archivo JSON."""

    def __init__(self, ruta: Path):
        self.ruta = ruta

    def leer(self) -> list[dict]:
        if not self.ruta.exists():
            return []
        return json.loads(self.ruta.read_text(encoding="utf-8"))

    def escribir(self, movimientos: list[dict]) -> None:
        self.ruta.write_text(json.dumps(movimientos, indent=2, ensure_ascii=False), encoding="utf-8")

    def registrar(self, datos: dict) -> dict:
        movimientos = self.leer()
        nuevo_id = max((m["id"] for m in movimientos), default=0) + 1
        movimiento = {"id": nuevo_id, **datos}
        movimientos.append(movimiento)
        self.escribir(movimientos)
        return movimiento

    def eliminar(self, id_movimiento: int) -> bool:
        movimientos = self.leer()
        restantes = [m for m in movimientos if m["id"] != id_movimiento]
        if len(restantes) == len(movimientos):
            return False
        self.escribir(restantes)
        return True

    def del_mes(self, mes: str | None) -> list[dict]:
        """Movimientos del mes 'AAAA-MM' (o todos si mes es None), por fecha y luego por orden de registro."""
        del_mes = [m for m in self.leer() if mes is None or m["fecha"].startswith(mes + "-")]
        return sorted(del_mes, key=lambda m: (m["fecha"], m["id"]))

    def resumen(self, mes: str) -> dict:
        # Se suma con Decimal para que 0.10 + 0.20 dé 0.30 exacto y no 0.30000000000000004.
        cero = Decimal(0)
        totales = {"ingreso": cero, "gasto": cero}
        por_medio = {medio: {"ingreso": cero, "gasto": cero} for medio in MEDIOS}
        por_categoria = {tipo: {} for tipo in CATEGORIAS}
        for m in self.del_mes(mes):
            monto = Decimal(str(m["monto"]))
            totales[m["tipo"]] += monto
            por_medio[m["medio"]][m["tipo"]] += monto
            categorias = por_categoria[m["tipo"]]
            categorias[m["categoria"]] = categorias.get(m["categoria"], cero) + monto

        def cuentas(t: dict) -> dict:
            return {"ingresos": float(t["ingreso"]), "gastos": float(t["gasto"]),
                    "saldo": float(t["ingreso"] - t["gasto"])}

        return {
            "mes": mes,
            **cuentas(totales),
            "por_medio": {medio: cuentas(t) for medio, t in por_medio.items()},
            "por_categoria": {
                "ingresos": {c: float(v) for c, v in por_categoria["ingreso"].items()},
                "gastos": {c: float(v) for c, v in por_categoria["gasto"].items()},
            },
        }


def crear_manejador(caja: Caja):
    """Devuelve una clase de manejador HTTP que usa la caja dada."""

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

        def _id_de_ruta(self) -> int | None:
            partes = self.path.strip("/").split("/")
            if len(partes) == 2 and partes[0] == "movimientos" and partes[1].isdigit():
                return int(partes[1])
            return None

        def _leer_cuerpo(self) -> dict | None:
            """Devuelve el cuerpo JSON como diccionario ({} si viene vacío) o None si no es válido."""
            largo = int(self.headers.get("Content-Length", 0))
            try:
                cuerpo = json.loads(self.rfile.read(largo) or b"{}")
            except json.JSONDecodeError:
                return None
            return cuerpo if isinstance(cuerpo, dict) else None

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/":
                return self._enviar(200, PAGINA_WEB.read_bytes(), "text/html; charset=utf-8")
            if url.path not in ("/movimientos", "/resumen"):
                return self._responder(404, {"error": "Ruta no encontrada"})
            mes = parse_qs(url.query).get("mes", [date.today().strftime("%Y-%m")])[0]
            if url.path == "/movimientos" and mes == "todos":
                return self._responder(200, caja.del_mes(None))
            if not validar_fecha(mes, r"\d{4}-\d{2}", "-01"):
                return self._responder(400, {"error": "El filtro 'mes' debe tener el formato AAAA-MM, por ejemplo 2026-10"})
            if url.path == "/movimientos":
                return self._responder(200, caja.del_mes(mes))
            self._responder(200, caja.resumen(mes))

        def do_POST(self):
            if self.path != "/movimientos":
                return self._responder(404, {"error": "Ruta no encontrada"})
            cuerpo = self._leer_cuerpo()
            if cuerpo is None:
                return self._responder(400, {"error": "JSON inválido"})
            try:
                datos = validar_movimiento(cuerpo)
            except ValueError as e:
                return self._responder(400, {"error": str(e)})
            self._responder(201, caja.registrar(datos))

        def do_DELETE(self):
            id_movimiento = self._id_de_ruta()
            if id_movimiento is None or not caja.eliminar(id_movimiento):
                return self._responder(404, {"error": "Movimiento no encontrado"})
            self._responder(204)

        def log_message(self, formato, *args):
            print(f"[servidor] {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    return Manejador


def main() -> None:
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), crear_manejador(Caja(ARCHIVO_DATOS)))
    puerto = servidor.server_address[1]  # el real, por si PUERTO era 0
    print(f"Caja del consultorio escuchando en http://127.0.0.1:{puerto}  (Ctrl+C para detener)", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    main()
