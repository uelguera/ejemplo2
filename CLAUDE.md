# ejemplo2 — Consultorio: módulos Caja y Productos (Python + Node.js)

App para un consultorio, en soles, pagos en efectivo o Yape. Proyecto de aprendizaje para practicar Claude Code; es pequeño a propósito. Nació en `ejemplo1` (lista de tareas) y usa la misma arquitectura.

## Arquitectura (por módulos)

- `servidor/servidor.py` — solo HTTP (librería estándar): sirve las páginas y pasa cada petición a los módulos hasta que uno la atiende. Lee las variables de entorno de los archivos de datos.
- `servidor/comun.py` — lo compartido: `Peticion`, `ArchivoJson`/`ConIds`, `leer_soles`/`leer_entero`, fechas, `CATEGORIAS`, `MEDIOS`.
- `servidor/caja.py` — **módulo Caja** (`ModuloCaja`): movimientos, resumen, cierre diario, gastos fijos.
- `servidor/productos.py` — **módulo Productos** (`ModuloProductos`): catálogo con costo, venta y stock. Vender y reponer registran movimientos a través de `ModuloCaja.registrar` (así respetan los días cerrados); al eliminar en la caja una venta, el stock vuelve (gancho `al_eliminar_movimiento`).
- **Agregar un módulo:** una clase con `atender(peticion) -> (estado, cuerpo) | None` en su propio archivo, añadida a la lista `modulos` de `crear_manejador()`; su página en `ARCHIVOS_WEB` y un enlace en el menú de cada página.
- Las páginas no comparten ruta con la API: `/productos` es la API y `/inventario` la página de productos.
- Datos (fuera de git, son datos reales): `servidor/movimientos.json`, `cierres.json`, `gastos_fijos.json`, `productos.json`.
- Gastos fijos: "Pagar" crea un movimiento con `gasto_fijo: <id>`; está pagado en un mes si existe ese movimiento. Ventas y compras de productos llevan `producto` y `cantidad`. Al editar un movimiento se conservan esos vínculos (`VINCULOS` en `caja.py`).
- Cierre de caja: cada día empieza en S/ 0 de efectivo (el usuario se lleva todo). Un día cerrado bloquea sus movimientos (409) hasta reabrirlo.
- Web: `servidor/web/caja.html` (en `/` y `/caja`), `productos.html` (en `/inventario`), y lo compartido en `comun.css` y `comun.js`. Las categorías están en `comun.py` y repetidas en `comun.js`: si cambias una, cambia la otra.
- CLI: `cliente/caja.js` y `cliente/productos.js`; lo común (`pedir`, errores, respaldos, formato de soles, `--opciones`) en `cliente/api.js`.
- Montos con `Decimal` en el servidor y en céntimos en JS. No guardar nombres de pacientes ni diagnósticos: la página no tiene contraseña.

## Comandos

| Tarea | Comando |
|---|---|
| Levantar servidor | `python servidor/servidor.py` (puerto 8001, para convivir con ejemplo1 en el 8000) |
| Caja | `node cliente/caja.js registrar ingreso\|gasto <monto> <categoria> efectivo\|yape ["..."] [--fecha AAAA-MM-DD]` · `listar [AAAA-MM]` · `resumen [AAAA-MM]` · `editar <id> campo=valor...` · `eliminar <id>` · `cierre [AAAA-MM-DD]` · `cerrar <efectivo_contado> <yape_segun_app> ["nota"] [--fecha AAAA-MM-DD]` · `reabrir <AAAA-MM-DD>` · `cierres [AAAA-MM]` · `fijos [AAAA-MM]` · `fijos agregar "nombre" <monto> <categoria> <medio> [--dia N]` · `fijos pagar <id> [--fecha] [--medio]` · `fijos editar <id> campo=valor...` · `fijos eliminar <id>` · `respaldar [carpeta]` (respalda todos los módulos) |
| Productos | `node cliente/productos.js listar` · `agregar "nombre" <costo> <venta> [--stock N] [--minimo N]` · `editar <id> campo=valor...` · `eliminar <id>` · `vender <id> [cantidad] [--medio] [--fecha]` · `reponer <id> <cantidad> [--pagado efectivo\|yape] [--fecha]` |
| Pruebas Python | `cd servidor && python -m unittest -v` |
| Pruebas Node | `cd cliente && npm test` (levantan el servidor real: necesitan `python`) |

Ambas suites de pruebas deben pasar antes de dar una tarea por terminada.

## Reglas

- Sin dependencias externas (ni pip ni npm) salvo que el usuario lo pida.
- Código, nombres y mensajes en español.
- El usuario está aprendiendo Claude Code: explica brevemente qué haces y por qué.
