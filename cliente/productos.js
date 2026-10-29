#!/usr/bin/env node
// Cliente de línea de comandos para los productos del consultorio (precio de costo y de venta, stock).
// Al vender, el ingreso se registra en la caja; al reponer con --pagado, también el gasto.
//
// Uso:
//   node productos.js listar
//   node productos.js agregar "Paracetamol 500 mg" 3.50 6 --stock 20 --minimo 5   (costo, venta)
//   node productos.js editar 1 venta=6.50 stock_minimo=10
//   node productos.js eliminar 1          (las ventas ya registradas siguen en la caja)
//   node productos.js vender 1            (1 unidad, en efectivo, hoy)
//   node productos.js vender 1 3 --medio yape --fecha 2026-10-05
//   node productos.js reponer 1 10        (solo sube el stock)
//   node productos.js reponer 1 10 --pagado efectivo   (y registra el gasto "compras" en la caja)

import { ejecutarComandos, formatearSoles, leerCambios, pedir, sacarOpcion } from "./api.js";

const enCentimos = (monto) => Math.round(monto * 100); // para sumar y multiplicar sin errores de redondeo

export function describirStock(p) {
  if (p.estado_stock === "agotado") return "agotado";
  if (p.estado_stock === "bajo") return `quedan ${p.stock} (stock bajo)`;
  return `${p.stock} en stock`;
}

// "1. Paracetamol  costo S/ 3.50 · venta S/ 6.00 · ganancia S/ 2.50 (41.7%)  → 20 en stock"
export function formatearProducto(p) {
  const precios = `costo ${formatearSoles(p.costo)} · venta ${formatearSoles(p.venta)} · ganancia ${formatearSoles(p.ganancia)} (${p.margen}%)`;
  return `${p.id}. ${p.nombre}  ${precios}  → ${describirStock(p)}`;
}

// El catálogo con el valor del stock a precio de costo y cuántos hay que reponer.
export function formatearCatalogo(productos) {
  const valor = productos.reduce((suma, p) => suma + enCentimos(p.costo) * p.stock, 0) / 100;
  const porReponer = productos.filter((p) => p.estado_stock !== "ok").length;
  return [
    ...productos.map(formatearProducto),
    `Valor del stock (a costo): ${formatearSoles(valor)} · por reponer: ${porReponer}`,
  ].join("\n");
}

// Error si quedaron argumentos que no se usaron (p. ej. un nombre con espacios sin comillas).
function sinSobrantes(resto, ejemplo) {
  if (resto.length) throw new Error(`No se entiende "${resto.join(" ")}". ${ejemplo}`);
}

const comandos = {
  async listar() {
    const productos = await pedir("GET", "/productos");
    console.log(productos.length
      ? formatearCatalogo(productos)
      : 'No hay productos. Agrega uno con: node productos.js agregar "Paracetamol 500 mg" 3.50 6 --stock 20 --minimo 5');
  },
  async agregar(nombre, costo, venta, ...resto) {
    const stock = sacarOpcion(resto, "--stock");
    const stockMinimo = sacarOpcion(resto, "--minimo");
    sinSobrantes(resto, 'Si el nombre tiene espacios, ponlo entre comillas: "Paracetamol 500 mg"');
    const producto = await pedir("POST", "/productos", { nombre, costo, venta, stock, stock_minimo: stockMinimo });
    console.log(`Agregado: ${formatearProducto(producto)}`);
  },
  async editar(id, ...pares) {
    const producto = await pedir("PATCH", `/productos/${id}`, leerCambios(pares));
    console.log(`Editado: ${formatearProducto(producto)}`);
  },
  async eliminar(id) {
    await pedir("DELETE", `/productos/${id}`);
    console.log(`Eliminado el producto ${id}. Sus ventas ya registradas siguen en la caja.`);
  },
  async vender(id, ...resto) {
    const medio = sacarOpcion(resto, "--medio");
    const fecha = sacarOpcion(resto, "--fecha");
    const [cantidad, ...sobrantes] = resto;
    sinSobrantes(sobrantes, "Uso: vender <id> [cantidad] [--medio efectivo|yape] [--fecha AAAA-MM-DD]");
    const { movimiento, producto } = await pedir("POST", `/productos/${id}/vender`, { cantidad, medio, fecha });
    console.log(`Vendido: ${movimiento.descripcion} por ${formatearSoles(movimiento.monto)} (${movimiento.medio}), `
      + `registrado en la caja. Ahora: ${describirStock(producto)}.`);
  },
  async reponer(id, cantidad, ...resto) {
    const pagadoCon = sacarOpcion(resto, "--pagado");
    const fecha = sacarOpcion(resto, "--fecha");
    sinSobrantes(resto, "Uso: reponer <id> <cantidad> [--pagado efectivo|yape] [--fecha AAAA-MM-DD]");
    const { movimiento, producto } = await pedir("POST", `/productos/${id}/reponer`,
      { cantidad, pagado_con: pagadoCon, fecha });
    const gasto = movimiento
      ? ` Gasto de ${formatearSoles(movimiento.monto)} (${movimiento.medio}) registrado en la caja.`
      : "";
    console.log(`Repuesto: ${producto.nombre}, ahora hay ${producto.stock}.${gasto}`);
  },
};

// Solo se ejecuta si se llama directamente (no al importarlo desde las pruebas).
if (import.meta.main) {
  ejecutarComandos(comandos, "Uso: node productos.js <listar | agregar \"nombre\" <costo> <venta> [--stock N] [--minimo N] | editar <id> campo=valor... | eliminar <id> | vender <id> [cantidad] [--medio efectivo|yape] [--fecha AAAA-MM-DD] | reponer <id> <cantidad> [--pagado efectivo|yape] [--fecha AAAA-MM-DD]>");
}
