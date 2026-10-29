"""Módulo Productos: catálogo con precio de costo y de venta, stock, y ventas que entran a la caja.

Rutas:
    GET    /productos               -> productos por nombre, con "ganancia", "margen" (%) y "estado_stock"
                                       ("ok", "bajo" si stock <= stock_minimo, "agotado" si es 0)
    POST   /productos               -> crea un producto (cuerpo: {"nombre": "...", "costo": 3.50, "venta": 6,
                                       "stock": 20 (opcional, 0), "stock_minimo": 5 (opcional, 0)})
    PATCH  /productos/<id>          -> cambia campos (los precios nuevos solo valen para ventas futuras)
    DELETE /productos/<id>          -> elimina el producto (las ventas ya registradas se quedan)
    POST   /productos/<id>/vender   -> vende: registra un ingreso "venta" en la caja y baja el stock
                                       (cuerpo: {"cantidad": 1, "medio": "efectivo"|"yape", "fecha": "AAAA-MM-DD"})
    POST   /productos/<id>/reponer  -> sube el stock; con "pagado_con" también registra el gasto "compras"
                                       (cuerpo: {"cantidad": 10, "pagado_con": "efectivo"|"yape" (opcional), "fecha": ...})
Si en la caja se elimina el movimiento de una venta, el stock vuelve.
"""

from decimal import Decimal

from caja import ModuloCaja, validar_movimiento
from comun import (
    ConIds, Peticion, Respuesta, campos_desconocidos, error, json_invalido, leer_entero, leer_soles,
    ruta_no_encontrada,
)

CAMPOS_PRODUCTO = ("nombre", "costo", "venta", "stock", "stock_minimo")


def validar_producto(cuerpo: dict) -> dict:
    """Devuelve el producto limpio (sin id) o lanza ValueError con un mensaje para el usuario."""
    nombre = str(cuerpo.get("nombre") or "").strip()
    if not nombre:
        raise ValueError("El campo 'nombre' es obligatorio, por ejemplo Paracetamol 500 mg")
    costo = leer_soles(cuerpo.get("costo"), "costo", admite_cero=True)
    venta = leer_soles(cuerpo.get("venta"), "venta")
    stock = leer_entero(cuerpo.get("stock", 0), "stock")
    stock_minimo = leer_entero(cuerpo.get("stock_minimo", 0), "stock_minimo")
    return {"nombre": nombre, "costo": float(costo), "venta": float(venta),
            "stock": stock, "stock_minimo": stock_minimo}


def con_calculos(producto: dict) -> dict:
    """Agrega la ganancia por unidad, el margen sobre el precio de venta y el estado del stock."""
    costo, venta = Decimal(str(producto["costo"])), Decimal(str(producto["venta"]))
    ganancia = venta - costo
    if producto["stock"] == 0:
        estado = "agotado"
    elif producto["stock"] <= producto["stock_minimo"]:
        estado = "bajo"
    else:
        estado = "ok"
    return {**producto, "ganancia": float(ganancia),
            "margen": float(round(ganancia / venta * 100, 1)), "estado_stock": estado}


class Productos(ConIds):
    """Guarda los productos en un archivo JSON."""

    def listado(self) -> list[dict]:
        return sorted((con_calculos(p) for p in self.leer()), key=lambda p: (p["nombre"].casefold(), p["id"]))

    def cambiar_stock(self, producto: dict, diferencia: int) -> dict:
        datos = {c: producto[c] for c in CAMPOS_PRODUCTO}
        datos["stock"] = max(0, datos["stock"] + diferencia)
        return self.actualizar(producto["id"], datos)


class ModuloProductos:
    """Atiende las rutas de productos. Registra las ventas y compras en la caja a través de ModuloCaja."""

    def __init__(self, productos: Productos, modulo_caja: ModuloCaja):
        self.productos = productos
        self.modulo_caja = modulo_caja
        modulo_caja.al_eliminar_movimiento.append(self.devolver_venta)

    def devolver_venta(self, movimiento: dict) -> None:
        """Si se eliminó la venta de un producto, sus unidades vuelven al stock."""
        if movimiento["tipo"] != "ingreso" or "producto" not in movimiento:
            return
        producto = self.productos.buscar(movimiento["producto"])
        if producto is not None:
            self.productos.cambiar_stock(producto, movimiento["cantidad"])

    def atender(self, p: Peticion) -> Respuesta | None:
        if p.partes[0] != "productos":
            return None
        if p.metodo == "GET":
            return (200, self.productos.listado()) if len(p.partes) == 1 else ruta_no_encontrada()
        if p.metodo == "POST":
            return self._post(p)
        if p.metodo in ("PATCH", "DELETE"):
            id_producto = p.id_de("productos")
            producto = self.productos.buscar(id_producto) if id_producto is not None else None
            if producto is None:
                return error(404, "Producto no encontrado")
            if p.metodo == "DELETE":
                self.productos.eliminar(id_producto)
                return 204, None
            return self._editar(p, producto)
        return None

    def _post(self, p: Peticion) -> Respuesta:
        partes = p.partes
        accion = partes[2] if len(partes) == 3 and partes[1].isdigit() and partes[2] in ("vender", "reponer") else None
        if len(partes) != 1 and accion is None:
            return ruta_no_encontrada()
        producto = None
        if accion:
            producto = self.productos.buscar(int(partes[1]))
            if producto is None:
                return error(404, "Producto no encontrado")
        cuerpo = p.cuerpo()
        if cuerpo is None:
            return json_invalido()
        try:
            if accion == "vender":
                return self._vender(producto, cuerpo)
            if accion == "reponer":
                return self._reponer(producto, cuerpo)
            return 201, con_calculos(self.productos.crear(validar_producto(cuerpo)))
        except ValueError as e:
            return error(400, str(e))

    def _editar(self, p: Peticion, original: dict) -> Respuesta:
        cuerpo = p.cuerpo()
        if cuerpo is None:
            return json_invalido()
        if (respuesta := campos_desconocidos(cuerpo, CAMPOS_PRODUCTO)) is not None:
            return respuesta
        try:
            datos = validar_producto({**original, **cuerpo})
        except ValueError as e:
            return error(400, str(e))
        return 200, con_calculos(self.productos.actualizar(original["id"], datos))

    def _vender(self, producto: dict, cuerpo: dict) -> Respuesta:
        cantidad = leer_entero(cuerpo.get("cantidad", 1), "cantidad", minimo=1)
        if producto["stock"] == 0:
            return error(409, f"{producto['nombre']} está agotado")
        if cantidad > producto["stock"]:
            return error(409, f"Solo quedan {producto['stock']} de {producto['nombre']}")
        total = Decimal(str(producto["venta"])) * cantidad
        datos = validar_movimiento({
            "tipo": "ingreso", "monto": str(total), "categoria": "venta",
            "medio": cuerpo.get("medio") or "efectivo", "fecha": cuerpo.get("fecha"),
            "descripcion": f"{cantidad} × {producto['nombre']}",
        })
        estado, movimiento = self.modulo_caja.registrar({**datos, "producto": producto["id"], "cantidad": cantidad})
        if estado != 201:  # el día está cerrado: no se vende ni se toca el stock
            return estado, movimiento
        actualizado = self.productos.cambiar_stock(producto, -cantidad)
        return 201, {"movimiento": movimiento, "producto": con_calculos(actualizado)}

    def _reponer(self, producto: dict, cuerpo: dict) -> Respuesta:
        cantidad = leer_entero(cuerpo.get("cantidad"), "cantidad", minimo=1)
        movimiento = None
        if cuerpo.get("pagado_con"):
            if producto["costo"] == 0:
                raise ValueError(f"El costo de {producto['nombre']} es S/ 0: no hay gasto que registrar")
            datos = validar_movimiento({
                "tipo": "gasto", "monto": str(Decimal(str(producto["costo"])) * cantidad), "categoria": "compras",
                "medio": cuerpo["pagado_con"], "fecha": cuerpo.get("fecha"),
                "descripcion": f"{cantidad} × {producto['nombre']}",
            })
            estado, movimiento = self.modulo_caja.registrar({**datos, "producto": producto["id"], "cantidad": cantidad})
            if estado != 201:
                return estado, movimiento
        actualizado = self.productos.cambiar_stock(producto, cantidad)
        return 201, {"movimiento": movimiento, "producto": con_calculos(actualizado)}
