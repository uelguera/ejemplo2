// Pruebas de punta a punta del CLI de productos contra el servidor Python real.

import { test, before, beforeEach, after } from "node:test";
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { crearCli, levantarServidor } from "./servidor-de-prueba.js";

const RUTA_PRODUCTOS = fileURLToPath(new URL("./productos.js", import.meta.url));
const RUTA_CAJA = fileURLToPath(new URL("./caja.js", import.meta.url));

let servidor, cli, caja;

before(async () => {
  servidor = await levantarServidor();
  cli = crearCli(RUTA_PRODUCTOS, servidor.url);
  caja = crearCli(RUTA_CAJA, servidor.url);
});

beforeEach(() => {
  for (const archivo of [servidor.archivoCaja, servidor.archivoCierres, servidor.archivoGastosFijos, servidor.archivoProductos]) {
    writeFileSync(archivo, "[]"); // cada prueba empieza sin datos
  }
});

after(() => {
  servidor?.detener();
});

test("agregar y listar productos", async () => {
  assert.match((await cli("listar")).salida, /^No hay productos\. Agrega uno con:/);
  assert.deepEqual(await cli("agregar", "Paracetamol 500 mg", "3.50", "6", "--stock", "20", "--minimo", "5"), {
    codigo: 0, error: "",
    salida: "Agregado: 1. Paracetamol 500 mg  costo S/ 3.50 · venta S/ 6.00 · ganancia S/ 2.50 (41.7%)  → 20 en stock",
  });
  await cli("agregar", "Alcohol", "4", "7");
  assert.equal((await cli("listar")).salida, [
    "2. Alcohol  costo S/ 4.00 · venta S/ 7.00 · ganancia S/ 3.00 (42.9%)  → agotado",
    "1. Paracetamol 500 mg  costo S/ 3.50 · venta S/ 6.00 · ganancia S/ 2.50 (41.7%)  → 20 en stock",
    "Valor del stock (a costo): S/ 70.00 · por reponer: 1",
  ].join("\n"));
});

test("vender registra el ingreso en la caja y baja el stock", async () => {
  await cli("agregar", "Paracetamol", "3.50", "6", "--stock", "5", "--minimo", "2");
  assert.equal((await cli("vender", "1", "3", "--medio", "yape", "--fecha", "2026-10-05")).salida,
    "Vendido: 3 × Paracetamol por S/ 18.00 (yape), registrado en la caja. Ahora: quedan 2 (stock bajo).");
  assert.equal((await caja("listar", "2026-10")).salida, "1. 2026-10-05  + S/ 18.00  venta · yape · 3 × Paracetamol");
  assert.equal((await cli("vender", "1", "3", "--fecha", "2026-10-05")).error, "Error: Solo quedan 2 de Paracetamol");

  await caja("eliminar", "1"); // anular la venta devuelve el stock
  assert.match((await cli("listar")).salida, /→ 5 en stock\n/);
});

test("reponer con y sin gasto en la caja", async () => {
  await cli("agregar", "Gasas", "1.20", "2.50");
  assert.equal((await cli("reponer", "1", "10")).salida, "Repuesto: Gasas, ahora hay 10.");
  assert.equal((await cli("reponer", "1", "5", "--pagado", "efectivo", "--fecha", "2026-10-05")).salida,
    "Repuesto: Gasas, ahora hay 15. Gasto de S/ 6.00 (efectivo) registrado en la caja.");
  assert.equal((await caja("listar", "2026-10")).salida, "1. 2026-10-05  - S/ 6.00  compras · efectivo · 5 × Gasas");
});

test("editar, eliminar y errores", async () => {
  await cli("agregar", "Alcohol", "4", "7", "--stock", "3");
  assert.equal((await cli("editar", "1", "venta=8", "stock_minimo=3")).salida,
    "Editado: 1. Alcohol  costo S/ 4.00 · venta S/ 8.00 · ganancia S/ 4.00 (50%)  → quedan 3 (stock bajo)");
  assert.equal((await cli("agregar", "Alcohol", "en", "gel", "4", "7")).error,
    'Error: No se entiende "4 7". Si el nombre tiene espacios, ponlo entre comillas: "Paracetamol 500 mg"');
  assert.equal((await cli("agregar", "Jeringas", "1", "0")).error,
    "Error: El campo 'venta' debe ser mayor que 0 y como máximo 1000000");
  assert.equal((await cli("vender", "1", "0")).error,
    "Error: El campo 'cantidad' debe ser un número entero de 1 o más (como máximo 1000000)");
  assert.equal((await cli("reponer", "1", "2", "--pagado")).error, "Error: Falta el valor después de --pagado (efectivo o yape)");
  assert.equal((await cli("vender", "9")).error, "Error: Producto no encontrado");
  assert.equal((await cli("eliminar", "1")).salida, "Eliminado el producto 1. Sus ventas ya registradas siguen en la caja.");
});

test("un comando desconocido muestra el uso", async () => {
  const resultado = await cli("regalar");
  assert.equal(resultado.codigo, 1);
  assert.match(resultado.salida, /^Uso: node productos\.js/);
});
