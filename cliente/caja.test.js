import { test } from "node:test";
import assert from "node:assert/strict";
import {
  describirDiferencia, formatearCierre, formatearLineaCierre, formatearMovimiento, formatearResumen,
  formatearSoles, leerCambios, mesActual, sacarFecha,
} from "./caja.js";
import { nombreRespaldo } from "./api.js";

test("la diferencia del efectivo se describe como faltante o sobrante", () => {
  assert.equal(describirDiferencia(0), "cuadra");
  assert.equal(describirDiferencia(-4.5), "faltan S/ 4.50");
  assert.equal(describirDiferencia(10), "sobran S/ 10.00");
});

test("la diferencia de Yape dice qué falta registrar o qué sobra", () => {
  assert.equal(describirDiferencia(0, "yape"), "cuadra");
  assert.equal(describirDiferencia(20, "yape"), "en la app hay S/ 20.00 sin registrar");
  assert.equal(describirDiferencia(-15, "yape"), "S/ 15.00 registrados que no están en la app");
});

test("un cierre guardado sin nota no muestra la línea de nota", () => {
  const cierre = {
    fecha: "2026-10-05", cerrado: true, cerrado_en: "2026-10-05T19:42:10", nota: "",
    efectivo: { ingresos: 80, gastos: 35.5, esperado: 44.5, contado: 44.5, diferencia: 0 },
    yape: { ingresos: 150, app: 150, diferencia: 0 },
  };
  assert.equal(formatearCierre(cierre), [
    "Cierre del 2026-10-05: cerrado el 2026-10-05 19:42",
    "  Efectivo: esperado S/ 44.50 · contado S/ 44.50 → cuadra",
    "  Yape: registrado S/ 150.00 · app S/ 150.00 → cuadra",
  ].join("\n"));
  assert.equal(formatearLineaCierre(cierre), "2026-10-05  efectivo: cuadra · yape: cuadra");
});

test("--fecha se saca de los argumentos y el resto queda como nota", () => {
  const args = ["Di", "--fecha", "2026-10-05", "mal"];
  assert.equal(sacarFecha(args), "2026-10-05");
  assert.deepEqual(args, ["Di", "mal"]);
  assert.equal(sacarFecha(["sin", "fecha"]), undefined);
  assert.throws(() => sacarFecha(["--fecha"]), /Falta la fecha/);
});

test("los cambios se leen como campo=valor; el valor puede tener espacios y signos =", () => {
  assert.deepEqual(leerCambios(["monto=40", "descripcion=Pago a=b y c"]), { monto: "40", descripcion: "Pago a=b y c" });
  assert.deepEqual(leerCambios(["descripcion="]), { descripcion: "" });
  assert.throws(() => leerCambios([]), /Indica qué cambiar/);
  assert.throws(() => leerCambios(["=40"]), /no tiene la forma campo=valor/);
});

test("el nombre del respaldo lleva fecha y hora con ceros a la izquierda", () => {
  assert.equal(nombreRespaldo("caja", new Date(2026, 0, 2, 9, 5, 3)), "caja-2026-01-02_09-05-03.json");
});

test("los montos se muestran en soles con dos decimales y espacio normal", () => {
  assert.equal(formatearSoles(1234.5), "S/ 1,234.50");
  assert.equal(formatearSoles(0), "S/ 0.00");
  assert.equal(formatearSoles(-99.8), "-S/ 99.80");
});

test("un ingreso se muestra con + y sus detalles", () => {
  const ingreso = { id: 1, tipo: "ingreso", monto: 150, fecha: "2026-10-05", categoria: "consulta", medio: "yape", descripcion: "Control" };
  assert.equal(formatearMovimiento(ingreso), "1. 2026-10-05  + S/ 150.00  consulta · yape · Control");
});

test("un gasto sin descripción se muestra con -", () => {
  const gasto = { id: 2, tipo: "gasto", monto: 35.5, fecha: "2026-10-06", categoria: "insumos", medio: "efectivo", descripcion: "" };
  assert.equal(formatearMovimiento(gasto), "2. 2026-10-06  - S/ 35.50  insumos · efectivo");
});

test("el mes actual lleva cero a la izquierda", () => {
  assert.equal(mesActual(new Date(2026, 0, 31)), "2026-01");
  assert.equal(mesActual(new Date(2026, 11, 1)), "2026-12");
});

test("el resumen omite las secciones de categorías vacías", () => {
  const vacio = { ingresos: 0, gastos: 0, saldo: 0 };
  const texto = formatearResumen({
    mes: "2026-10", ...vacio,
    por_medio: { efectivo: vacio, yape: vacio },
    por_categoria: { ingresos: {}, gastos: {} },
  });
  assert.equal(texto, [
    "Resumen de 2026-10",
    "  Ingresos: S/ 0.00",
    "  Gastos:   S/ 0.00",
    "  Saldo:    S/ 0.00",
    "Por medio de pago:",
    "  efectivo: ingresos S/ 0.00 · gastos S/ 0.00 · saldo S/ 0.00",
    "  yape: ingresos S/ 0.00 · gastos S/ 0.00 · saldo S/ 0.00",
  ].join("\n"));
});
