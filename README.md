# ejemplo2 — Consultorio: Caja y Productos

App del consultorio en soles, con pagos en efectivo o Yape, organizada en **módulos**:

- **Caja:** ingresos y gastos, resumen mensual, cierre de caja diario y gastos fijos.
- **Productos:** catálogo con precio de costo y de venta, ganancia y stock. Al vender, el ingreso entra solo a la caja.

Un servidor en **Python** y clientes de línea de comandos en **Node.js**. Sin dependencias externas.

```
 node cliente/caja.js       ─┐                                  ┌─ caja.py       ─▶ movimientos, cierres, gastos fijos
                             ├─HTTP/JSON─▶ servidor/servidor.py ─┤
 node cliente/productos.js  ─┘   (y las páginas web)            └─ productos.py  ─▶ productos
```

## Probarlo

En una terminal:

```bash
python servidor/servidor.py
```

Abre **http://127.0.0.1:8001** en el navegador: el menú de arriba lleva a **Caja** y a **Productos** (`/inventario`). O, en otra terminal, usa el CLI:

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

## Gastos fijos

Gastos que se pagan una vez al mes (alquiler, luz, sueldos…). Los registras una sola vez y cada mes ves cuáles están **pendientes** y cuáles **pagados**. Al pagar uno, se registra el gasto con la fecha y el medio reales.

- **En la página:** sección «Gastos fijos de <mes>». «Administrar» para agregarlos o editarlos; «Pagar» en cada pendiente.
- **En la terminal:**
  ```bash
  node cliente/caja.js fijos agregar "Alquiler" 1200 alquiler efectivo --dia 5   # --dia: vencimiento (opcional)
  node cliente/caja.js fijos                      # pendientes y pagados del mes (o: fijos 2026-09)
  node cliente/caja.js fijos pagar 1              # hoy, con el medio de siempre
  node cliente/caja.js fijos pagar 1 --medio yape --fecha 2026-10-03
  node cliente/caja.js fijos editar 1 monto=1300  # solo afecta los pagos futuros
  node cliente/caja.js fijos eliminar 1           # los pagos ya hechos se conservan
  ```

Si eliminas el movimiento de un pago, ese gasto fijo vuelve a quedar pendiente.

## Productos

Cada producto tiene **precio de costo**, **precio de venta** y **stock**. La lista muestra la ganancia por unidad (en soles y en % del precio de venta) y avisa cuando el stock está bajo o agotado.

- **Vender:** registra el ingreso (categoría «venta») en la caja por `precio de venta × cantidad` y baja el stock. Si el día está cerrado, no se puede vender en esa fecha. Para anular una venta, elimínala en la caja: el stock vuelve.
- **Reponer:** sube el stock. Si indicas cómo pagaste, también registra el gasto (categoría «compras») en la caja por `precio de costo × cantidad`.
- Cambiar los precios solo afecta las ventas futuras.

En la página (menú **Productos**) hay botones **Vender**, **Reponer**, **Editar** y **Eliminar** en cada producto. En la terminal:

```bash
node cliente/productos.js agregar "Paracetamol 500 mg" 3.50 6 --stock 20 --minimo 5   # costo, venta
node cliente/productos.js listar
node cliente/productos.js vender 1 3 --medio yape          # 3 unidades
node cliente/productos.js reponer 1 10 --pagado efectivo   # 10 unidades, registrando el gasto
node cliente/productos.js editar 1 venta=6.50
node cliente/productos.js eliminar 1                       # sus ventas siguen en la caja
```

## Copia de seguridad

Los movimientos se guardan en `servidor/movimientos.json`, los cierres en `servidor/cierres.json`, los gastos fijos en `servidor/gastos_fijos.json` y los productos en `servidor/productos.json` (ninguno se sube a git). Para copiarlos todos, con el servidor encendido:

```bash
node cliente/caja.js respaldar                # en respaldos/: caja-..., cierres-..., gastos-fijos-... y productos-... .json
node cliente/caja.js respaldar E:\copias      # o en otra carpeta (USB, Google Drive...)
```

Para restaurar una copia, cópiala encima del archivo correspondiente en `servidor/` (`caja-...` → `movimientos.json`, `cierres-...` → `cierres.json`, `gastos-fijos-...` → `gastos_fijos.json`, `productos-...` → `productos.json`).

## Pruebas

```bash
cd servidor && python -m unittest -v
cd cliente && npm test        # levanta el servidor real: necesita python
```

GitHub Actions ejecuta ambas suites en cada push (`.github/workflows/pruebas.yml`).
