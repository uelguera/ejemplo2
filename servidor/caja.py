"""Módulo Caja: ingresos y gastos en soles, cierre de caja diario y gastos fijos.

Rutas:
    GET    /movimientos       -> movimientos de un mes, por fecha (?mes=AAAA-MM; por defecto el actual;
                                 ?mes=todos devuelve todos, para las copias de seguridad)
    POST   /movimientos       -> registra un movimiento (cuerpo: {"tipo": "ingreso"|"gasto",
                                 "monto": 150, "categoria": "...", "medio": "efectivo"|"yape",
                                 "fecha": "AAAA-MM-DD" (opcional, hoy), "descripcion": "..." (opcional)})
    PATCH  /movimientos/<id>  -> cambia uno o más campos (mismo cuerpo que POST, solo lo que cambia)
    DELETE /movimientos/<id>  -> elimina un movimiento
    GET    /resumen           -> totales de un mes (?mes=AAAA-MM; por defecto el actual)

Cierre de caja (cada día empieza en S/ 0 de efectivo):
    GET    /cierre            -> cierre guardado de un día, o la vista previa si sigue abierto
                                 (?fecha=AAAA-MM-DD; por defecto hoy)
    POST   /cierres           -> cierra un día (cuerpo: {"efectivo_contado": 190, "yape_app": 150,
                                 "fecha": "AAAA-MM-DD" (opcional, hoy), "nota": "..." (opcional)})
    DELETE /cierres/<fecha>   -> reabre un día cerrado
    GET    /cierres           -> cierres de un mes (?mes=AAAA-MM; por defecto el actual)
Un día cerrado queda bloqueado: sus movimientos no se pueden registrar, editar ni eliminar (409).

Gastos fijos (plantillas que se pagan una vez al mes):
    GET    /gastos-fijos               -> plantillas con su estado en un mes ("pagado" y su "movimiento")
                                          (?mes=AAAA-MM; por defecto el actual; ?mes=todos = solo las plantillas)
    POST   /gastos-fijos               -> crea una plantilla (cuerpo: {"nombre": "Alquiler", "categoria": "alquiler",
                                          "monto": 1200, "medio": "efectivo"|"yape", "dia": 5 (opcional, vencimiento)})
    PATCH  /gastos-fijos/<id>          -> cambia campos de la plantilla (no toca lo ya pagado)
    DELETE /gastos-fijos/<id>          -> elimina la plantilla (los pagos hechos se quedan)
    POST   /gastos-fijos/<id>/pagar    -> registra el pago como movimiento con "gasto_fijo": <id>
                                          (cuerpo opcional: {"fecha": "AAAA-MM-DD" (hoy), "medio": "yape"})
Un gasto fijo está pagado en un mes si hay un movimiento de ese mes con su "gasto_fijo".
"""

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal

from comun import (
    CATEGORIAS, MEDIOS, ArchivoJson, ConIds, Peticion, Respuesta, campos_desconocidos, error, es_dia, es_mes,
    json_invalido, leer_soles, ruta_no_encontrada,
)

CAMPOS = ("tipo", "monto", "categoria", "medio", "fecha", "descripcion")
CAMPOS_GASTO_FIJO = ("nombre", "categoria", "monto", "medio", "dia")
# Campos que otros módulos agregan a un movimiento y que se conservan al editarlo.
VINCULOS = ("gasto_fijo", "producto", "cantidad")


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


def validar_gasto_fijo(cuerpo: dict) -> dict:
    """Devuelve la plantilla limpia (sin id) o lanza ValueError con un mensaje para el usuario."""
    nombre = str(cuerpo.get("nombre") or "").strip()
    if not nombre:
        raise ValueError("El campo 'nombre' es obligatorio, por ejemplo Alquiler")

    categoria = str(cuerpo.get("categoria", "")).strip().lower()
    if categoria not in CATEGORIAS["gasto"]:
        raise ValueError(f"La categoría de un gasto debe ser una de: {', '.join(CATEGORIAS['gasto'])}")

    monto = leer_soles(cuerpo.get("monto"), "monto")

    medio = str(cuerpo.get("medio", "")).strip().lower()
    if medio not in MEDIOS:
        raise ValueError(f"El campo 'medio' debe ser uno de: {', '.join(MEDIOS)}")

    dia = cuerpo.get("dia")
    if dia in (None, ""):
        dia = None
    else:
        texto = str(dia).strip()
        if isinstance(dia, bool) or not texto.isdigit() or not 1 <= int(texto) <= 31:
            raise ValueError("El campo 'dia' (vencimiento) debe ser un número del 1 al 31")
        dia = int(texto)

    return {"nombre": nombre, "categoria": categoria, "monto": float(monto), "medio": medio, "dia": dia}


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


def dia_cerrado(fecha: str) -> Respuesta:
    return error(409, f"El día {fecha} está cerrado. Reábrelo para hacer cambios.")


class Caja(ConIds):
    """Guarda los ingresos y gastos del consultorio en un archivo JSON."""

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


class GastosFijos(ConIds):
    """Guarda las plantillas de gastos fijos (alquiler, luz...) en un archivo JSON."""

    def estado_del_mes(self, movimientos_del_mes: list[dict]) -> list[dict]:
        """Cada plantilla con "pagado" y el "movimiento" que la paga ese mes; primero las que vencen antes."""
        pagos = {m["gasto_fijo"]: m for m in movimientos_del_mes if "gasto_fijo" in m}
        plantillas = sorted(self.leer(), key=lambda g: (g["dia"] is None, g["dia"] or 0, g["id"]))
        return [
            {**g, "pagado": g["id"] in pagos,
             "movimiento": {c: pagos[g["id"]][c] for c in ("id", "fecha", "medio")} if g["id"] in pagos else None}
            for g in plantillas
        ]


class ModuloCaja:
    """Atiende las rutas de la caja: movimientos, resumen, cierres y gastos fijos."""

    RECURSOS = ("movimientos", "resumen", "cierre", "cierres", "gastos-fijos")

    def __init__(self, caja: Caja, cierres: Cierres, gastos_fijos: GastosFijos):
        self.caja = caja
        self.cierres = cierres
        self.gastos_fijos = gastos_fijos
        # Otros módulos se enteran aquí cuando se elimina un movimiento (p. ej. Productos devuelve el stock).
        self.al_eliminar_movimiento: list[Callable[[dict], None]] = []

    def registrar(self, datos: dict) -> Respuesta:
        """Registra un movimiento ya validado si su día no está cerrado. Lo usan también otros módulos."""
        if self.cierres.esta_cerrado(datos["fecha"]):
            return dia_cerrado(datos["fecha"])
        return 201, self.caja.crear(datos)

    def atender(self, p: Peticion) -> Respuesta | None:
        if p.partes[0] not in self.RECURSOS:
            return None
        atender = {"GET": self._get, "POST": self._post, "PATCH": self._patch, "DELETE": self._delete}.get(p.metodo)
        return atender(p) if atender else None

    def _get(self, p: Peticion) -> Respuesta:
        if len(p.partes) != 1:
            return ruta_no_encontrada()
        recurso = p.partes[0]
        if recurso == "cierre":
            fecha = p.valor("fecha", date.today().isoformat())
            if not es_dia(fecha):
                return error(400, "El filtro 'fecha' debe tener el formato AAAA-MM-DD, por ejemplo 2026-10-29")
            return 200, self.cierres.buscar(fecha) or calcular_cierre(fecha, self.caja.del_dia(fecha))
        mes = p.valor("mes", date.today().strftime("%Y-%m"))
        if mes == "todos" and recurso != "resumen":
            todos = {"movimientos": lambda: self.caja.del_mes(None), "cierres": lambda: self.cierres.del_mes(None),
                     "gastos-fijos": self.gastos_fijos.leer}
            return 200, todos[recurso]()
        if not es_mes(mes):
            return error(400, "El filtro 'mes' debe tener el formato AAAA-MM, por ejemplo 2026-10")
        if recurso == "movimientos":
            return 200, self.caja.del_mes(mes)
        if recurso == "gastos-fijos":
            return 200, self.gastos_fijos.estado_del_mes(self.caja.del_mes(mes))
        if recurso == "cierres":
            return 200, self.cierres.del_mes(mes)
        return 200, self.caja.resumen(mes)

    def _post(self, p: Peticion) -> Respuesta:
        partes = p.partes
        pagar = len(partes) == 3 and partes[0] == "gastos-fijos" and partes[1].isdigit() and partes[2] == "pagar"
        if not pagar and (len(partes) != 1 or partes[0] not in ("movimientos", "cierres", "gastos-fijos")):
            return ruta_no_encontrada()
        cuerpo = p.cuerpo()
        if cuerpo is None:
            return json_invalido()
        if pagar:
            return self._pagar_gasto_fijo(int(partes[1]), cuerpo)
        if partes[0] == "cierres":
            return self._cerrar_dia(cuerpo)
        try:
            if partes[0] == "gastos-fijos":
                return 201, self.gastos_fijos.crear(validar_gasto_fijo(cuerpo))
            datos = validar_movimiento(cuerpo)
        except ValueError as e:
            return error(400, str(e))
        return self.registrar(datos)

    def _pagar_gasto_fijo(self, id_gasto: int, cuerpo: dict) -> Respuesta:
        gasto = self.gastos_fijos.buscar(id_gasto)
        if gasto is None:
            return error(404, "Gasto fijo no encontrado")
        try:
            datos = validar_movimiento({
                "tipo": "gasto", "monto": gasto["monto"], "categoria": gasto["categoria"],
                "medio": cuerpo.get("medio") or gasto["medio"], "fecha": cuerpo.get("fecha"),
                "descripcion": gasto["nombre"],
            })
        except ValueError as e:
            return error(400, str(e))
        mes = datos["fecha"][:7]
        if any(m.get("gasto_fijo") == id_gasto for m in self.caja.del_mes(mes)):
            return error(409, f"{gasto['nombre']} ya está pagado en {mes}")
        return self.registrar({**datos, "gasto_fijo": id_gasto})

    def _cerrar_dia(self, cuerpo: dict) -> Respuesta:
        fecha = str(cuerpo.get("fecha") or date.today().isoformat())
        if not es_dia(fecha):
            return error(400, "El campo 'fecha' debe tener el formato AAAA-MM-DD, por ejemplo 2026-10-29")
        if fecha > date.today().isoformat():
            return error(400, f"No se puede cerrar un día que aún no llega ({fecha})")
        if self.cierres.esta_cerrado(fecha):
            return error(409, f"El día {fecha} ya está cerrado. Reábrelo para cerrarlo de nuevo.")
        try:
            efectivo_contado = leer_soles(cuerpo.get("efectivo_contado"), "efectivo_contado", admite_cero=True)
            yape_app = leer_soles(cuerpo.get("yape_app"), "yape_app", admite_cero=True)
        except ValueError as e:
            return error(400, str(e))
        nota = str(cuerpo.get("nota") or "").strip()
        vista_previa = calcular_cierre(fecha, self.caja.del_dia(fecha))
        return 201, self.cierres.cerrar(vista_previa, efectivo_contado, yape_app, nota)

    def _patch(self, p: Peticion) -> Respuesta:
        if p.partes[0] == "gastos-fijos" and len(p.partes) > 1:
            return self._editar_gasto_fijo(p)
        id_movimiento = p.id_de("movimientos")
        original = self.caja.buscar(id_movimiento) if id_movimiento is not None else None
        if original is None:
            return error(404, "Movimiento no encontrado")
        cuerpo = p.cuerpo()
        if cuerpo is None:
            return json_invalido()
        if (respuesta := campos_desconocidos(cuerpo, CAMPOS)) is not None:
            return respuesta
        if self.cierres.esta_cerrado(original["fecha"]):
            return dia_cerrado(original["fecha"])
        try:
            datos = validar_movimiento({**original, **cuerpo})
        except ValueError as e:
            return error(400, str(e))
        if self.cierres.esta_cerrado(datos["fecha"]):  # no se puede mover un movimiento a un día cerrado
            return dia_cerrado(datos["fecha"])
        # Sigue vinculado a lo que lo creó (el pago de un gasto fijo, la venta de un producto...).
        datos.update({c: original[c] for c in VINCULOS if c in original})
        return 200, self.caja.actualizar(id_movimiento, datos)

    def _editar_gasto_fijo(self, p: Peticion) -> Respuesta:
        id_gasto = p.id_de("gastos-fijos")
        original = self.gastos_fijos.buscar(id_gasto) if id_gasto is not None else None
        if original is None:
            return error(404, "Gasto fijo no encontrado")
        cuerpo = p.cuerpo()
        if cuerpo is None:
            return json_invalido()
        if (respuesta := campos_desconocidos(cuerpo, CAMPOS_GASTO_FIJO)) is not None:
            return respuesta
        try:
            datos = validar_gasto_fijo({**original, **cuerpo})
        except ValueError as e:
            return error(400, str(e))
        return 200, self.gastos_fijos.actualizar(id_gasto, datos)

    def _delete(self, p: Peticion) -> Respuesta:
        if p.partes[0] == "cierres" and len(p.partes) == 2 and p.partes[1]:
            fecha = p.partes[1]
            if not self.cierres.reabrir(fecha):
                return error(404, f"El día {fecha} no está cerrado")
            return 204, None
        if p.partes[0] == "gastos-fijos" and len(p.partes) > 1:
            id_gasto = p.id_de("gastos-fijos")
            if id_gasto is None or not self.gastos_fijos.eliminar(id_gasto):
                return error(404, "Gasto fijo no encontrado")
            return 204, None
        id_movimiento = p.id_de("movimientos")
        movimiento = self.caja.buscar(id_movimiento) if id_movimiento is not None else None
        if movimiento is None:
            return error(404, "Movimiento no encontrado")
        if self.cierres.esta_cerrado(movimiento["fecha"]):
            return dia_cerrado(movimiento["fecha"])
        self.caja.eliminar(id_movimiento)
        for avisar in self.al_eliminar_movimiento:
            avisar(movimiento)
        return 204, None
