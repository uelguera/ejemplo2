// Lo que necesita el CLI de la caja: la conexión con el servidor,
// la ejecución de comandos con sus errores y las copias de seguridad.

import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const URL_BASE = process.env.CAJA_URL ?? "http://127.0.0.1:8001";
const CARPETA_RESPALDOS = fileURLToPath(new URL("../respaldos/", import.meta.url));

export async function pedir(metodo, ruta, cuerpo) {
  const respuesta = await fetch(URL_BASE + ruta, {
    method: metodo,
    headers: { "Content-Type": "application/json" },
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  const texto = await respuesta.text();
  const datos = texto ? JSON.parse(texto) : null;
  if (!respuesta.ok) {
    throw new Error(datos?.error ?? `Error HTTP ${respuesta.status}`);
  }
  return datos;
}

// Nombre con fecha y hora local, p. ej. caja-2026-10-28_16-30-05.json
export function nombreRespaldo(prefijo, fecha = new Date()) {
  const dos = (numero) => String(numero).padStart(2, "0");
  const dia = `${fecha.getFullYear()}-${dos(fecha.getMonth() + 1)}-${dos(fecha.getDate())}`;
  const hora = `${dos(fecha.getHours())}-${dos(fecha.getMinutes())}-${dos(fecha.getSeconds())}`;
  return `${prefijo}-${dia}_${hora}.json`;
}

// Guarda los datos en un archivo nuevo de la carpeta (por defecto respaldos/ del proyecto) y devuelve su ruta.
export async function guardarRespaldo(prefijo, datos, carpeta = CARPETA_RESPALDOS) {
  await mkdir(carpeta, { recursive: true });
  const ruta = resolve(carpeta, nombreRespaldo(prefijo));
  await writeFile(ruta, JSON.stringify(datos, null, 2) + "\n", "utf-8");
  return ruta;
}

// Ejecuta el comando pedido en la terminal; si no existe muestra el uso, y si falla, el error.
export async function ejecutarComandos(comandos, uso) {
  const [comando, ...args] = process.argv.slice(2);
  const accion = Object.hasOwn(comandos, comando) ? comandos[comando] : undefined;
  if (!accion) {
    console.log(uso);
    process.exitCode = 1;
    return;
  }
  try {
    await accion(...args);
  } catch (error) {
    const mensaje = error.cause?.code === "ECONNREFUSED"
      ? `No se pudo conectar a ${URL_BASE}. ¿Está corriendo el servidor? (python servidor/servidor.py)`
      : error.message;
    console.error(`Error: ${mensaje}`);
    process.exitCode = 1;
  }
}

// ---- Formato y lectura de argumentos, compartidos por los CLI de caja y productos ----

const SOLES = new Intl.NumberFormat("es-PE", { style: "currency", currency: "PEN" });

// "S/ 1,234.50", con espacio normal (Intl usa uno de no separación que se ve raro al copiar).
export function formatearSoles(monto) {
  return SOLES.format(monto).replace(/\u00a0/g, " ");
}

// Mes actual en hora local, p. ej. 2026-10
export function mesActual(fecha = new Date()) {
  return `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, "0")}`;
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

const EJEMPLOS_OPCIONES = {
  "--fecha": "AAAA-MM-DD", "--dia": "un número del 1 al 31", "--medio": "efectivo o yape",
  "--pagado": "efectivo o yape", "--stock": "unidades", "--minimo": "unidades",
};

// Saca "--opcion valor" de los argumentos (los modifica) y devuelve el valor, o undefined si no está.
export function sacarOpcion(args, opcion) {
  const posicion = args.indexOf(opcion);
  if (posicion === -1) return undefined;
  const valor = args[posicion + 1];
  if (!valor) throw new Error(`Falta el valor después de ${opcion} (${EJEMPLOS_OPCIONES[opcion]})`);
  args.splice(posicion, 2);
  return valor;
}
