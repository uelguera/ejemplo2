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
  writeFileSync(servidor.archivoCierres, "[]"); // y sin días cerrados
  writeFileSync(servidor.archivoGastosFijos, "[]"); // ni gastos fijos
  writeFileSync(servidor.archivoProductos, "[]"); // ni productos
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
    "Error: La categoría de un gasto debe ser una de: alquiler, insumos, compras, servicios, sueldos, otro");
  assert.equal((await cli("editar", "99", "monto=1")).error, "Error: Movimiento no encontrado");
  assert.equal((await cli("listar", "2026-10")).salida, "1. 2026-10-05  + S/ 150.00  consulta · yape");
});

test("eliminar quita el movimiento", async () => {
  await cli("registrar", "ingreso", "150", "consulta", "yape", "--fecha", "2026-10-05");
  assert.equal((await cli("eliminar", "1")).salida, "Eliminado el movimiento 1.");
  assert.equal((await cli("listar", "2026-10")).salida, "No hay movimientos en 2026-10.");
});

test("respaldar guarda movimientos, cierres, gastos fijos y productos, de cualquier mes", async () => {
  await cli("registrar", "ingreso", "150", "consulta", "yape", "--fecha", "2026-10-05");
  await cli("registrar", "gasto", "20", "servicios", "efectivo", "--fecha", "2026-09-30");
  await cli("cerrar", "0", "150", "--fecha", "2026-10-05");
  await cli("fijos", "agregar", "Alquiler", "1200", "alquiler", "efectivo");
  writeFileSync(servidor.archivoProductos, JSON.stringify([
    { id: 1, nombre: "Gasas", costo: 1, venta: 2, stock: 5, stock_minimo: 0 },
    { id: 2, nombre: "Alcohol", costo: 4, venta: 7, stock: 3, stock_minimo: 1 },
  ]));
  const destino = join(servidor.carpeta, "respaldos-caja");
  const { codigo, salida } = await cli("respaldar", destino);
  assert.equal(codigo, 0);
  const [lineaCaja, lineaCierres, lineaFijos, lineaProductos] = salida.split("\n");
  const fechaHora = String.raw`\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.json$`;
  assert.match(lineaCaja, new RegExp(String.raw`^Copia de seguridad guardada \(2 movimientos\): .*caja-${fechaHora}`));
  assert.match(lineaCierres, new RegExp(String.raw`^Copia de seguridad guardada \(1 cierre\): .*cierres-${fechaHora}`));
  assert.match(lineaFijos, new RegExp(String.raw`^Copia de seguridad guardada \(1 gasto fijo\): .*gastos-fijos-${fechaHora}`));
  assert.match(lineaProductos, new RegExp(String.raw`^Copia de seguridad guardada \(2 productos\): .*productos-${fechaHora}`));
  const archivos = readdirSync(destino).sort();
  assert.equal(archivos.length, 4);
  const leer = (nombre) => JSON.parse(readFileSync(join(destino, nombre), "utf-8"));
  assert.deepEqual(leer(archivos[0]).map((m) => m.fecha), ["2026-09-30", "2026-10-05"]); // caja-...
  assert.deepEqual(leer(archivos[1]).map((c) => c.fecha), ["2026-10-05"]); // cierres-...
  assert.deepEqual(leer(archivos[2]).map((g) => g.nombre), ["Alquiler"]); // gastos-fijos-...
  assert.deepEqual(leer(archivos[3]).map((p) => p.nombre), ["Alcohol", "Gasas"]); // productos-...
});

test("gastos fijos: agregar, ver pendientes y pagar", async () => {
  assert.match((await cli("fijos", "2026-10")).salida, /^No hay gastos fijos\. Agrega uno con:/);
  assert.equal((await cli("fijos", "agregar", "Alquiler", "1200", "alquiler", "efectivo", "--dia", "5")).salida,
    "Agregado: 1. Alquiler  S/ 1,200.00  alquiler · efectivo · vence el 5");
  await cli("fijos", "agregar", "Luz del consultorio", "80.50", "servicios", "yape");
  assert.equal((await cli("fijos", "2026-10")).salida, [
    "1. Alquiler  S/ 1,200.00  alquiler · efectivo · vence el 5  → pendiente",
    "2. Luz del consultorio  S/ 80.50  servicios · yape  → pendiente",
    "Por pagar en 2026-10: S/ 1,280.50 (2 de 2)",
  ].join("\n"));

  assert.equal((await cli("fijos", "pagar", "1", "--fecha", "2026-10-03", "--medio", "yape")).salida,
    "Pagado: 1. 2026-10-03  - S/ 1,200.00  alquiler · yape · Alquiler");
  assert.equal((await cli("fijos", "2026-10")).salida, [
    "1. Alquiler  S/ 1,200.00  alquiler · efectivo · vence el 5  → pagado el 2026-10-03",
    "2. Luz del consultorio  S/ 80.50  servicios · yape  → pendiente",
    "Por pagar en 2026-10: S/ 80.50 (1 de 2)",
  ].join("\n"));
  assert.equal((await cli("listar", "2026-10")).salida, "1. 2026-10-03  - S/ 1,200.00  alquiler · yape · Alquiler");

  await cli("fijos", "pagar", "2", "--fecha", "2026-10-20");
  assert.match((await cli("fijos", "2026-10")).salida, /\nTodo pagado en 2026-10\.$/);
  assert.match((await cli("fijos", "2026-11")).salida, /\nPor pagar en 2026-11: S\/ 1,280\.50 \(2 de 2\)$/);
});

test("gastos fijos: editar, eliminar y errores", async () => {
  await cli("fijos", "agregar", "Alquiler", "1200", "alquiler", "efectivo", "--dia", "5");
  assert.equal((await cli("fijos", "editar", "1", "monto=1300", "dia=")).salida,
    "Editado: 1. Alquiler  S/ 1,300.00  alquiler · efectivo");
  await cli("fijos", "pagar", "1", "--fecha", "2026-10-03");
  assert.equal((await cli("fijos", "pagar", "1", "--fecha", "2026-10-30")).error, "Error: Alquiler ya está pagado en 2026-10");
  assert.equal((await cli("fijos", "agregar", "Luz", "del", "consultorio", "80", "servicios", "yape")).error,
    'Error: No se entiende "servicios yape". Si el nombre tiene espacios, ponlo entre comillas: "Luz del consultorio"');
  assert.equal((await cli("fijos", "agregar", "Luz", "80", "consulta", "yape")).error,
    "Error: La categoría de un gasto debe ser una de: alquiler, insumos, compras, servicios, sueldos, otro");
  assert.equal((await cli("fijos", "agregar", "Luz", "80", "servicios", "yape", "--dia")).error,
    "Error: Falta el valor después de --dia (un número del 1 al 31)");
  assert.equal((await cli("fijos", "pagar", "9")).error, "Error: Gasto fijo no encontrado");

  assert.equal((await cli("fijos", "eliminar", "1")).salida,
    "Eliminado el gasto fijo 1. Los pagos ya registrados se conservan.");
  assert.equal((await cli("listar", "2026-10")).salida, "1. 2026-10-03  - S/ 1,300.00  alquiler · efectivo · Alquiler");
});

// El 2026-10-05: efectivo +80 −35.50 (esperado S/ 44.50) y Yape +150.
async function prepararDia() {
  await cli("registrar", "ingreso", "150", "consulta", "yape", "--fecha", "2026-10-05");
  await cli("registrar", "ingreso", "80", "certificado", "efectivo", "--fecha", "2026-10-05");
  await cli("registrar", "gasto", "35.50", "insumos", "efectivo", "--fecha", "2026-10-05");
}

test("cierre muestra lo que debería haber en un día abierto", async () => {
  await prepararDia();
  assert.equal((await cli("cierre", "2026-10-05")).salida, [
    "Cierre del 2026-10-05: abierto",
    "  Efectivo: ingresos S/ 80.00 · gastos S/ 35.50 · esperado S/ 44.50",
    "  Yape: ingresos S/ 150.00",
    "Para cerrarlo: node caja.js cerrar <efectivo_contado> <yape_segun_app> --fecha 2026-10-05",
  ].join("\n"));
  assert.match((await cli("cierre")).salida, /^Cierre del \d{4}-\d{2}-\d{2}: abierto/); // sin fecha = hoy
});

test("cerrar guarda las diferencias y la nota", async () => {
  await prepararDia();
  const { codigo, salida } = await cli("cerrar", "40", "170", "Di", "mal", "un", "vuelto", "--fecha", "2026-10-05");
  assert.equal(codigo, 0);
  const lineas = salida.split("\n");
  assert.match(lineas[0], /^Cierre del 2026-10-05: cerrado el \d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  assert.deepEqual(lineas.slice(1), [
    "  Efectivo: esperado S/ 44.50 · contado S/ 40.00 → faltan S/ 4.50",
    "  Yape: registrado S/ 150.00 · app S/ 170.00 → en la app hay S/ 20.00 sin registrar",
    "  Nota: Di mal un vuelto",
  ]);
  assert.equal((await cli("cierre", "2026-10-05")).salida, salida);
});

test("un día cerrado no admite cambios hasta reabrirlo", async () => {
  await prepararDia();
  await cli("cerrar", "44.50", "150", "--fecha", "2026-10-05");
  const bloqueado = "Error: El día 2026-10-05 está cerrado. Reábrelo para hacer cambios.";
  assert.equal((await cli("registrar", "ingreso", "10", "otro", "yape", "--fecha", "2026-10-05")).error, bloqueado);
  assert.equal((await cli("editar", "1", "monto=10")).error, bloqueado);
  assert.equal((await cli("eliminar", "1")).error, bloqueado);
  assert.equal((await cli("cerrar", "0", "0", "--fecha", "2026-10-05")).error,
    "Error: El día 2026-10-05 ya está cerrado. Reábrelo para cerrarlo de nuevo.");

  assert.equal((await cli("reabrir", "2026-10-05")).salida,
    "Reabierto el día 2026-10-05: ya puedes corregir sus movimientos y volver a cerrarlo.");
  assert.equal((await cli("editar", "1", "monto=10")).codigo, 0);
  assert.equal((await cli("reabrir", "2026-10-05")).error, "Error: El día 2026-10-05 no está cerrado");
  assert.equal((await cli("reabrir")).error, "Error: Indica el día a reabrir, por ejemplo: reabrir 2026-10-29");
});

test("cierres lista el historial del mes", async () => {
  await prepararDia();
  await cli("cerrar", "44.50", "150", "--fecha", "2026-10-05");
  await cli("cerrar", "10", "0", "--fecha", "2026-10-02");
  assert.equal((await cli("cierres", "2026-10")).salida, [
    "2026-10-02  efectivo: sobran S/ 10.00 · yape: cuadra",
    "2026-10-05  efectivo: cuadra · yape: cuadra",
  ].join("\n"));
  assert.equal((await cli("cierres", "2026-09")).salida, "No hay cierres en 2026-09.");
});

test("los errores del servidor se muestran y salen con código 1", async () => {
  assert.deepEqual(await cli("registrar", "ingreso", "150", "alquiler", "yape"), {
    codigo: 1, salida: "",
    error: "Error: La categoría de un ingreso debe ser una de: consulta, procedimiento, certificado, venta, otro",
  });
  assert.equal((await cli("registrar", "ingreso", "-5", "consulta", "yape")).error,
    "Error: El campo 'monto' debe ser mayor que 0 y como máximo 1000000");
  assert.equal((await cli("registrar", "gasto", "10", "insumos", "tarjeta")).error,
    "Error: El campo 'medio' debe ser uno de: efectivo, yape");
  assert.equal((await cli("registrar", "gasto", "10", "insumos", "yape", "--fecha")).error,
    "Error: Falta el valor después de --fecha (AAAA-MM-DD)");
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
