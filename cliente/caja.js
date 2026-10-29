#!/usr/bin/env node
// Cliente de línea de comandos para la caja del consultorio (ingresos y gastos en soles).
//
// Uso:
//   node caja.js registrar ingreso 150 consulta yape "Control"
//   node caja.js registrar gasto 35.50 insumos efectivo --fecha 2026-10-05
//   node caja.js listar                   (mes actual)
//   node caja.js listar 2026-09
//   node caja.js resumen                  (mes actual; o: resumen 2026-09)
//   node caja.js eliminar 3
//   node caja.js respaldar                (copia en respaldos/ del proyecto)
//   node caja.js respaldar E:\copias      (o en la carpeta indicada)
//
// Categorías de ingreso: consulta, procedimiento, certificado, otro
// Categorías de gasto:   alquiler, insumos, servicios, sueldos, otro
// Medios de pago:        efectivo, yape

import { ejecutarComandos, guardarRespaldo, pedir } from "./api.js";

const SOLES = new Intl.NumberFormat("es-PE", { style: "currency", currency: "PEN" });

// "S/ 1,234.50", con espacio normal (Intl usa uno de no separación que se ve raro al copiar).
export function formatearSoles(monto) {
  return SOLES.format(monto).replace(/\u00a0/g, " ");
}

export function formatearMovimiento(m) {
  const signo = m.tipo === "gasto" ? "-" : "+";
  const detalle = [m.categoria, m.medio, m.descripcion].filter(Boolean).join(" · ");
  return `${m.id}. ${m.fecha}  ${signo} ${formatearSoles(m.monto)}  ${detalle}`;
}

// Mes actual en hora local, p. ej. 2026-10
export function mesActual(fecha = new Date()) {
  return `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, "0")}`;
}

export function formatearResumen(r) {
  const cuentas = (t) => `ingresos ${formatearSoles(t.ingresos)} · gastos ${formatearSoles(t.gastos)} · saldo ${formatearSoles(t.saldo)}`;
  const categorias = (titulo, montos) => {
    const filas = Object.entries(montos).map(([categoria, monto]) => `  ${categoria}: ${formatearSoles(monto)}`);
    return filas.length ? [titulo, ...filas] : [];
  };
  return [
    `Resumen de ${r.mes}`,
    `  Ingresos: ${formatearSoles(r.ingresos)}`,
    `  Gastos:   ${formatearSoles(r.gastos)}`,
    `  Saldo:    ${formatearSoles(r.saldo)}`,
    "Por medio de pago:",
    ...Object.entries(r.por_medio).map(([medio, t]) => `  ${medio}: ${cuentas(t)}`),
    ...categorias("Ingresos por categoría:", r.por_categoria.ingresos),
    ...categorias("Gastos por categoría:", r.por_categoria.gastos),
  ].join("\n");
}

const comandos = {
  async registrar(tipo, monto, categoria, medio, ...resto) {
    let fecha;
    const posicion = resto.indexOf("--fecha");
    if (posicion !== -1) {
      fecha = resto[posicion + 1];
      if (!fecha) throw new Error("Falta la fecha después de --fecha (AAAA-MM-DD)");
      resto.splice(posicion, 2);
    }
    const movimiento = await pedir("POST", "/movimientos", {
      tipo, monto, categoria, medio, fecha, descripcion: resto.join(" "),
    });
    console.log(`Registrado: ${formatearMovimiento(movimiento)}`);
  },
  async listar(mes = mesActual()) {
    const movimientos = await pedir("GET", `/movimientos?mes=${encodeURIComponent(mes)}`);
    console.log(movimientos.length ? movimientos.map(formatearMovimiento).join("\n") : `No hay movimientos en ${mes}.`);
  },
  async resumen(mes = mesActual()) {
    console.log(formatearResumen(await pedir("GET", `/resumen?mes=${encodeURIComponent(mes)}`)));
  },
  async eliminar(id) {
    await pedir("DELETE", `/movimientos/${id}`);
    console.log(`Eliminado el movimiento ${id}.`);
  },
  async respaldar(carpeta) {
    const movimientos = await pedir("GET", "/movimientos?mes=todos");
    const ruta = await guardarRespaldo("caja", movimientos, carpeta);
    const cantidad = `${movimientos.length} ${movimientos.length === 1 ? "movimiento" : "movimientos"}`;
    console.log(`Copia de seguridad guardada (${cantidad}): ${ruta}`);
  },
};

// Solo se ejecuta si se llama directamente (no al importarlo desde las pruebas).
if (import.meta.main) {
  ejecutarComandos(comandos, "Uso: node caja.js <registrar ingreso|gasto <monto> <categoria> efectivo|yape [\"descripcion\"] [--fecha AAAA-MM-DD] | listar [AAAA-MM] | resumen [AAAA-MM] | eliminar <id> | respaldar [carpeta]>");
}
