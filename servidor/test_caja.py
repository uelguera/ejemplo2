"""Pruebas del módulo Caja: movimientos, resumen, cierre de caja y gastos fijos."""

import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta

from servidor_de_prueba import ServidorDePrueba


class PruebasCaja(ServidorDePrueba):
    def test_pagina_web(self):
        with urllib.request.urlopen(self.base + "/") as respuesta:
            self.assertEqual(respuesta.status, 200)
            self.assertIn("text/html", respuesta.headers["Content-Type"])
            self.assertIn("<title>Caja del consultorio</title>", respuesta.read().decode("utf-8"))

    def test_ruta_desconocida_da_404(self):
        self.assertEqual(self.pedir("GET", "/tareas")[0], 404)
        self.assertEqual(self.pedir("POST", "/resumen", {})[0], 404)

    def test_registrar_y_listar(self):
        estado, movimiento = self.registrar(descripcion="  Control  ")
        self.assertEqual(estado, 201)
        self.assertEqual(movimiento, {"id": 1, "tipo": "ingreso", "monto": 150.0, "fecha": "2026-10-05",
                                      "categoria": "consulta", "medio": "yape", "descripcion": "Control"})
        self.assertEqual(self.pedir("GET", "/movimientos?mes=2026-10"), (200, [movimiento]))

    def test_acepta_mayusculas_y_monto_como_texto(self):
        estado, movimiento = self.registrar(tipo="Gasto", monto="35.50", categoria="Insumos", medio="EFECTIVO")
        self.assertEqual(estado, 201)
        self.assertEqual((movimiento["tipo"], movimiento["monto"], movimiento["categoria"], movimiento["medio"]),
                         ("gasto", 35.5, "insumos", "efectivo"))

    def test_sin_fecha_usa_hoy(self):
        estado, movimiento = self.pedir("POST", "/movimientos", {
            "tipo": "gasto", "monto": 20, "categoria": "servicios", "medio": "efectivo"})
        self.assertEqual(estado, 201)
        self.assertEqual(movimiento["fecha"], date.today().isoformat())
        self.assertEqual(self.pedir("GET", "/movimientos")[1], [movimiento])  # sin ?mes = mes actual

    def test_datos_invalidos_fallan(self):
        invalidos = [
            {"tipo": "prestamo"},
            {"monto": 0},
            {"monto": -10},
            {"monto": 10.555},
            {"monto": "diez"},
            {"monto": True},
            {"monto": 2000000},
            {"categoria": "alquiler"},  # es categoría de gasto, no de ingreso
            {"medio": "tarjeta"},
            {"fecha": "05/10/2026"},
            {"fecha": "2026-02-30"},
        ]
        for cambios in invalidos:
            with self.subTest(cambios):
                estado, cuerpo = self.registrar(**cambios)
                self.assertEqual(estado, 400)
                self.assertIn("error", cuerpo)
        self.assertEqual(self.pedir("GET", "/movimientos?mes=2026-10")[1], [])

    def test_json_invalido_falla(self):
        peticion = urllib.request.Request(self.base + "/movimientos", data=b"{no es json", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(peticion)
        with error.exception as e:
            self.assertEqual(e.code, 400)

    def test_lista_por_mes_ordenada_por_fecha(self):
        self.registrar(fecha="2026-10-20")
        self.registrar(fecha="2026-09-30")
        self.registrar(fecha="2026-10-03")
        octubre = self.pedir("GET", "/movimientos?mes=2026-10")[1]
        self.assertEqual([m["fecha"] for m in octubre], ["2026-10-03", "2026-10-20"])
        self.assertEqual(len(self.pedir("GET", "/movimientos?mes=2026-09")[1]), 1)
        todos = self.pedir("GET", "/movimientos?mes=todos")[1]
        self.assertEqual([m["fecha"] for m in todos], ["2026-09-30", "2026-10-03", "2026-10-20"])

    def test_mes_invalido_falla(self):
        for ruta in ("/movimientos?mes=octubre", "/resumen?mes=2026-13", "/resumen?mes=todos"):
            with self.subTest(ruta):
                self.assertEqual(self.pedir("GET", ruta)[0], 400)

    def test_resumen(self):
        self.registrar(monto=0.1)
        self.registrar(monto=0.2, medio="efectivo", categoria="certificado")
        self.registrar(tipo="gasto", monto=100, categoria="alquiler", medio="efectivo")
        self.registrar(monto=999, fecha="2026-11-01")  # otro mes: no cuenta
        estado, resumen = self.pedir("GET", "/resumen?mes=2026-10")
        self.assertEqual(estado, 200)
        self.assertEqual(resumen, {
            "mes": "2026-10",
            "ingresos": 0.3,  # exacto gracias a Decimal (no 0.30000000000000004)
            "gastos": 100.0,
            "saldo": -99.7,
            "por_medio": {
                "efectivo": {"ingresos": 0.2, "gastos": 100.0, "saldo": -99.8},
                "yape": {"ingresos": 0.1, "gastos": 0.0, "saldo": 0.1},
            },
            "por_categoria": {
                "ingresos": {"consulta": 0.1, "certificado": 0.2},
                "gastos": {"alquiler": 100.0},
            },
        })

    def test_editar_solo_lo_que_cambia(self):
        self.registrar(descripcion="Control")
        estado, movimiento = self.pedir("PATCH", "/movimientos/1", {"monto": "180.50", "medio": "efectivo"})
        self.assertEqual(estado, 200)
        self.assertEqual(movimiento, {"id": 1, "tipo": "ingreso", "monto": 180.5, "fecha": "2026-10-05",
                                      "categoria": "consulta", "medio": "efectivo", "descripcion": "Control"})
        self.assertEqual(self.pedir("GET", "/movimientos?mes=2026-10")[1], [movimiento])

    def test_editar_cambia_el_resumen_y_el_mes(self):
        self.registrar()
        self.pedir("PATCH", "/movimientos/1", {"tipo": "gasto", "categoria": "insumos", "fecha": "2026-09-30"})
        self.assertEqual(self.pedir("GET", "/movimientos?mes=2026-10")[1], [])
        resumen = self.pedir("GET", "/resumen?mes=2026-09")[1]
        self.assertEqual((resumen["ingresos"], resumen["gastos"]), (0.0, 150.0))

    def test_editar_con_datos_invalidos_no_cambia_nada(self):
        self.registrar()
        invalidos = [
            {"tipo": "gasto"},  # "consulta" no es categoría de gasto
            {"monto": -1},
            {"fecha": "2026-13-01"},
            {"id": 7},
            {"precio": 10},
            {},
        ]
        for cambios in invalidos:
            with self.subTest(cambios):
                estado, cuerpo = self.pedir("PATCH", "/movimientos/1", cambios)
                self.assertEqual(estado, 400)
                self.assertIn("error", cuerpo)
        self.assertEqual(self.pedir("GET", "/movimientos?mes=2026-10")[1][0]["monto"], 150.0)

    def test_editar_inexistente_da_404(self):
        self.assertEqual(self.pedir("PATCH", "/movimientos/99", {"monto": 10})[0], 404)
        self.assertEqual(self.pedir("PATCH", "/movimientos/abc", {"monto": 10})[0], 404)

    def test_eliminar(self):
        self.registrar()
        self.assertEqual(self.pedir("DELETE", "/movimientos/1"), (204, None))
        self.assertEqual(self.pedir("GET", "/movimientos?mes=2026-10")[1], [])
        self.assertEqual(self.pedir("DELETE", "/movimientos/1")[0], 404)
        self.assertEqual(self.pedir("DELETE", "/movimientos/abc")[0], 404)


class PruebasCierre(ServidorDePrueba):
    def preparar_dia(self):
        """El 2026-10-05: efectivo +80 −35.50 (esperado 44.50) y Yape +150. Otro día no cuenta."""
        self.registrar()  # ingreso 150 por Yape
        self.registrar(monto=80, categoria="certificado", medio="efectivo")
        self.registrar(tipo="gasto", monto="35.50", categoria="insumos", medio="efectivo")
        self.registrar(monto=999, medio="efectivo", fecha="2026-10-06")

    def cerrar(self, **cambios):
        return self.pedir("POST", "/cierres", {"fecha": "2026-10-05", "efectivo_contado": 40,
                                                "yape_app": 150, **cambios})

    def test_vista_previa_del_dia_abierto(self):
        self.preparar_dia()
        self.assertEqual(self.pedir("GET", "/cierre?fecha=2026-10-05"), (200, {
            "fecha": "2026-10-05",
            "cerrado": False,
            "efectivo": {"ingresos": 80.0, "gastos": 35.5, "esperado": 44.5},
            "yape": {"ingresos": 150.0},
        }))

    def test_vista_previa_sin_fecha_es_hoy(self):
        cierre = self.pedir("GET", "/cierre")[1]
        self.assertEqual((cierre["fecha"], cierre["cerrado"]), (date.today().isoformat(), False))

    def test_cerrar_con_faltante(self):
        self.preparar_dia()
        estado, cierre = self.cerrar(nota="  Di mal un vuelto  ")
        self.assertEqual(estado, 201)
        cerrado_en = cierre.pop("cerrado_en")
        self.assertRegex(cerrado_en, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
        self.assertEqual(cierre, {
            "fecha": "2026-10-05",
            "cerrado": True,
            "efectivo": {"ingresos": 80.0, "gastos": 35.5, "esperado": 44.5, "contado": 40.0, "diferencia": -4.5},
            "yape": {"ingresos": 150.0, "app": 150.0, "diferencia": 0.0},
            "nota": "Di mal un vuelto",
        })
        self.assertEqual(self.pedir("GET", "/cierre?fecha=2026-10-05")[1], {**cierre, "cerrado_en": cerrado_en})

    def test_cerrar_con_sobrante_y_yape_sin_anotar(self):
        self.preparar_dia()
        cierre = self.cerrar(efectivo_contado="50.00", yape_app=170)[1]
        self.assertEqual(cierre["efectivo"]["diferencia"], 5.5)
        self.assertEqual(cierre["yape"]["diferencia"], 20.0)  # la app recibió 20 que no se registraron

    def test_cerrar_cuadra_con_decimales_exactos(self):
        self.registrar(monto=0.1, medio="efectivo")
        self.registrar(monto=0.2, medio="efectivo")
        cierre = self.cerrar(efectivo_contado=0.3, yape_app=0)[1]
        self.assertEqual(cierre["efectivo"]["esperado"], 0.3)
        self.assertEqual(cierre["efectivo"]["diferencia"], 0.0)

    def test_cerrar_dia_sin_movimientos(self):
        estado, cierre = self.cerrar(efectivo_contado=0, yape_app=0)
        self.assertEqual(estado, 201)
        self.assertEqual(cierre["efectivo"]["diferencia"], 0.0)

    def test_cerrar_dos_veces_da_409(self):
        self.cerrar()
        estado, cuerpo = self.cerrar(efectivo_contado=44.5)
        self.assertEqual(estado, 409)
        self.assertIn("ya está cerrado", cuerpo["error"])
        self.assertEqual(self.pedir("GET", "/cierre?fecha=2026-10-05")[1]["efectivo"]["contado"], 40.0)

    def test_cerrar_con_datos_invalidos_falla(self):
        manana = (date.today() + timedelta(days=1)).isoformat()
        invalidos = [
            {"fecha": manana},
            {"fecha": "2026-02-30"},
            {"efectivo_contado": -1},
            {"efectivo_contado": None},
            {"yape_app": "mucho"},
            {"yape_app": 1.234},
        ]
        for cambios in invalidos:
            with self.subTest(cambios):
                estado, cuerpo = self.cerrar(**cambios)
                self.assertEqual(estado, 400)
                self.assertIn("error", cuerpo)
        self.assertEqual(self.pedir("GET", "/cierres?mes=todos")[1], [])

    def test_reabrir(self):
        self.cerrar()
        self.assertEqual(self.pedir("DELETE", "/cierres/2026-10-05"), (204, None))
        self.assertFalse(self.pedir("GET", "/cierre?fecha=2026-10-05")[1]["cerrado"])
        self.assertEqual(self.pedir("DELETE", "/cierres/2026-10-05")[0], 404)
        self.assertEqual(self.cerrar()[0], 201)  # se puede volver a cerrar

    def test_listar_cierres_por_mes(self):
        self.cerrar(fecha="2026-10-20")
        self.cerrar(fecha="2026-10-05")
        self.cerrar(fecha="2026-09-30")
        self.assertEqual([c["fecha"] for c in self.pedir("GET", "/cierres?mes=2026-10")[1]],
                         ["2026-10-05", "2026-10-20"])
        self.assertEqual(len(self.pedir("GET", "/cierres?mes=todos")[1]), 3)
        self.assertEqual(self.pedir("GET", "/cierres?mes=octubre")[0], 400)

    def test_dia_cerrado_bloquea_los_movimientos(self):
        self.preparar_dia()
        self.cerrar()
        intentos = [
            ("POST", "/movimientos", {"tipo": "ingreso", "monto": 10, "categoria": "consulta",
                                      "medio": "yape", "fecha": "2026-10-05"}),
            ("PATCH", "/movimientos/1", {"monto": 10}),           # editar un movimiento del día cerrado
            ("PATCH", "/movimientos/4", {"fecha": "2026-10-05"}),  # mover otro hacia el día cerrado
            ("DELETE", "/movimientos/1", None),
        ]
        for metodo, ruta, cuerpo in intentos:
            with self.subTest(metodo=metodo, ruta=ruta, cuerpo=cuerpo):
                estado, respuesta = self.pedir(metodo, ruta, cuerpo)
                self.assertEqual(estado, 409)
                self.assertEqual(respuesta["error"], "El día 2026-10-05 está cerrado. Reábrelo para hacer cambios.")
        self.assertEqual(len(self.pedir("GET", "/movimientos?mes=2026-10")[1]), 4)
        self.assertEqual(self.pedir("PATCH", "/movimientos/4", {"monto": 1})[0], 200)  # otro día: sin bloqueo

    def test_reabrir_desbloquea(self):
        self.preparar_dia()
        self.cerrar()
        self.pedir("DELETE", "/cierres/2026-10-05")
        self.assertEqual(self.pedir("PATCH", "/movimientos/1", {"monto": 10})[0], 200)
        self.assertEqual(self.pedir("DELETE", "/movimientos/1")[0], 204)


class PruebasGastosFijos(ServidorDePrueba):
    def crear_fijo(self, **cambios):
        plantilla = {"nombre": "Alquiler", "categoria": "alquiler", "monto": 1200, "medio": "efectivo", "dia": 5, **cambios}
        return self.pedir("POST", "/gastos-fijos", plantilla)

    def pagar(self, id_gasto=1, **cuerpo):
        return self.pedir("POST", f"/gastos-fijos/{id_gasto}/pagar", {"fecha": "2026-10-03", **cuerpo})

    def test_crear_y_ver_pendiente(self):
        estado, plantilla = self.crear_fijo(nombre="  Alquiler  ", monto="1200.00", dia="5")
        self.assertEqual(estado, 201)
        self.assertEqual(plantilla, {"id": 1, "nombre": "Alquiler", "categoria": "alquiler",
                                     "monto": 1200.0, "medio": "efectivo", "dia": 5})
        self.assertEqual(self.pedir("GET", "/gastos-fijos?mes=2026-10")[1],
                         [{**plantilla, "pagado": False, "movimiento": None}])
        self.assertEqual(self.pedir("GET", "/gastos-fijos?mes=todos")[1], [plantilla])

    def test_sin_dia_y_orden_por_vencimiento(self):
        self.crear_fijo(nombre="Internet", categoria="servicios", monto=90, dia=None)
        self.crear_fijo(nombre="Luz", categoria="servicios", monto=80, dia=20)
        self.crear_fijo(nombre="Alquiler", dia=5)
        nombres = [g["nombre"] for g in self.pedir("GET", "/gastos-fijos?mes=2026-10")[1]]
        self.assertEqual(nombres, ["Alquiler", "Luz", "Internet"])  # sin día de vencimiento, al final

    def test_datos_invalidos_fallan(self):
        invalidos = [
            {"nombre": "  "},
            {"categoria": "consulta"},  # es categoría de ingreso
            {"monto": 0},
            {"monto": "mil"},
            {"medio": "tarjeta"},
            {"dia": 0},
            {"dia": 32},
            {"dia": 5.5},
            {"dia": True},
        ]
        for cambios in invalidos:
            with self.subTest(cambios):
                estado, cuerpo = self.crear_fijo(**cambios)
                self.assertEqual(estado, 400)
                self.assertIn("error", cuerpo)
        self.assertEqual(self.pedir("GET", "/gastos-fijos?mes=todos")[1], [])

    def test_pagar_registra_el_gasto(self):
        self.crear_fijo()
        estado, movimiento = self.pagar()
        self.assertEqual(estado, 201)
        self.assertEqual(movimiento, {"id": 1, "tipo": "gasto", "monto": 1200.0, "fecha": "2026-10-03",
                                      "categoria": "alquiler", "medio": "efectivo", "descripcion": "Alquiler",
                                      "gasto_fijo": 1})
        estado_mes = self.pedir("GET", "/gastos-fijos?mes=2026-10")[1][0]
        self.assertEqual((estado_mes["pagado"], estado_mes["movimiento"]),
                         (True, {"id": 1, "fecha": "2026-10-03", "medio": "efectivo"}))
        self.assertEqual(self.pedir("GET", "/resumen?mes=2026-10")[1]["gastos"], 1200.0)
        self.assertFalse(self.pedir("GET", "/gastos-fijos?mes=2026-11")[1][0]["pagado"])  # cada mes por separado

    def test_pagar_con_otro_medio_y_sin_fecha(self):
        self.crear_fijo()
        estado, movimiento = self.pedir("POST", "/gastos-fijos/1/pagar", {"medio": "yape"})
        self.assertEqual(estado, 201)
        self.assertEqual((movimiento["medio"], movimiento["fecha"]), ("yape", date.today().isoformat()))

    def test_pagar_dos_veces_en_el_mismo_mes_da_409(self):
        self.crear_fijo()
        self.pagar()
        estado, cuerpo = self.pagar(fecha="2026-10-28")
        self.assertEqual(estado, 409)
        self.assertEqual(cuerpo["error"], "Alquiler ya está pagado en 2026-10")
        self.assertEqual(self.pagar(fecha="2026-11-03")[0], 201)  # el mes siguiente sí

    def test_pagar_en_dia_cerrado_da_409(self):
        self.crear_fijo()
        self.pedir("POST", "/cierres", {"fecha": "2026-10-03", "efectivo_contado": 0, "yape_app": 0})
        estado, cuerpo = self.pagar()
        self.assertEqual(estado, 409)
        self.assertIn("está cerrado", cuerpo["error"])

    def test_pagar_con_datos_invalidos_o_inexistente(self):
        self.crear_fijo()
        self.assertEqual(self.pagar(fecha="2026-02-30")[0], 400)
        self.assertEqual(self.pagar(medio="tarjeta")[0], 400)
        self.assertEqual(self.pagar(id_gasto=99)[0], 404)
        self.assertEqual(self.pedir("POST", "/gastos-fijos/1/cobrar", {})[0], 404)

    def test_eliminar_el_pago_lo_deja_pendiente(self):
        self.crear_fijo()
        self.pagar()
        self.pedir("DELETE", "/movimientos/1")
        self.assertFalse(self.pedir("GET", "/gastos-fijos?mes=2026-10")[1][0]["pagado"])

    def test_editar_el_pago_conserva_el_vinculo(self):
        self.crear_fijo()
        self.pagar()
        estado, movimiento = self.pedir("PATCH", "/movimientos/1", {"medio": "yape", "fecha": "2026-10-04"})
        self.assertEqual(estado, 200)
        self.assertEqual(movimiento["gasto_fijo"], 1)
        self.assertTrue(self.pedir("GET", "/gastos-fijos?mes=2026-10")[1][0]["pagado"])
        self.assertEqual(self.pedir("PATCH", "/movimientos/1", {"gasto_fijo": 2})[0], 400)  # no se puede cambiar

    def test_movimiento_normal_no_cuenta_como_pago(self):
        self.crear_fijo()
        self.registrar(tipo="gasto", categoria="alquiler", monto=1200, medio="efectivo", descripcion="Alquiler")
        self.assertFalse(self.pedir("GET", "/gastos-fijos?mes=2026-10")[1][0]["pagado"])

    def test_editar_plantilla_no_cambia_lo_pagado(self):
        self.crear_fijo()
        self.pagar()
        estado, plantilla = self.pedir("PATCH", "/gastos-fijos/1", {"monto": 1300, "dia": ""})
        self.assertEqual(estado, 200)
        self.assertEqual((plantilla["monto"], plantilla["dia"], plantilla["nombre"]), (1300.0, None, "Alquiler"))
        self.assertEqual(self.pedir("GET", "/movimientos?mes=2026-10")[1][0]["monto"], 1200.0)
        for cambios in ({"monto": -1}, {"precio": 1}, {}):
            with self.subTest(cambios):
                self.assertEqual(self.pedir("PATCH", "/gastos-fijos/1", cambios)[0], 400)
        self.assertEqual(self.pedir("PATCH", "/gastos-fijos/99", {"monto": 1})[0], 404)

    def test_eliminar_plantilla_conserva_los_pagos(self):
        self.crear_fijo()
        self.pagar()
        self.assertEqual(self.pedir("DELETE", "/gastos-fijos/1"), (204, None))
        self.assertEqual(self.pedir("GET", "/gastos-fijos?mes=2026-10")[1], [])
        self.assertEqual(len(self.pedir("GET", "/movimientos?mes=2026-10")[1]), 1)
        self.assertEqual(self.pedir("DELETE", "/gastos-fijos/1")[0], 404)


if __name__ == "__main__":
    unittest.main()
