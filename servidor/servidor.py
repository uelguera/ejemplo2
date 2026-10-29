"""API de la caja del consultorio (ingresos y gastos en soles): servidor HTTP mínimo con la librería estándar.

Endpoints de movimientos:
    GET    /                  -> página web de la caja
    GET    /movimientos       -> movimientos de un mes, por fecha (?mes=AAAA-MM; por defecto el actual;
                                 ?mes=todos devuelve todos, para las copias de seguridad)
    POST   /movimientos       -> registra un movimiento (cuerpo: {"tipo": "ingreso"|"gasto",
                                 "monto": 150, "categoria": "...", "medio": "efectivo"|"yape",
                                 "fecha": "AAAA-MM-DD" (opcional, hoy), "descripcion": "..." (opcional)})
    PATCH  /movimientos/<id>  -> cambia uno o más campos (mismo cuerpo que POST, solo lo que cambia)
    DELETE /movimientos/<id>  -> elimina un movimiento
    GET    /resumen           -> totales de un mes (?mes=AAAA-MM; por defecto el actual)

Endpoints de cierre de caja (cada día empieza en S/ 0 de efectivo):
    GET    /cierre            -> cierre guardado de un día, o la vista previa si sigue abierto
                                 (?fecha=AAAA-MM-DD; por defecto hoy)
    POST   /cierres           -> cierra un día (cuerpo: {"efectivo_contado": 190, "yape_app": 150,
                                 "fecha": "AAAA-MM-DD" (opcional, hoy), "nota": "..." (opcional)})
    DELETE /cierres/<fecha>   -> reabre un día cerrado
    GET    /cierres           -> cierres de un mes (?mes=AAAA-MM; por defecto el actual)
Un día cerrado queda bloqueado: sus movimientos no se pueden registrar, editar ni eliminar (409).

Variables de entorno opcionales:
    CAJA_PUERTO      -> puerto (por defecto 8001; 0 = uno libre cualquiera)
    CAJA_ARCHIVO     -> archivo JSON de movimientos (por defecto servidor/movimientos.json)
    CIERRES_ARCHIVO  -> archivo JSON de cierres (por defecto servidor/cierres.json)
"""

import json
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PUERTO = int(os.environ.get("CAJA_PUERTO", 8001))
ARCHIVO_DATOS = Path(os.environ.get("CAJA_ARCHIVO", Path(__file__).parent / "movimientos.json"))
ARCHIVO_CIERRES = Path(os.environ.get("CIERRES_ARCHIVO", Path(__file__).parent / "cierres.json"))
PAGINA_WEB = Path(__file__).parent / "web" / "index.html"

# Cambia estas listas para usar otras categorías o medios de pago
# (las categorías están repetidas en web/index.html: cambia ambas).
CATEGORIAS = {
    "ingreso": ("consulta", "procedimiento", "certificado", "otro"),
    "gasto": ("alquiler", "insumos", "servicios", "sueldos", "otro"),
}
MEDIOS = ("efectivo", "yape")
MONTO_MAXIMO = Decimal("1000000")
CAMPOS = ("tipo", "monto", "categoria", "medio", "fecha", "descripcion")


def validar_fecha(texto: str, patron: str, relleno: str) -> bool:
    """Comprueba el formato exacto y que la fecha exista (relleno completa un mes hasta un día)."""
    if not re.fullmatch(patron, texto):
        return False
    try:
        date.fromisoformat(texto + relleno)
    except ValueError:
        return False
    return True


def es_dia(texto: str) -> bool:
    return validar_fecha(texto, r"\d{4}-\d{2}-\d{2}", "")


def es_mes(texto: str) -> bool:
    return validar_fecha(texto, r"\d{4}-\d{2}", "-01")


def leer_soles(valor, campo: str, admite_cero: bool = False) -> Decimal:
    """Convierte un monto en soles (número o texto) a Decimal, o lanza ValueError con un mensaje para el usuario."""
    try:
        if isinstance(valor, bool) or valor is None:
            raise InvalidOperation
        monto = Decimal(str(valor).strip())
    except InvalidOperation:
        raise ValueError(f"El campo '{campo}' debe ser un número, por ejemplo 150 o 35.50") from None
    minimo_valido = monto >= 0 if admite_cero else monto > 0
    if not monto.is_finite() or not minimo_valido or monto > MONTO_MAXIMO:
        desde = "0 o más" if admite_cero else "mayor que 0"
        raise ValueError(f"El campo '{campo}' debe ser {desde} y como máximo {MONTO_MAXIMO}")
    if monto.as_tuple().exponent < -2:
        raise ValueError(f"El campo '{campo}' admite como máximo 2 decimales")
    return monto


def validar_movimiento(cuerpo: dict) -> dict:
    """Devuelve el movimiento limpio (sin id) o lanza ValueError con un mensaje para el usuario."""
    tipo = str(cuerpo.get("tipo", "")).strip().lower()
    if tipo not in CATEGORIAS:
        raise ValueError("El campo 'tipo' debe ser 'ingreso' o 'gasto'")

    monto = leer_soles(cuerpo.get("monto"), "monto")

    categoria = str(cuerpo.get("categoria", "")).strip().lower()
    if categoria not in CATEGORIAS[tipo]:
        raise ValueError(f"La categoría de un {tipo} debe ser una de: {', '.join(CATEGORIAS[tipo])}")

    medio = str(cuerpo.get("medio", "")).strip().lower()
    if medio not in MEDIOS:
        raise ValueError(f"El campo 'medio' debe ser uno de: {', '.join(MEDIOS)}")

    fecha = cuerpo.get("fecha") or date.today().isoformat()
    if not es_dia(str(fecha)):
        raise ValueError("El campo 'fecha' debe tener el formato AAAA-MM-DD, por ejemplo 2026-10-29")

    return {
        "tipo": tipo,
        "monto": float(monto),
        "fecha": str(fecha),
        "categoria": categoria,
        "medio": medio,
        "descripcion": str(cuerpo.get("descripcion") or "").strip(),
    }


def calcular_cierre(fecha: str, movimientos: list[dict]) -> dict:
    """Vista previa del cierre de un día: el efectivo esperado (el día empieza en 0) y lo recibido por Yape."""
    suma = {(medio, tipo): Decimal(0) for medio in MEDIOS for tipo in CATEGORIAS}
    for m in movimientos:
        suma[(m["medio"], m["tipo"])] += Decimal(str(m["monto"]))
    esperado = suma[("efectivo", "ingreso")] - suma[("efectivo", "gasto")]
    return {
        "fecha": fecha,
        "cerrado": False,
        "efectivo": {"ingresos": float(suma[("efectivo", "ingreso")]),
                     "gastos": float(suma[("efectivo", "gasto")]),
                     "esperado": float(esperado)},
        "yape": {"ingresos": float(suma[("yape", "ingreso")])},
    }


class ArchivoJson:
    """Guarda una lista de registros en un archivo JSON."""

    def __init__(self, ruta: Path):
        self.ruta = ruta

    def leer(self) -> list[dict]:
        if not self.ruta.exists():
            return []
        return json.loads(self.ruta.read_text(encoding="utf-8"))

    def escribir(self, registros: list[dict]) -> None:
        self.ruta.write_text(json.dumps(registros, indent=2, ensure_ascii=False), encoding="utf-8")


class Caja(ArchivoJson):
    """Guarda los ingresos y gastos del consultorio en un archivo JSON."""

    def registrar(self, datos: dict) -> dict:
        movimientos = self.leer()
        nuevo_id = max((m["id"] for m in movimientos), default=0) + 1
        movimiento = {"id": nuevo_id, **datos}
        movimientos.append(movimiento)
        self.escribir(movimientos)
        return movimiento

    def buscar(self, id_movimiento: int) -> dict | None:
        return next((m for m in self.leer() if m["id"] == id_movimiento), None)

    def actualizar(self, id_movimiento: int, datos: dict) -> dict | None:
        """Reemplaza los datos del movimiento (ya validados con validar_movimiento)."""
        movimientos = self.leer()
        for posicion, movimiento in enumerate(movimientos):
            if movimiento["id"] == id_movimiento:
                movimientos[posicion] = {"id": id_movimiento, **datos}
                self.escribir(movimientos)
                return movimientos[posicion]
        return None

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

    def del_dia(self, fecha: str) -> list[dict]:
        return [m for m in self.leer() if m["fecha"] == fecha]

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


class Cierres(ArchivoJson):
    """Guarda los cierres de caja diarios (uno por fecha) en un archivo JSON."""

    def buscar(self, fecha: str) -> dict | None:
        return next((c for c in self.leer() if c["fecha"] == fecha), None)

    def esta_cerrado(self, fecha: str) -> bool:
        return self.buscar(fecha) is not None

    def cerrar(self, vista_previa: dict, efectivo_contado: Decimal, yape_app: Decimal, nota: str) -> dict:
        """Guarda una foto del cierre con las diferencias (lo contado − lo esperado)."""
        efectivo, yape = vista_previa["efectivo"], vista_previa["yape"]
        cierre = {
            "fecha": vista_previa["fecha"],
            "cerrado": True,
            "efectivo": {**efectivo, "contado": float(efectivo_contado),
                         "diferencia": float(efectivo_contado - Decimal(str(efectivo["esperado"])))},
            "yape": {**yape, "app": float(yape_app),
                     "diferencia": float(yape_app - Decimal(str(yape["ingresos"])))},
            "nota": nota,
            "cerrado_en": datetime.now().isoformat(timespec="seconds"),
        }
        cierres = self.leer()
        cierres.append(cierre)
        self.escribir(cierres)
        return cierre

    def reabrir(self, fecha: str) -> bool:
        cierres = self.leer()
        restantes = [c for c in cierres if c["fecha"] != fecha]
        if len(restantes) == len(cierres):
            return False
        self.escribir(restantes)
        return True

    def del_mes(self, mes: str | None) -> list[dict]:
        """Cierres del mes 'AAAA-MM' (o todos si mes es None), por fecha."""
        return sorted((c for c in self.leer() if mes is None or c["fecha"].startswith(mes + "-")),
                      key=lambda c: c["fecha"])


def crear_manejador(caja: Caja, cierres: Cierres):
    """Devuelve una clase de manejador HTTP que usa la caja y los cierres dados."""

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

        def _dia_cerrado(self, fecha: str) -> None:
            self._responder(409, {"error": f"El día {fecha} está cerrado. Reábrelo para hacer cambios."})

        def _parte_de_ruta(self, recurso: str) -> str | None:
            """En /recurso/<valor> devuelve <valor>; si la ruta es otra, None."""
            partes = self.path.strip("/").split("/")
            if len(partes) == 2 and partes[0] == recurso and partes[1]:
                return partes[1]
            return None

        def _id_de_ruta(self) -> int | None:
            valor = self._parte_de_ruta("movimientos")
            return int(valor) if valor is not None and valor.isdigit() else None

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
            consulta = parse_qs(url.query)
            if url.path == "/":
                return self._enviar(200, PAGINA_WEB.read_bytes(), "text/html; charset=utf-8")
            if url.path == "/cierre":
                fecha = consulta.get("fecha", [date.today().isoformat()])[0]
                if not es_dia(fecha):
                    return self._responder(400, {"error": "El filtro 'fecha' debe tener el formato AAAA-MM-DD, por ejemplo 2026-10-29"})
                return self._responder(200, cierres.buscar(fecha) or calcular_cierre(fecha, caja.del_dia(fecha)))
            if url.path not in ("/movimientos", "/resumen", "/cierres"):
                return self._responder(404, {"error": "Ruta no encontrada"})
            mes = consulta.get("mes", [date.today().strftime("%Y-%m")])[0]
            if url.path == "/movimientos" and mes == "todos":
                return self._responder(200, caja.del_mes(None))
            if url.path == "/cierres" and mes == "todos":
                return self._responder(200, cierres.del_mes(None))
            if not es_mes(mes):
                return self._responder(400, {"error": "El filtro 'mes' debe tener el formato AAAA-MM, por ejemplo 2026-10"})
            if url.path == "/movimientos":
                return self._responder(200, caja.del_mes(mes))
            if url.path == "/cierres":
                return self._responder(200, cierres.del_mes(mes))
            self._responder(200, caja.resumen(mes))

        def do_POST(self):
            if self.path not in ("/movimientos", "/cierres"):
                return self._responder(404, {"error": "Ruta no encontrada"})
            cuerpo = self._leer_cuerpo()
            if cuerpo is None:
                return self._responder(400, {"error": "JSON inválido"})
            if self.path == "/cierres":
                return self._cerrar_dia(cuerpo)
            try:
                datos = validar_movimiento(cuerpo)
            except ValueError as e:
                return self._responder(400, {"error": str(e)})
            if cierres.esta_cerrado(datos["fecha"]):
                return self._dia_cerrado(datos["fecha"])
            self._responder(201, caja.registrar(datos))

        def _cerrar_dia(self, cuerpo: dict) -> None:
            fecha = str(cuerpo.get("fecha") or date.today().isoformat())
            if not es_dia(fecha):
                return self._responder(400, {"error": "El campo 'fecha' debe tener el formato AAAA-MM-DD, por ejemplo 2026-10-29"})
            if fecha > date.today().isoformat():
                return self._responder(400, {"error": f"No se puede cerrar un día que aún no llega ({fecha})"})
            if cierres.esta_cerrado(fecha):
                return self._responder(409, {"error": f"El día {fecha} ya está cerrado. Reábrelo para cerrarlo de nuevo."})
            try:
                efectivo_contado = leer_soles(cuerpo.get("efectivo_contado"), "efectivo_contado", admite_cero=True)
                yape_app = leer_soles(cuerpo.get("yape_app"), "yape_app", admite_cero=True)
            except ValueError as e:
                return self._responder(400, {"error": str(e)})
            nota = str(cuerpo.get("nota") or "").strip()
            vista_previa = calcular_cierre(fecha, caja.del_dia(fecha))
            self._responder(201, cierres.cerrar(vista_previa, efectivo_contado, yape_app, nota))

        def do_PATCH(self):
            id_movimiento = self._id_de_ruta()
            original = caja.buscar(id_movimiento) if id_movimiento is not None else None
            if original is None:
                return self._responder(404, {"error": "Movimiento no encontrado"})
            cuerpo = self._leer_cuerpo()
            if cuerpo is None:
                return self._responder(400, {"error": "JSON inválido"})
            desconocidos = sorted(set(cuerpo) - set(CAMPOS))
            if desconocidos:
                return self._responder(400, {"error": f"No se puede cambiar: {', '.join(desconocidos)}. "
                                                      f"Campos válidos: {', '.join(CAMPOS)}"})
            if not cuerpo:
                return self._responder(400, {"error": "Indica al menos un campo para cambiar"})
            if cierres.esta_cerrado(original["fecha"]):
                return self._dia_cerrado(original["fecha"])
            try:
                datos = validar_movimiento({**original, **cuerpo})
            except ValueError as e:
                return self._responder(400, {"error": str(e)})
            if cierres.esta_cerrado(datos["fecha"]):  # no se puede mover un movimiento a un día cerrado
                return self._dia_cerrado(datos["fecha"])
            self._responder(200, caja.actualizar(id_movimiento, datos))

        def do_DELETE(self):
            fecha_cierre = self._parte_de_ruta("cierres")
            if fecha_cierre is not None:
                if not cierres.reabrir(fecha_cierre):
                    return self._responder(404, {"error": f"El día {fecha_cierre} no está cerrado"})
                return self._responder(204)
            id_movimiento = self._id_de_ruta()
            movimiento = caja.buscar(id_movimiento) if id_movimiento is not None else None
            if movimiento is None:
                return self._responder(404, {"error": "Movimiento no encontrado"})
            if cierres.esta_cerrado(movimiento["fecha"]):
                return self._dia_cerrado(movimiento["fecha"])
            caja.eliminar(id_movimiento)
            self._responder(204)

        def log_message(self, formato, *args):
            print(f"[servidor] {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    return Manejador


def main() -> None:
    manejador = crear_manejador(Caja(ARCHIVO_DATOS), Cierres(ARCHIVO_CIERRES))
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), manejador)
    puerto = servidor.server_address[1]  # el real, por si PUERTO era 0
    print(f"Caja del consultorio escuchando en http://127.0.0.1:{puerto}  (Ctrl+C para detener)", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    main()
