// Funciones comunes de las páginas del consultorio (caja.html, productos.html).
// Se carga antes del script de cada página: lo que se declara aquí se usa allí.

// Las mismas listas que CATEGORIAS y MEDIOS en servidor/comun.py: si cambias una, cambia la otra.
const CATEGORIAS = {
  ingreso: ["consulta", "procedimiento", "certificado", "venta", "otro"],
  gasto: ["alquiler", "insumos", "compras", "servicios", "sueldos", "otro"],
};
const MEDIOS = ["efectivo", "yape"];

const soles = new Intl.NumberFormat("es-PE", { style: "currency", currency: "PEN" });
const $ = (id) => document.getElementById(id);
const hoy = () => new Date().toLocaleDateString("en-CA"); // AAAA-MM-DD en hora local
const mayuscula = (texto) => texto.charAt(0).toUpperCase() + texto.slice(1);

async function pedir(metodo, ruta, cuerpo) {
  let respuesta;
  try {
    respuesta = await fetch(ruta, {
      method: metodo,
      headers: { "Content-Type": "application/json" },
      body: cuerpo ? JSON.stringify(cuerpo) : undefined,
    });
  } catch {
    throw new Error("No se pudo conectar con el servidor. ¿Está corriendo? (python servidor/servidor.py)");
  }
  const texto = await respuesta.text();
  const datos = texto ? JSON.parse(texto) : null;
  if (!respuesta.ok) {
    throw new Error(datos?.error ?? `Error HTTP ${respuesta.status}`);
  }
  return datos;
}

// Devuelve accion(cambio, destino): ejecuta un cambio, muestra el error (en el párrafo "destino", o el
// primero de la lista) si lo hay, y siempre vuelve a cargar la página con cargar().
function crearAccion(cargar, parrafosDeError) {
  return async function accion(cambio, destino = parrafosDeError[0]) {
    for (const parrafo of parrafosDeError) parrafo.textContent = "";
    try { await cambio(); } catch (e) { destino.textContent = e.message; }
    try { await cargar(); } catch (e) { destino.textContent = e.message; }
  };
}

function boton(texto, alPulsar, clase = "") {
  const elemento = document.createElement("button");
  elemento.type = "button";
  elemento.textContent = texto;
  if (clase) elemento.className = clase;
  elemento.addEventListener("click", alPulsar);
  return elemento;
}

// Elemento con texto (nunca se interpreta como HTML) y clase opcional.
function elemento(etiqueta, texto = "", clase = "") {
  const nuevo = document.createElement(etiqueta);
  nuevo.textContent = texto;
  if (clase) nuevo.className = clase;
  return nuevo;
}
