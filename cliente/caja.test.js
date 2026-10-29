import { test } from "node:test";
import assert from "node:assert/strict";
import { formatearMovimiento, formatearResumen, formatearSoles, mesActual } from "./caja.js";
import { nombreRespaldo } from "./api.js";

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
