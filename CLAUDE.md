# ejemplo2 — Caja del consultorio (Python + Node.js)

Control de ingresos y gastos de un consultorio, en soles, pagados en efectivo o Yape, con resumen mensual. Proyecto de aprendizaje para practicar Claude Code; es pequeño a propósito. Nació en `ejemplo1` (lista de tareas) y usa la misma arquitectura.

## Arquitectura

- `servidor/servidor.py` — API HTTP en Python (solo librería estándar). Guarda en `servidor/movimientos.json` y `servidor/cierres.json` (fuera de git: son datos financieros reales).
- Cierre de caja: cada día empieza en S/ 0 de efectivo (el usuario se lleva todo). El cierre guarda una foto con las diferencias; un día cerrado bloquea sus movimientos (409) hasta reabrirlo.
- `servidor/web/index.html` — página web (HTML, CSS y JS en un archivo) que `servidor.py` sirve en `/` y usa la misma API.
- `cliente/caja.js` — CLI en Node.js que llama a la API con `fetch`; `cliente/api.js` tiene `pedir`, el manejo de errores y los respaldos.
- Montos sumados con `Decimal`. Las categorías están en `CATEGORIAS` de `servidor.py` y repetidas en `web/index.html`: si cambias una, cambia la otra.
- No guardar nombres de pacientes ni diagnósticos: la página no tiene contraseña.

## Comandos

| Tarea | Comando |
|---|---|
| Levantar servidor | `python servidor/servidor.py` (puerto 8001, para convivir con ejemplo1 en el 8000) |
| Usar el cliente | `node cliente/caja.js registrar ingreso\|gasto <monto> <categoria> efectivo\|yape ["..."] [--fecha AAAA-MM-DD]` · `listar [AAAA-MM]` · `resumen [AAAA-MM]` · `editar <id> campo=valor...` · `eliminar <id>` · `cierre [AAAA-MM-DD]` · `cerrar <efectivo_contado> <yape_segun_app> ["nota"] [--fecha AAAA-MM-DD]` · `reabrir <AAAA-MM-DD>` · `cierres [AAAA-MM]` · `respaldar [carpeta]` |
| Pruebas Python | `cd servidor && python -m unittest -v` |
| Pruebas Node | `cd cliente && npm test` (levantan el servidor real: necesitan `python`) |

Ambas suites de pruebas deben pasar antes de dar una tarea por terminada.

## Reglas

- Sin dependencias externas (ni pip ni npm) salvo que el usuario lo pida.
- Código, nombres y mensajes en español.
- El usuario está aprendiendo Claude Code: explica brevemente qué haces y por qué.
