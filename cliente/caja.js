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
// Gastos fijos (se pagan una vez al mes; "pagar" registra el gasto):
//   node caja.js fijos                    (pendientes y pagados del mes; o: fijos 2026-09)
//   node caja.js fijos agregar "Alquiler" 1200 alquiler efectivo --dia 5   (dia = vencimiento, opcional)
//   node caja.js fijos pagar 1            (hoy, con el medio de siempre)
//   node caja.js fijos pagar 1 --medio yape --fecha 2026-10-03
//   node caja.js fijos editar 1 monto=1300
//   node caja.js fijos eliminar 1         (los pagos ya hechos se conservan)
//
//   node caja.js respaldar          (copia en respaldos/ del proyecto)
//   node caja.js respaldar E:\copias      (o en la carpeta indicada)
//
// Categorías de ingreso: consulta, procedimiento, certificado, venta, otro
// Categorías de gasto:   alquiler, insumos, compras, servicios, sueldos, otro
// Medios de pago:        efectivo, yape

import {
  ejecutarComandos, formatearSoles, guardarRespaldo, leerCambios, mesActual, pedir, sacarOpcion,
} from "./api.js";

// Se exportan también desde aquí porque las pruebas y otros módulos ya los importaban de caja.js.
export { formatearSoles, leerCambios, mesActual, sacarOpcion };

export function formatearMovimiento(m) {
  const signo = m.tipo === "gasto" ? "-" : "+";
  const detalle = [m.categoria, m.medio, m.descripcion].filter(Boolean).join(" · ");
  return `${m.id}. ${m.fecha}  ${signo} ${formatearSoles(m.monto)}  ${detalle}`;
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

// "1. Alquiler  S/ 1,200.00  alquiler · efectivo · vence el 5  → pendiente"
// (la flecha solo aparece cuando viene el estado del mes)
export function formatearGastoFijo(g) {
  const detalle = [g.categoria, g.medio, g.dia ? `vence el ${g.dia}` : ""].filter(Boolean).join(" · ");
  const estado = g.pagado === undefined ? "" : g.pagado ? `  → pagado el ${g.movimiento.fecha}` : "  → pendiente";
  return `${g.id}. ${g.nombre}  ${formatearSoles(g.monto)}  ${detalle}${estado}`;
}

// Lista de gastos fijos del mes con lo que falta pagar al final.
export function formatearGastosFijosDelMes(gastos, mes) {
  const pendientes = gastos.filter((g) => !g.pagado);
  const total = pendientes.reduce((suma, g) => suma + Math.round(g.monto * 100), 0) / 100; // en céntimos: sin errores de redondeo
  const pie = pendientes.length
    ? `Por pagar en ${mes}: ${formatearSoles(total)} (${pendientes.length} de ${gastos.length})`
    : `Todo pagado en ${mes}.`;
  return [...gastos.map(formatearGastoFijo), pie].join("\n");
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
    const fecha = sacarOpcion(resto, "--fecha");
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
    const fecha = sacarOpcion(resto, "--fecha");
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
  async fijos(...args) {
    const [subcomando, ...resto] = args;
    if (Object.hasOwn(comandosFijos, subcomando)) return comandosFijos[subcomando](...resto);
    const mes = subcomando ?? mesActual();
    const gastos = await pedir("GET", `/gastos-fijos?mes=${encodeURIComponent(mes)}`);
    console.log(gastos.length
      ? formatearGastosFijosDelMes(gastos, mes)
      : 'No hay gastos fijos. Agrega uno con: node caja.js fijos agregar "Alquiler" 1200 alquiler efectivo --dia 5');
  },
  async respaldar(carpeta) {
    const archivos = [
      ["caja", "/movimientos?mes=todos", "movimiento", "movimientos"],
      ["cierres", "/cierres?mes=todos", "cierre", "cierres"],
      ["gastos-fijos", "/gastos-fijos?mes=todos", "gasto fijo", "gastos fijos"],
      ["productos", "/productos", "producto", "productos"],
    ];
    for (const [prefijo, ruta, singular, plural] of archivos) {
      const datos = await pedir("GET", ruta);
      const destino = await guardarRespaldo(prefijo, datos, carpeta);
      console.log(`Copia de seguridad guardada (${datos.length} ${datos.length === 1 ? singular : plural}): ${destino}`);
    }
  },
};

// Subcomandos de "fijos": node caja.js fijos <agregar|pagar|editar|eliminar> ...
const comandosFijos = {
  async agregar(nombre, monto, categoria, medio, ...resto) {
    const dia = sacarOpcion(resto, "--dia");
    if (resto.length) {
      throw new Error(`No se entiende "${resto.join(" ")}". Si el nombre tiene espacios, ponlo entre comillas: "Luz del consultorio"`);
    }
    const plantilla = await pedir("POST", "/gastos-fijos", { nombre, monto, categoria, medio, dia });
    console.log(`Agregado: ${formatearGastoFijo(plantilla)}`);
  },
  async pagar(id, ...resto) {
    const fecha = sacarOpcion(resto, "--fecha");
    const medio = sacarOpcion(resto, "--medio");
    const movimiento = await pedir("POST", `/gastos-fijos/${id}/pagar`, { fecha, medio });
    console.log(`Pagado: ${formatearMovimiento(movimiento)}`);
  },
  async editar(id, ...pares) {
    const plantilla = await pedir("PATCH", `/gastos-fijos/${id}`, leerCambios(pares));
    console.log(`Editado: ${formatearGastoFijo(plantilla)}`);
  },
  async eliminar(id) {
    await pedir("DELETE", `/gastos-fijos/${id}`);
    console.log(`Eliminado el gasto fijo ${id}. Los pagos ya registrados se conservan.`);
  },
};

// Solo se ejecuta si se llama directamente (no al importarlo desde las pruebas).
if (import.meta.main) {
  ejecutarComandos(comandos, "Uso: node caja.js <registrar ingreso|gasto <monto> <categoria> efectivo|yape [\"descripcion\"] [--fecha AAAA-MM-DD] | listar [AAAA-MM] | resumen [AAAA-MM] | editar <id> campo=valor... | eliminar <id> | cierre [AAAA-MM-DD] | cerrar <efectivo_contado> <yape_segun_app> [\"nota\"] [--fecha AAAA-MM-DD] | reabrir <AAAA-MM-DD> | cierres [AAAA-MM] | fijos [AAAA-MM] | fijos agregar \"nombre\" <monto> <categoria> efectivo|yape [--dia N] | fijos pagar <id> [--fecha AAAA-MM-DD] [--medio efectivo|yape] | fijos editar <id> campo=valor... | fijos eliminar <id> | respaldar [carpeta]>");
}
