import { test } from "node:test";
import assert from "node:assert/strict";
import { describirStock, formatearCatalogo, formatearProducto } from "./productos.js";

const paracetamol = {
  id: 1, nombre: "Paracetamol", costo: 3.5, venta: 6, stock: 20, stock_minimo: 5,
  ganancia: 2.5, margen: 41.7, estado_stock: "ok",
};

test("un producto muestra sus precios, la ganancia y el stock", () => {
  assert.equal(formatearProducto(paracetamol),
    "1. Paracetamol  costo S/ 3.50 · venta S/ 6.00 · ganancia S/ 2.50 (41.7%)  → 20 en stock");
});

test("el stock avisa cuando queda poco o se agotó", () => {
  assert.equal(describirStock({ ...paracetamol, stock: 3, estado_stock: "bajo" }), "quedan 3 (stock bajo)");
  assert.equal(describirStock({ ...paracetamol, stock: 0, estado_stock: "agotado" }), "agotado");
});

test("el catálogo suma el valor del stock a costo sin errores de redondeo", () => {
  const centavos = { ...paracetamol, id: 2, costo: 0.1, stock: 3, estado_stock: "bajo" };
  const lineas = formatearCatalogo([paracetamol, centavos]).split("\n");
  assert.equal(lineas.length, 3);
  assert.equal(lineas.at(-1), "Valor del stock (a costo): S/ 70.30 · por reponer: 1"); // 3.50 × 20 + 0.10 × 3
});
