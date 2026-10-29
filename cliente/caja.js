#!/usr/bin/env node
// Cliente de línea de comandos para la caja del consultorio (ingresos y gastos en soles).
//
// Uso:
//   node caja.js registrar ingreso 150 consulta yape "Control"
//   node caja.js registrar gasto 35.50 insumos efectivo --fecha 2026-10-05
//   node caja.js listar                   (mes actual)
//   node caja.js listar 2026-09
//   node caja.js resumen                  (mes actual; o: resumen 2026-09)
//   node caja.js editar 3 monto=40 medio=yape   (solo los campos que cambian)
//   node caja.js editar 3 descripcion="Guantes y gasas"
//   node caja.js eliminar 3
//
// Cierre de caja (cada día empieza en S/ 0 de efectivo; un día cerrado no admite cambios):
//   node caja.js cierre                   (hoy: lo que debería haber; o: cierre 2026-10-28)
//   node caja.js cerrar 190 150 "Di mal un vuelto"   (efectivo contado, total recibido según la app de Yape, nota)
//   node caja.js cerrar 0 80 --fecha 2026-10-28
//   node caja.js reabrir 2026-10-28       (para corregir movimientos de un día cerrado)
//   node caja.js cierres                  (historial del mes; o: cierres 2026-09)
//
//   node caja.js respaldar            (copia en respaldos/ del proyecto)
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

// ["monto=40", "descripcion=Guantes y gasas"] -> { monto: "40", descripcion: "Guantes y gasas" }
// Qué campos existen lo valida el servidor.
export function leerCambios(pares) {
  if (!pares.length) throw new Error("Indica qué cambiar, por ejemplo: editar 3 monto=40 medio=yape");
  const cambios = {};
  for (const par of pares) {
    const igual = par.indexOf("=");
    if (igual < 1) throw new Error(`"${par}" no tiene la forma campo=valor (por ejemplo monto=40)`);
    cambios[par.slice(0, igual)] = par.slice(igual + 1);
  }
  return cambios;
}

// Saca "--fecha AAAA-MM-DD" de los argumentos (los modifica) y devuelve la fecha, o undefined si no está.
export function sacarFecha(args) {
  const posicion = args.indexOf("--fecha");
  if (posicion === -1) return undefined;
  const fecha = args[posicion + 1];
  if (!fecha) throw new Error("Falta la fecha después de --fecha (AAAA-MM-DD)");
  args.splice(posicion, 2);
  return fecha;
}

// Diferencia = lo contado (o lo que dice la app) − lo registrado.
export function describirDiferencia(diferencia, medio = "efectivo") {
  if (diferencia === 0) return "cuadra";
  const monto = formatearSoles(Math.abs(diferencia));
  if (medio === "yape") {
    return diferencia > 0 ? `en la app hay ${monto} sin registrar` : `${monto} registrados que no están en la app`;
  }
  return diferencia > 0 ? `sobran ${monto}` : `faltan ${monto}`;
}

export function formatearCierre(c) {
  if (!c.cerrado) {
    return [
      `Cierre del ${c.fecha}: abierto`,
      `  Efectivo: ingresos ${formatearSoles(c.efectivo.ingresos)} · gastos ${formatearSoles(c.efectivo.gastos)} · esperado ${formatearSoles(c.efectivo.esperado)}`,
      `  Yape: ingresos ${formatearSoles(c.yape.ingresos)}`,
      `Para cerrarlo: node caja.js cerrar <efectivo_contado> <yape_segun_app> --fecha ${c.fecha}`,
    ].join("\n");
  }
  return [
    `Cierre del ${c.fecha}: cerrado el ${c.cerrado_en.replace("T", " ").slice(0, 16)}`,
    `  Efectivo: esperado ${formatearSoles(c.efectivo.esperado)} · contado ${formatearSoles(c.efectivo.contado)} → ${describirDiferencia(c.efectivo.diferencia)}`,
    `  Yape: registrado ${formatearSoles(c.yape.ingresos)} · app ${formatearSoles(c.yape.app)} → ${describirDiferencia(c.yape.diferencia, "yape")}`,
    ...(c.nota ? [`  Nota: ${c.nota}`] : []),
  ].join("\n");
}

// Una línea por cierre, para el historial del mes.
export function formatearLineaCierre(c) {
  return `${c.fecha}  efectivo: ${describirDiferencia(c.efectivo.diferencia)} · yape: ${describirDiferencia(c.yape.diferencia, "yape")}`;
}

const comandos = {
  async registrar(tipo, monto, categoria, medio, ...resto) {
    const fecha = sacarFecha(resto);
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
  async editar(id, ...pares) {
    const movimiento = await pedir("PATCH", `/movimientos/${id}`, leerCambios(pares));
    console.log(`Editado: ${formatearMovimiento(movimiento)}`);
  },
  async eliminar(id) {
    await pedir("DELETE", `/movimientos/${id}`);
    console.log(`Eliminado el movimiento ${id}.`);
  },
  async cierre(fecha) {
    const ruta = fecha ? `/cierre?fecha=${encodeURIComponent(fecha)}` : "/cierre";
    console.log(formatearCierre(await pedir("GET", ruta)));
  },
  async cerrar(efectivoContado, yapeApp, ...resto) {
    const fecha = sacarFecha(resto);
    const cierre = await pedir("POST", "/cierres", {
      fecha, efectivo_contado: efectivoContado, yape_app: yapeApp, nota: resto.join(" "),
    });
    console.log(formatearCierre(cierre));
  },
  async reabrir(fecha) {
    if (!fecha) throw new Error("Indica el día a reabrir, por ejemplo: reabrir 2026-10-29");
    await pedir("DELETE", `/cierres/${encodeURIComponent(fecha)}`);
    console.log(`Reabierto el día ${fecha}: ya puedes corregir sus movimientos y volver a cerrarlo.`);
  },
  async cierres(mes = mesActual()) {
    const cierres = await pedir("GET", `/cierres?mes=${encodeURIComponent(mes)}`);
    console.log(cierres.length ? cierres.map(formatearLineaCierre).join("\n") : `No hay cierres en ${mes}.`);
  },
  async respaldar(carpeta) {
    const movimientos = await pedir("GET", "/movimientos?mes=todos");
    const cierres = await pedir("GET", "/cierres?mes=todos");
    const rutaMovimientos = await guardarRespaldo("caja", movimientos, carpeta);
    const rutaCierres = await guardarRespaldo("cierres", cierres, carpeta);
    const cantidad = (n, singular, plural) => `${n} ${n === 1 ? singular : plural}`;
    console.log(`Copia de seguridad guardada (${cantidad(movimientos.length, "movimiento", "movimientos")}): ${rutaMovimientos}`);
    console.log(`Copia de seguridad guardada (${cantidad(cierres.length, "cierre", "cierres")}): ${rutaCierres}`);
  },
};

// Solo se ejecuta si se llama directamente (no al importarlo desde las pruebas).
if (import.meta.main) {
  ejecutarComandos(comandos, "Uso: node caja.js <registrar ingreso|gasto <monto> <categoria> efectivo|yape [\"descripcion\"] [--fecha AAAA-MM-DD] | listar [AAAA-MM] | resumen [AAAA-MM] | editar <id> campo=valor... | eliminar <id> | cierre [AAAA-MM-DD] | cerrar <efectivo_contado> <yape_segun_app> [\"nota\"] [--fecha AAAA-MM-DD] | reabrir <AAAA-MM-DD> | cierres [AAAA-MM] | respaldar [carpeta]>");
}
