// Ayuda para las pruebas de punta a punta: levanta el servidor Python real
// (puerto libre y archivos temporales) y ejecuta un CLI como lo haría una persona.
// No termina en .test.js, así que `node --test` no lo ejecuta como prueba.

import { execFile, spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

export const ejecutar = promisify(execFile);
const PYTHON = process.env.PYTHON ?? "python";
const RUTA_SERVIDOR = fileURLToPath(new URL("../servidor/servidor.py", import.meta.url));

// Arranca el servidor y espera a que anuncie en qué puerto escucha.
export function levantarServidor() {
  const carpeta = mkdtempSync(join(tmpdir(), "caja-"));
  const archivoCaja = join(carpeta, "movimientos.json");
  const archivoCierres = join(carpeta, "cierres.json");
  const archivoGastosFijos = join(carpeta, "gastos_fijos.json");
  const archivoProductos = join(carpeta, "productos.json");
  return new Promise((resolver, rechazar) => {
    const proceso = spawn(PYTHON, ["-u", RUTA_SERVIDOR], {
      env: {
        ...process.env, CAJA_PUERTO: "0", CAJA_ARCHIVO: archivoCaja, CIERRES_ARCHIVO: archivoCierres,
        GASTOS_FIJOS_ARCHIVO: archivoGastosFijos, PRODUCTOS_ARCHIVO: archivoProductos,
      },
    });
    const detener = () => {
      proceso.kill();
      rmSync(carpeta, { recursive: true, force: true });
    };
    let salida = "";
    proceso.stdout.on("data", (trozo) => {
      salida += trozo;
      const encontrado = salida.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (encontrado) {
        resolver({ url: encontrado[0], carpeta, archivoCaja, archivoCierres, archivoGastosFijos, archivoProductos, detener });
      }
    });
    proceso.on("error", rechazar);
    proceso.on("exit", (codigo) => rechazar(new Error(`El servidor terminó (código ${codigo}): ${salida}`)));
  });
}

// Devuelve una función que ejecuta el CLI dado contra la url y da su código de salida,
// lo que imprimió y los errores.
export function crearCli(rutaCli, url) {
  return async (...args) => {
    const opciones = { env: { ...process.env, CAJA_URL: url } };
    try {
      const { stdout } = await ejecutar(process.execPath, [rutaCli, ...args], opciones);
      return { codigo: 0, salida: stdout.trim(), error: "" };
    } catch (fallo) {
      return { codigo: fallo.code, salida: fallo.stdout.trim(), error: fallo.stderr.trim() };
    }
  };
}

// Pide al sistema un puerto libre y lo suelta: ahí no escucha nadie.
export function puertoSinServidor() {
  return new Promise((resolver) => {
    const temporal = createServer().listen(0, "127.0.0.1", () => {
      const { port } = temporal.address();
      temporal.close(() => resolver(port));
    });
  });
}
