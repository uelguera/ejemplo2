"""Lo que comparten los módulos (caja, productos...): archivos JSON, validaciones de montos y fechas,
y la forma en que cada módulo recibe una petición y devuelve su respuesta."""

import json
import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Cambia estas listas para usar otras categorías o medios de pago
# (están repetidas en web/comun.js: cambia ambas).
CATEGORIAS = {
    "ingreso": ("consulta", "procedimiento", "certificado", "venta", "otro"),
    "gasto": ("alquiler", "insumos", "compras", "servicios", "sueldos", "otro"),
}
MEDIOS = ("efectivo", "yape")
MONTO_MAXIMO = Decimal("1000000")
CANTIDAD_MAXIMA = 1_000_000

Respuesta = tuple[int, object]  # (código HTTP, cuerpo que se envía como JSON; None = sin cuerpo)


class Peticion:
    """Lo que un módulo necesita saber de una petición HTTP."""

    def __init__(self, metodo: str, ruta: str, consulta: dict, leer_cuerpo: Callable[[], dict | None]):
        self.metodo = metodo
        self.partes = ruta.strip("/").split("/")  # "/productos/3/vender" -> ["productos", "3", "vender"]
        self.consulta = consulta
        self._leer_cuerpo = leer_cuerpo

    def valor(self, nombre: str, por_defecto: str) -> str:
        """Valor de un parámetro de la URL (?nombre=valor)."""
        return self.consulta.get(nombre, [por_defecto])[0]

    def cuerpo(self) -> dict | None:
        """El cuerpo JSON como diccionario ({} si viene vacío) o None si no es válido."""
        return self._leer_cuerpo()

    def id_de(self, recurso: str) -> int | None:
        """En /recurso/<número> devuelve el número; si la ruta es otra, None."""
        if len(self.partes) == 2 and self.partes[0] == recurso and self.partes[1].isdigit():
            return int(self.partes[1])
        return None


def error(estado: int, mensaje: str) -> Respuesta:
    return estado, {"error": mensaje}


def ruta_no_encontrada() -> Respuesta:
    return error(404, "Ruta no encontrada")


def json_invalido() -> Respuesta:
    return error(400, "JSON inválido")


def campos_desconocidos(cuerpo: dict, validos: tuple[str, ...]) -> Respuesta | None:
    """Para PATCH: error si el cuerpo trae campos que no se pueden cambiar o viene vacío."""
    desconocidos = sorted(set(cuerpo) - set(validos))
    if desconocidos:
        return error(400, f"No se puede cambiar: {', '.join(desconocidos)}. Campos válidos: {', '.join(validos)}")
    if not cuerpo:
        return error(400, "Indica al menos un campo para cambiar")
    return None


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


def leer_entero(valor, campo: str, minimo: int = 0) -> int:
    """Convierte una cantidad entera (número o texto) a int, o lanza ValueError con un mensaje para el usuario."""
    texto = "" if valor is None or isinstance(valor, bool) else str(valor).strip()
    if not texto.isdigit() or not minimo <= int(texto) <= CANTIDAD_MAXIMA:
        raise ValueError(f"El campo '{campo}' debe ser un número entero de {minimo} o más (como máximo {CANTIDAD_MAXIMA})")
    return int(texto)


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


class ConIds(ArchivoJson):
    """Registros identificados por un "id" numérico que se asigna al crearlos."""

    def crear(self, datos: dict) -> dict:
        registros = self.leer()
        nuevo_id = max((r["id"] for r in registros), default=0) + 1
        registro = {"id": nuevo_id, **datos}
        registros.append(registro)
        self.escribir(registros)
        return registro

    def buscar(self, id_registro: int) -> dict | None:
        return next((r for r in self.leer() if r["id"] == id_registro), None)

    def actualizar(self, id_registro: int, datos: dict) -> dict | None:
        """Reemplaza los datos del registro (ya validados)."""
        registros = self.leer()
        for posicion, registro in enumerate(registros):
            if registro["id"] == id_registro:
                registros[posicion] = {"id": id_registro, **datos}
                self.escribir(registros)
                return registros[posicion]
        return None

    def eliminar(self, id_registro: int) -> bool:
        registros = self.leer()
        restantes = [r for r in registros if r["id"] != id_registro]
        if len(restantes) == len(registros):
            return False
        self.escribir(restantes)
        return True
