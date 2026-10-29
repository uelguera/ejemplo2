// Pruebas de punta a punta del CLI de caja contra el servidor Python real.

import { test, before, beforeEach, after } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { mesActual } from "./caja.js";
import { crearCli, ejecutar, levantarServidor, puertoSinServidor } from "./servidor-de-prueba.js";

const RUTA_CLI = fileURLToPath(new URL("./caja.js", import.meta.url));

let servidor, cli;

before(async () => {
  servidor = await levantarServidor();
  cli = crearCli(RUTA_CLI, servidor.url);
});

beforeEach(() => {
  writeFileSync(servidor.archivoCaja, "[]"); // cada prueba empieza con la caja vacía
});

after(() => {
  servidor?.detener();
});

test("registrar y listar un mes", async () => {
  const registro = await cli("registrar", "ingreso", "150", "consulta", "yape", "Control", "anual", "--fecha", "2026-10-05");
  assert.deepEqual(registro, { codigo: 0, salida: "Registrado: 1. 2026-10-05  + S/ 150.00  consulta · yape · Control anual", error: "" });
  await cli("registrar", "gasto", "35.50", "insumos", "efectivo", "--fecha", "2026-10-02");
  assert.equal((await cli("listar", "2026-10")).salida, [
    "2. 2026-10-02  - S/ 35.50  insumos · efectivo",
    "1. 2026-10-05  + S/ 150.00  consulta · yape · Control anual",
  ].join("\n"));
  assert.equal((await cli("listar", "2026-09")).salida, "No hay movimientos en 2026-09.");
});

test("sin --fecha registra hoy y listar sin mes muestra el actual", async () => {
  const { salida } = await cli("registrar", "gasto", "20", "servicios", "efectivo");
  assert.match(salida, new RegExp(`^Registrado: 1\\. ${mesActual()}-\\d{2}  - S/ 20\\.00  servicios · efectivo$`));
  assert.match((await cli("listar")).salida, /^1\. /);
});

test("resumen del mes", async () => {
  await cli("registrar", "ingreso", "150", "consulta", "yape", "--fecha", "2026-10-05");
  await cli("registrar", "ingreso", "80", "certificado", "efectivo", "--fecha", "2026-10-06");
  await cli("registrar", "gasto", "500", "alquiler", "efectivo", "--fecha", "2026-10-01");
  assert.equal((await cli("resumen", "2026-10")).salida, [
    "Resumen de 2026-10",
    "  Ingresos: S/ 230.00",
    "  Gastos:   S/ 500.00",
    "  Saldo:    -S/ 270.00",
    "Por medio de pago:",
    "  efectivo: ingresos S/ 80.00 · gastos S/ 500.00 · saldo -S/ 420.00",
    "  yape: ingresos S/ 150.00 · gastos S/ 0.00 · saldo S/ 150.00",
    "Ingresos por categoría:",
    "  consulta: S/ 150.00",
    "  certificado: S/ 80.00",
    "Gastos por categoría:",
    "  alquiler: S/ 500.00",
  ].join("\n"));
});

test("editar cambia solo los campos indicados", async () => {
  await cli("registrar", "gasto", "35.50", "insumos", "efectivo", "Guantes", "--fecha", "2026-10-02");
  assert.deepEqual(await cli("editar", "1", "monto=40", "medio=yape", "descripcion=Guantes y gasas"), {
    codigo: 0, salida: "Editado: 1. 2026-10-02  - S/ 40.00  insumos · yape · Guantes y gasas", error: "",
  });
  assert.equal((await cli("listar", "2026-10")).salida, "1. 2026-10-02  - S/ 40.00  insumos · yape · Guantes y gasas");
});

test("editar muestra los errores sin cambiar nada", async () => {
  await cli("registrar", "ingreso", "150", "consulta", "yape", "--fecha", "2026-10-05");
  assert.equal((await cli("editar", "1")).error, "Error: Indica qué cambiar, por ejemplo: editar 3 monto=40 medio=yape");
  assert.equal((await cli("editar", "1", "40")).error, 'Error: "40" no tiene la forma campo=valor (por ejemplo monto=40)');
  assert.equal((await cli("editar", "1", "precio=40")).error,
    "Error: No se puede cambiar: precio. Campos válidos: tipo, monto, categoria, medio, fecha, descripcion");
  assert.equal((await cli("editar", "1", "tipo=gasto")).error,
    "Error: La categoría de un gasto debe ser una de: alquiler, insumos, servicios, sueldos, otro");
  assert.equal((await cli("editar", "99", "monto=1")).error, "Error: Movimiento no encontrado");
  assert.equal((await cli("listar", "2026-10")).salida, "1. 2026-10-05  + S/ 150.00  consulta · yape");
});

test("eliminar quita el movimiento", async () => {
  await cli("registrar", "ingreso", "150", "consulta", "yape", "--fecha", "2026-10-05");
  assert.equal((await cli("eliminar", "1")).salida, "Eliminado el movimiento 1.");
  assert.equal((await cli("listar", "2026-10")).salida, "No hay movimientos en 2026-10.");
});

test("respaldar guarda todos los movimientos, de cualquier mes", async () => {
  await cli("registrar", "ingreso", "150", "consulta", "yape", "--fecha", "2026-10-05");
  await cli("registrar", "gasto", "20", "servicios", "efectivo", "--fecha", "2026-09-30");
  const destino = join(servidor.carpeta, "respaldos-caja");
  const { codigo, salida } = await cli("respaldar", destino);
  assert.equal(codigo, 0);
  assert.match(salida, /^Copia de seguridad guardada \(2 movimientos\): .*caja-\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.json$/);
  const archivos = readdirSync(destino);
  assert.equal(archivos.length, 1);
  const copia = JSON.parse(readFileSync(join(destino, archivos[0]), "utf-8"));
  assert.deepEqual(copia.map((m) => m.fecha), ["2026-09-30", "2026-10-05"]);
});

test("los errores del servidor se muestran y salen con código 1", async () => {
  assert.deepEqual(await cli("registrar", "ingreso", "150", "alquiler", "yape"), {
    codigo: 1, salida: "",
    error: "Error: La categoría de un ingreso debe ser una de: consulta, procedimiento, certificado, otro",
  });
  assert.equal((await cli("registrar", "ingreso", "-5", "consulta", "yape")).error,
    "Error: El campo 'monto' debe ser mayor que 0 y como máximo 1000000");
  assert.equal((await cli("registrar", "gasto", "10", "insumos", "tarjeta")).error,
    "Error: El campo 'medio' debe ser uno de: efectivo, yape");
  assert.equal((await cli("registrar", "gasto", "10", "insumos", "yape", "--fecha")).error,
    "Error: Falta la fecha después de --fecha (AAAA-MM-DD)");
  assert.equal((await cli("listar", "octubre")).error,
    "Error: El filtro 'mes' debe tener el formato AAAA-MM, por ejemplo 2026-10");
  assert.equal((await cli("eliminar", "99")).error, "Error: Movimiento no encontrado");
});

test("un comando desconocido muestra el uso", async () => {
  const resultado = await cli("volar");
  assert.equal(resultado.codigo, 1);
  assert.match(resultado.salida, /^Uso: node caja\.js/);
});

test("sin servidor explica cómo levantarlo", async () => {
  const urlVacia = `http://127.0.0.1:${await puertoSinServidor()}`;
  const opciones = { env: { ...process.env, CAJA_URL: urlVacia } };
  const fallo = await ejecutar(process.execPath, [RUTA_CLI, "listar"], opciones).catch((e) => e);
  assert.equal(fallo.code, 1);
  assert.match(fallo.stderr, /No se pudo conectar a .*¿Está corriendo el servidor\?/);
});
