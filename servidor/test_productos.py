"""Pruebas del módulo Productos y de las páginas web de los módulos."""

import unittest
from datetime import date

from servidor_de_prueba import ServidorDePrueba


class PruebasPaginas(ServidorDePrueba):
    def test_paginas_y_archivos_comunes(self):
        casos = [
            ("/", "text/html", "<title>Caja del consultorio</title>"),
            ("/caja", "text/html", "<title>Caja del consultorio</title>"),
            ("/inventario", "text/html", "<title>Productos del consultorio</title>"),
            ("/comun.css", "text/css", ":root"),
            ("/comun.js", "text/javascript", "async function pedir"),
        ]
        for ruta, tipo, contenido in casos:
            with self.subTest(ruta):
                estado, tipo_real, texto = self.pagina(ruta)
                self.assertEqual(estado, 200)
                self.assertIn(tipo, tipo_real)
                self.assertIn(contenido, texto)

    def test_las_paginas_tienen_el_menu(self):
        for ruta in ("/caja", "/inventario"):
            with self.subTest(ruta):
                texto = self.pagina(ruta)[2]
                self.assertIn('href="/caja"', texto)
                self.assertIn('href="/inventario"', texto)

    def test_la_api_de_productos_no_devuelve_la_pagina(self):
        self.assertEqual(self.pedir("GET", "/productos"), (200, []))


class PruebasProductos(ServidorDePrueba):
    def crear(self, **cambios):
        producto = {"nombre": "Paracetamol", "costo": 3.5, "venta": 6, "stock": 20, "stock_minimo": 5, **cambios}
        return self.pedir("POST", "/productos", producto)

    def vender(self, id_producto=1, **cuerpo):
        return self.pedir("POST", f"/productos/{id_producto}/vender",
                          {"cantidad": 3, "medio": "yape", "fecha": "2026-10-05", **cuerpo})

    def reponer(self, id_producto=1, **cuerpo):
        return self.pedir("POST", f"/productos/{id_producto}/reponer", {"cantidad": 10, "fecha": "2026-10-05", **cuerpo})

    def stock(self, id_producto=1):
        return next(p["stock"] for p in self.pedir("GET", "/productos")[1] if p["id"] == id_producto)

    def test_crear_con_calculos(self):
        estado, producto = self.crear(nombre="  Paracetamol  ", costo="3.50", venta="6.00", stock="20")
        self.assertEqual(estado, 201)
        self.assertEqual(producto, {"id": 1, "nombre": "Paracetamol", "costo": 3.5, "venta": 6.0, "stock": 20,
                                    "stock_minimo": 5, "ganancia": 2.5, "margen": 41.7, "estado_stock": "ok"})
        self.assertEqual(self.pedir("GET", "/productos"), (200, [producto]))

    def test_estado_del_stock_y_valores_por_defecto(self):
        _, sin_stock = self.pedir("POST", "/productos", {"nombre": "Gasas", "costo": 1, "venta": 2})
        self.assertEqual((sin_stock["stock"], sin_stock["stock_minimo"], sin_stock["estado_stock"]), (0, 0, "agotado"))
        self.assertEqual(self.crear(nombre="Alcohol", stock=5, stock_minimo=5)[1]["estado_stock"], "bajo")
        self.assertEqual(self.crear(nombre="Jeringas", stock=6, stock_minimo=5)[1]["estado_stock"], "ok")

    def test_venta_menor_que_costo_da_ganancia_negativa(self):
        producto = self.crear(costo=10, venta=8)[1]
        self.assertEqual((producto["ganancia"], producto["margen"]), (-2.0, -25.0))

    def test_costo_cero_se_permite(self):
        producto = self.crear(costo=0, venta=5)[1]
        self.assertEqual((producto["ganancia"], producto["margen"]), (5.0, 100.0))

    def test_ordenados_por_nombre(self):
        for nombre in ("vendas", "Alcohol", "gasas"):
            self.crear(nombre=nombre)
        self.assertEqual([p["nombre"] for p in self.pedir("GET", "/productos")[1]], ["Alcohol", "gasas", "vendas"])

    def test_datos_invalidos_fallan(self):
        invalidos = [
            {"nombre": " "},
            {"costo": -1},
            {"costo": "barato"},
            {"venta": 0},
            {"venta": 1.234},
            {"stock": -1},
            {"stock": 1.5},
            {"stock": "muchos"},
            {"stock_minimo": True},
        ]
        for cambios in invalidos:
            with self.subTest(cambios):
                estado, cuerpo = self.crear(**cambios)
                self.assertEqual(estado, 400)
                self.assertIn("error", cuerpo)
        self.assertEqual(self.pedir("GET", "/productos")[1], [])

    def test_vender_registra_el_ingreso_y_baja_el_stock(self):
        self.crear()
        estado, respuesta = self.vender()
        self.assertEqual(estado, 201)
        self.assertEqual(respuesta["movimiento"], {
            "id": 1, "tipo": "ingreso", "monto": 18.0, "fecha": "2026-10-05", "categoria": "venta",
            "medio": "yape", "descripcion": "3 × Paracetamol", "producto": 1, "cantidad": 3,
        })
        self.assertEqual(respuesta["producto"]["stock"], 17)
        self.assertEqual(self.stock(), 17)
        resumen = self.pedir("GET", "/resumen?mes=2026-10")[1]
        self.assertEqual((resumen["ingresos"], resumen["por_categoria"]["ingresos"]), (18.0, {"venta": 18.0}))

    def test_vender_por_defecto_una_unidad_en_efectivo_hoy(self):
        self.crear()
        movimiento = self.pedir("POST", "/productos/1/vender", {})[1]["movimiento"]
        self.assertEqual((movimiento["cantidad"], movimiento["medio"], movimiento["fecha"], movimiento["monto"]),
                         (1, "efectivo", date.today().isoformat(), 6.0))

    def test_vender_suma_exacta_con_decimales(self):
        self.crear(costo=0.05, venta=0.1)
        self.assertEqual(self.vender(cantidad=3)[1]["movimiento"]["monto"], 0.3)

    def test_vender_sin_stock_suficiente_da_409(self):
        self.crear(stock=2)
        estado, cuerpo = self.vender(cantidad=3)
        self.assertEqual((estado, cuerpo["error"]), (409, "Solo quedan 2 de Paracetamol"))
        self.vender(cantidad=2)
        estado, cuerpo = self.vender(cantidad=1)
        self.assertEqual((estado, cuerpo["error"]), (409, "Paracetamol está agotado"))
        self.assertEqual(len(self.pedir("GET", "/movimientos?mes=2026-10")[1]), 1)

    def test_vender_en_dia_cerrado_no_toca_el_stock(self):
        self.crear()
        self.pedir("POST", "/cierres", {"fecha": "2026-10-05", "efectivo_contado": 0, "yape_app": 0})
        estado, cuerpo = self.vender()
        self.assertEqual(estado, 409)
        self.assertIn("está cerrado", cuerpo["error"])
        self.assertEqual(self.stock(), 20)

    def test_vender_con_datos_invalidos(self):
        self.crear()
        for cuerpo in ({"cantidad": 0}, {"cantidad": -1}, {"cantidad": "dos"}, {"cantidad": 1.5},
                       {"medio": "tarjeta"}, {"fecha": "2026-02-30"}):
            with self.subTest(cuerpo):
                self.assertEqual(self.vender(**cuerpo)[0], 400)
        self.assertEqual(self.stock(), 20)
        self.assertEqual(self.vender(id_producto=99)[0], 404)
        self.assertEqual(self.pedir("POST", "/productos/1/regalar", {})[0], 404)

    def test_reponer_sin_pago_solo_sube_el_stock(self):
        self.crear()
        estado, respuesta = self.reponer()
        self.assertEqual(estado, 201)
        self.assertEqual((respuesta["movimiento"], respuesta["producto"]["stock"]), (None, 30))
        self.assertEqual(self.pedir("GET", "/movimientos?mes=2026-10")[1], [])

    def test_reponer_pagado_registra_la_compra(self):
        self.crear()
        movimiento = self.reponer(pagado_con="efectivo")[1]["movimiento"]
        self.assertEqual(movimiento, {
            "id": 1, "tipo": "gasto", "monto": 35.0, "fecha": "2026-10-05", "categoria": "compras",
            "medio": "efectivo", "descripcion": "10 × Paracetamol", "producto": 1, "cantidad": 10,
        })
        self.assertEqual(self.stock(), 30)
        self.assertEqual(self.pedir("GET", "/cierre?fecha=2026-10-05")[1]["efectivo"]["gastos"], 35.0)

    def test_reponer_con_errores(self):
        self.crear(costo=0)
        self.assertEqual(self.reponer(pagado_con="efectivo")[0], 400)  # costo 0: no hay gasto
        self.assertEqual(self.reponer(cantidad=0)[0], 400)
        self.assertEqual(self.pedir("POST", "/productos/1/reponer", {})[0], 400)  # falta la cantidad
        self.crear(nombre="Gasas")
        self.pedir("POST", "/cierres", {"fecha": "2026-10-05", "efectivo_contado": 0, "yape_app": 0})
        self.assertEqual(self.reponer(id_producto=2, pagado_con="yape")[0], 409)
        self.assertEqual(self.stock(1), 20)
        self.assertEqual(self.stock(2), 20)

    def test_eliminar_la_venta_devuelve_el_stock(self):
        self.crear()
        self.vender()
        self.assertEqual(self.pedir("DELETE", "/movimientos/1")[0], 204)
        self.assertEqual(self.stock(), 20)

    def test_eliminar_la_compra_no_cambia_el_stock(self):
        self.crear()
        self.reponer(pagado_con="yape")
        self.pedir("DELETE", "/movimientos/1")
        self.assertEqual(self.stock(), 30)  # las unidades llegaron; solo se quita el gasto

    def test_editar_la_venta_conserva_el_vinculo(self):
        self.crear()
        self.vender()
        movimiento = self.pedir("PATCH", "/movimientos/1", {"medio": "efectivo"})[1]
        self.assertEqual((movimiento["producto"], movimiento["cantidad"]), (1, 3))
        self.pedir("DELETE", "/movimientos/1")
        self.assertEqual(self.stock(), 20)

    def test_editar_producto_no_cambia_ventas_pasadas(self):
        self.crear()
        self.vender()
        estado, producto = self.pedir("PATCH", "/productos/1", {"venta": 7, "stock_minimo": 20})
        self.assertEqual(estado, 200)
        self.assertEqual((producto["venta"], producto["ganancia"], producto["estado_stock"]), (7.0, 3.5, "bajo"))
        self.assertEqual(self.pedir("GET", "/movimientos?mes=2026-10")[1][0]["monto"], 18.0)
        for cambios in ({"venta": 0}, {"precio": 1}, {}):
            with self.subTest(cambios):
                self.assertEqual(self.pedir("PATCH", "/productos/1", cambios)[0], 400)
        self.assertEqual(self.pedir("PATCH", "/productos/99", {"venta": 1})[0], 404)

    def test_eliminar_producto_conserva_las_ventas(self):
        self.crear()
        self.vender()
        self.assertEqual(self.pedir("DELETE", "/productos/1"), (204, None))
        self.assertEqual(self.pedir("GET", "/productos")[1], [])
        self.assertEqual(len(self.pedir("GET", "/movimientos?mes=2026-10")[1]), 1)
        self.assertEqual(self.pedir("DELETE", "/movimientos/1")[0], 204)  # sin producto: no falla
        self.assertEqual(self.pedir("DELETE", "/productos/1")[0], 404)


if __name__ == "__main__":
    unittest.main()
