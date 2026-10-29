# ejemplo2 — Caja del consultorio

Ingresos y gastos del consultorio en soles, pagados en efectivo o Yape, con resumen mensual. Un servidor en **Python** y un cliente de línea de comandos en **Node.js**. Sin dependencias externas.

```
 node cliente/caja.js  ──HTTP/JSON──▶  python servidor/servidor.py  ──▶  movimientos.json
```

## Probarlo

En una terminal:

```bash
python servidor/servidor.py
```

Abre **http://127.0.0.1:8001** en el navegador para usar la página web, o en otra terminal usa el CLI:

```bash
node cliente/caja.js registrar ingreso 150 consulta yape "Control"
node cliente/caja.js registrar gasto 35.50 insumos efectivo --fecha 2026-10-05
node cliente/caja.js listar                   # mes actual; o: listar 2026-09
node cliente/caja.js resumen                  # totales del mes, por medio de pago y por categoría
node cliente/caja.js editar 2 monto=40 medio=yape   # cambia solo esos campos
node cliente/caja.js eliminar 2
```

En la página web, el botón **Editar** de cada movimiento lo carga en el formulario para corregirlo.

- Ingresos: `consulta`, `procedimiento`, `certificado`, `otro`
- Gastos: `alquiler`, `insumos`, `servicios`, `sueldos`, `otro`

No escribas nombres de pacientes en la descripción: la página no tiene contraseña.

## Cierre de caja

Al final del día cuentas el efectivo y miras en la app de Yape cuánto recibiste. Cada día empieza en S/ 0 de efectivo.

1. **Ver lo que debería haber:** en la página, la sección «Cierre del día», o `node cliente/caja.js cierre`.
2. **Cerrar:** escribes el efectivo contado y el total de Yape según la app, más una nota si quieres.
   ```bash
   node cliente/caja.js cerrar 190 150 "Di mal un vuelto"     # efectivo contado, Yape según la app, nota
   node cliente/caja.js cerrar 0 80 --fecha 2026-10-28        # cerrar un día anterior
   ```
   El cierre guarda las diferencias: en efectivo, si **faltan** o **sobran** soles; en Yape, si hay pagos en la app **sin registrar** o registros que no están en la app.
3. **Un día cerrado queda bloqueado:** no se pueden registrar, editar ni eliminar sus movimientos. Para corregir algo:
   ```bash
   node cliente/caja.js reabrir 2026-10-28     # luego corriges y vuelves a cerrar
   ```
4. **Historial:** `node cliente/caja.js cierres` (mes actual) o `cierres 2026-09`.

## Copia de seguridad

Los movimientos se guardan en `servidor/movimientos.json` y los cierres en `servidor/cierres.json` (ninguno se sube a git). Para copiarlos, con el servidor encendido:

```bash
node cliente/caja.js respaldar                # en respaldos/caja-... .json y respaldos/cierres-... .json
node cliente/caja.js respaldar E:\copias      # o en otra carpeta (USB, Google Drive...)
```

Para restaurar una copia, cópiala encima del archivo correspondiente en `servidor/` (`caja-...` → `movimientos.json`, `cierres-...` → `cierres.json`).

## Pruebas

```bash
cd servidor && python -m unittest -v
cd cliente && npm test        # levanta el servidor real: necesita python
```

GitHub Actions ejecuta ambas suites en cada push (`.github/workflows/pruebas.yml`).
