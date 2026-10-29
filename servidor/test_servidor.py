"""Pruebas del servidor: levantan la API en un puerto libre con un archivo temporal."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path

from servidor import Caja, crear_manejador


class PruebasCaja(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        caja = Caja(Path(self.carpeta.name) / "movimientos.json")
        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), crear_manejador(caja))
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

    def registrar(self, **cambios):
        movimiento = {"tipo": "ingreso", "monto": 150, "categoria": "consulta",
                      "medio": "yape", "fecha": "2026-10-05", **cambios}
        return self.pedir("POST", "/movimientos", movimiento)

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


if __name__ == "__main__":
    unittest.main()
