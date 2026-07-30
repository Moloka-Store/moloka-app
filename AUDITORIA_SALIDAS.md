# AUDITORÍA — LAS SALIDAS DE INVENTARIO (v1)

*29-jul-2026. Lectura + medida. Cero escrituras. Producción (`ogfbjjdxcltzpygzuyla`) leída en SOLO LECTURA.*
*Estado auditado: `origin/main` del worktree `moloka_app-audit-salidas` (PR #69 **sin fusionar** → la función de envíos todavía se llama `actualizarReparto`). Es lo que Elena usa HOY.*

Marcas: 🔬 **MEDIDO** (BD / ejecución) · 📖 **LEÍDO** (código, con línea).

---

## 0. LO URGENTE

**Hay UN bug vivo que afecta a Elena hoy, y ya está siendo arreglado por el PR #69. No lo toco.**

### 0.1 El reparto por estanterías de un envío no responde a lo que Elena teclea (colisión de nombres)

- 📖 Existen **dos** funciones globales llamadas `actualizarReparto`:
  - línea **6735** — la del **envío FBA** (reparto entre estanterías): `actualizarReparto(idx, est, el)`.
  - línea **9730** — la de **facturas** (reparto entre fichas): `actualizarReparto(idxLinea, idxFicha, campo, valor)`.
- 🔬 `grep -oP '^(async )?function \K\w+' index.html | sort | uniq -d` → **`actualizarReparto`** (único duplicado que queda).
- En JavaScript, la segunda declaración (9730) **pisa** a la primera en el ámbito global. El modal de reparto de estanterías tiene los inputs con `oninput="actualizarReparto(idx,'D-1',this)"` (📖 6721), pero eso llama a la función de **facturas**, no a la de estanterías.
- **Efecto real:** cuando Elena edita a mano de qué estantería salen las unidades de un producto que está en **varias** baldas, su cambio **se ignora en silencio**. El modal se queda con la **precarga** (llenado por orden P → D-1 → D-2 … 📖 6701-6708), y ese reparto de precarga es el que se aplica al confirmar. El label "Repartido X / Y" tampoco se recalcula (📖 `recalcRepartoUI` nunca se dispara desde el input).
- **Lo que NO rompe:** el total sale bien. El stock global y el `stock_moloka` **no se descuadran** (🔬 0 descuadres en 424 fichas). Lo que se corrompe es **la atribución por balda**: descuenta de la balda que dice la precarga, no de la que Elena eligió. Con el tiempo, el mapa de baldas del app se separa del físico.
- **Alcance HOY:** 🔬 solo **4 fichas activas** tienen stock repartido en más de una estantería física ahora mismo. El modal (y por tanto el bug) solo aparece con esos productos multi-balda. Es un bug real pero de radio pequeño hoy.
- **Es exactamente el mismo hallazgo de esta mañana** ("facturas rompía el reparto por estanterías"): la función de facturas pisa a la de envíos. **El PR #69 lo arregla** renombrando la de envíos a `actualizarRepartoEstanteria`. Correcto. **No hay nada que hacer aquí más que fusionar el #69.**

*No he encontrado ninguna otra cosa que esté descuadrando el stock de Elena hoy: las cifras (§5) salen limpias.*

---

## 1. CÓMO FUNCIONA HOY

**El modelo de stock es "el stock vive en las baldas".** `productos.ubicaciones_cant` (jsonb, `{ "P": 3, "D-1": 5, ... }`) es la verdad; `stock_moloka` **se deriva** sumando las baldas en el **mismo** `update`, nunca se escribe suelto. `ubicaciones` (array de text) es solo el listado de claves, para pintar etiquetas.

### 1.1 Envío a FBA — `confirmarEnvioFBA` (📖 6775-7035)
1. **Reparto por estantería** (📖 6779-6802): productos en 1 sola estantería → automático (toda la qty de ahí); en varias → modal `pedirRepartoEstanterias` (📖 6696). Productos sin estantería conocida → `{}` (luego la barrera los bloquea).
2. **Barrera no-negativos** (📖 6804-6829): **re-lee `ubicaciones_cant` fresco de BD** (📖 6811) y valida que (a) la suma repartida == qty y (b) no se pide de una balda más de lo que hay. Si algo falla → toast de error y **aborta**. Sólida.
3. **Pesos de cajas** (modal UPS) → 4. **Inserta en `envios_fba`** `estado:'preparado'` con snapshot congelado de productos (📖 6852-6860).
5. **Descuenta stock producto a producto** (📖 6871-6895): parte de las baldas frescas, resta el reparto, recalcula `stock_moloka` como suma de baldas, y lo mete todo en **un único `update` crítico con control de error**. Si el update falla → `fallosStock` + **toast** (📖 6896-6898). Solo si el stock bajó, registra el movimiento (`-qty`, tipo `envio_fba`, balda origen, referencia). Diseño explícitamente endurecido tras un bug del 8-jun (📖 6864-6868).
6. Silencia alertas `mandar_fba`/`pedir_proveedor` con lógica LIL (📖 6900-7015), genera PDF, limpia el carrito.
   - `enviado_fba`, `stock_fba` y `stock_inbound` **no se tocan** aquí (📖 6869; el inbound/FBA lo gobierna el informe de Amazon).
   - `estado` del envío se avanza a mano (preparado→enviado→recibido) desde el detalle (`cambiarEstadoEnvio`, 📖 7229). Es un campo de bookkeeping **sin efecto sobre el stock**.

### 1.2 Entrada manual suelta — `confirmarEntrada` (📖 6288-6324)
Suma `qty` a la balda **P**, deriva `stock_moloka`, registra movimiento `entrada`/`entrada_mercancia`. **No** toca `activo`/`estado` (no resucita fichas). Variantes: `confirmarEntradaChase` (📖 6329, crea ficha CHASE si no existe) y `crearProductoYEntrada` (📖 6412).

### 1.3 Ajustes — `confirmarAjusteStock` (📖 5866-5934)
Dos ramas: **por balda** (campo `stock_moloka`, re-lee fresco, recalcula desde baldas, movimiento `ajuste` o `venta_otros` si el motivo es venta) y **directa FBA** (campo `stock_fba`, override manual). Ambas dejan fila en `ajustes_stock`. La inserción **no** setea `diferencia` ni `fecha` (los rellena la BD; 🔬 0 nulos).

### 1.4 Rastro — `registrarMovimiento` (📖 6269-6286)
Log append en `movimientos`. **Best-effort: si el insert falla, solo va a `console.error` y el flujo de stock sigue** (📖 6282, 6265 lo dice explícito). `usuario = localStorage 'moloka_usuario' || 'desconocido'`.

### 1.5 Devoluciones (📖 8060-8136)
**Solo lectura/reporting.** `cargarDevoluciones` lee la tabla `devoluciones` (poblada por otro importador) y la cruza con `rentabilidad.json`. **No devuelve stock a ninguna balda** ni a `stock_moloka`/`stock_fba`. Una devolución SELLABLE no reingresa inventario por esta app.

---

## 2. LO BUENO (conservar en la v2)

- 🔬📖 **`stock_moloka` derivado de las baldas en el mismo write** → **0 descuadres en 424 fichas, 0 negativos, 0 baldas negativas**. El modelo es sólido; es la razón de que las cifras salgan limpias.
- 📖 **Barrera no-negativos real y sobre stock FRESCO** (6804-6829): no se puede enviar de una balda más de lo que tiene, ni sin localizar el origen. Re-lee de BD justo antes, no confía en la copia en memoria.
- 📖 **El descuento crítico está aislado y comprobado** (6863-6898), con la lección del bug 8-jun ya incorporada: stock primero, movimiento solo si bajó, ubicaciones no bloquean. **`fallosStock` avisa por toast**, no se traga.
- 🔬 **Rastro perfecto desde que hay tracking:** de los **124** envíos posteriores al 2026-06-09, **124 tienen su movimiento** con la referencia (0 huérfanos). Los 95 "sin movimiento" son **todos** anteriores al arranque del log.
- 📖 **Las salidas NO resucitan fichas.** Ni el envío ni la entrada suelta escriben `activo:true`/`estado:'OK'` a ciegas (el pecado de facturas). Solo tocan campos de stock.
- 🔬 **`ajustes_stock` está vivo y consistente:** 56 filas, hasta 2026-07-19, `diferencia`/`fecha` siempre pobladas.
- 📖 Búsqueda de producto en envío tolerante (EAN-13/UPC-12 con/sin cero, fnsku, asin) y **selector** cuando hay varias coincidencias (regular vs CHASE se distinguen por ficha) — las baldas no se confunden porque cada ficha tiene su `id` y su `ubicaciones_cant`.

---

## 3. LO MALO (ordenado por lo que cuesta)

1. 📖🔬 **Colisión `actualizarReparto`** — ver §0. Coste: atribución por balda errónea en multi-balda. Arreglado por PR #69.
2. 📖 **No hay transacción en `confirmarEnvioFBA`.** El insert en `envios_fba` (paso 4) y los N updates de stock (paso 5) + los N movimientos son operaciones sueltas. Si un update de stock peta a mitad del bucle, quedan productos descontados y otros no, **con la fila de envío ya creada** (`preparado`). Solo un toast lo delata. Es el mismo riesgo estructural que las facturas, aquí en la operativa **diaria**.
3. 📖 **`registrarMovimiento` se traga los errores** (6282). Si el insert del movimiento falla, **el stock ya se movió pero no queda rastro** y Elena no ve nada. La Película (el ledger) es best-effort, no garantizada.
4. 📖 **`ajustes_stock` insert también a `console.warn`** (5908, 5924): el stock se ajusta pero la fila de auditoría puede perderse en silencio.
5. 📖 **`Miravia` está dentro de `ESTANTERIAS_MOLOKA`** (5642) → el pool de baldas elegibles para un envío FBA **incluye Miravia**. `huecosDe` (6781) filtra por esa lista, así que stock del canal Miravia es candidato a salir hacia FBA. Cruce de canales latente. (Hoy no ha mordido: 🔬 0 descuadres.)
6. 🔬📖 **`enviado_fba` es una columna muerta y stale.** **Ningún** punto del código la escribe (`grep enviado_fba` → 0 matches de escritura). En BD: 164 fichas con valor >0, **9.584 unidades** congeladas de alguna migración vieja, que ya no se actualizan nunca. Es el gemelo del desfase de `stock_fba` que se midió esta mañana.
7. 🔬 **56 de 424 fichas tienen `ubicaciones` (array) desincronizado de las claves de `ubicaciones_cant`.** Es el caso Goku generalizado. No afecta al stock (se deriva del jsonb, 0 descuadres), pero **la UI de envío pinta las etiquetas de balda desde el array** (6567), así que esas fichas muestran ubicaciones equivocadas.
8. 📖 **Race read-modify-write.** El descuento re-lee fresco (6811) y escribe después (6884): más estrecho que facturas, pero sigue sin ser atómico. Dos pestañas / un factura-confirm simultáneo pueden perder una escritura. Mitigado por ser un solo operador, no eliminado.
9. 🔬 **`movimientos.tipo` tiene ruido legacy.** Conviven `ajuste_recuento` (2), `venta_miravia` (1), `roto` (1) — valores que el código actual ya no emite — y **`venta_otros`, que el código documenta como tipo (6266) y produce (5899), tiene 0 filas**. Además 293 movimientos `envio_fba` (los previos al tracking) van sin `motivo`, sin `referencia` y con `usuario` NULL (los escribió un código anterior a `registrarMovimiento`).
10. 📖 **Devoluciones no reingresa stock** (§1.5). Si esto es intencionado (el stock devuelto lo tiene Amazon), vale; pero hoy no hay ningún camino por el que una devolución vuelva al inventario de Moloka.

---

## 4. LO QUE NUNCA SE VALIDA

- 📖 **Que el movimiento se escribió.** Se traga el error → puede haber stock movido sin línea en el ledger.
- 📖 **Que el reparto que editó Elena se aplicó.** Por la colisión §0, sus ediciones se ignoran sin aviso.
- 📖 **Atomicidad del envío.** Nada garantiza que envío + descuentos + movimientos ocurran todos o ninguno.
- 📖 **Concurrencia.** Ninguna guarda contra dos escrituras simultáneas sobre la misma ficha.
- 🔬 **`enviado_fba` no se mantiene ni se compara** con nada; queda a la deriva.
- 📖 **Que el `stock_despues` del snapshot del envío coincida con la realidad** tras posibles cambios concurrentes.

---

## 5. LAS CIFRAS (🔬 medido en producción)

**Integridad de stock (424 fichas):**
| Medida | Valor |
|---|---|
| `stock_moloka` NULL / negativo | 0 / 0 |
| Descuadre `stock_moloka` vs suma de baldas | **0** |
| Unidades en descuadre | **0** |
| Fichas con alguna balda negativa | 0 |
| Baldas huérfanas (clave fuera de {P,D-1,D-2,D-3,I-1,I-2,Miravia}) | **0** |
| Fichas con `ubicaciones[]` desincronizado de `ubicaciones_cant` | **56** |
| Fichas activas con stock en >1 estantería física (afectables por §0) | **4** |

**`envios_fba` (219 filas, 2026-05-02 → 07-27):**
| Estado | N |
|---|---|
| preparado | 187 |
| enviado | 32 |

- Envíos **posteriores** al arranque del log (2026-06-09): **124**, y **124 con su movimiento** (0 huérfanos).
- Envíos **anteriores**: 95, sin movimiento (el log aún no existía). No es pérdida de datos actual.

**`movimientos` (844 filas, desde 2026-06-09):**
| tipo | N | sin referencia | usuario='desconocido' | usuario NULL |
|---|---|---|---|---|
| envio_fba | 618 | 293 | 325 | 293 |
| entrada | 199 | 54 | 149 | 50 |
| ajuste | 23 | 23 | 23 | 0 |
| ajuste_recuento | 2 | 2 | 0 | 2 |
| venta_miravia | 1 | 1 | 0 | 1 |
| roto | 1 | 1 | 0 | 1 |

- Por motivo: (null) 347 · envio_fba 325 · factura 145 · error_conteo 14 · rotura 6 · otro 3 · alta_producto 3 · entrada_mercancia 1.
- **`entrada_mercancia` = 1**: la entrada manual suelta casi no se usa; casi todas las entradas entran por el módulo de facturas (`motivo='factura'` = 145).
- Los 293 `envio_fba` sin referencia/usuario son legacy previos a `registrarMovimiento`.

**`ajustes_stock` (56 filas, 2026-05-06 → 07-19) — vivo, NO muerto:**
| motivo | campo | N |
|---|---|---|
| error_conteo | stock_moloka | 33 |
| otro | stock_moloka | 13 |
| rotura | stock_moloka | 7 |
| venta_fuera_amazon | stock_moloka | 3 |

- **Todos** sobre `stock_moloka`; **0 ajustes sobre `stock_fba`** (la rama de override FBA nunca se ha usado). `diferencia`/`fecha`: 0 nulos.

**`enviado_fba` (columna muerta):** 424 fichas · 0 NULL · 260 en cero · **164 con valor >0** · máx 2.064 · **suma 9.584 uds** — nunca reescrita por la app.

---

## 6. QUÉ IMPLICA PARA LA v2

- **Conservar el modelo "el stock vive en las baldas" y derivar `stock_moloka` en el mismo write.** Es lo que da 0 descuadres. Es el activo más valioso de esta capa.
- **Mover el descuento del envío a un RPC transaccional** (como ya se hizo con `entrada_factura`): envío + N descuentos + N movimientos, todo o nada. Cierra el punto §3.2 y la race §3.8.
- **El ledger (`movimientos`) debe ser Película garantizada, no best-effort.** Si el movimiento no se puede escribir, la salida no debe darse por buena en silencio (§3.3, §4). Es un cajón Película (CLAUDE.md §1.6): append obligatorio.
- **No más funciones globales duplicadas.** La colisión `actualizarReparto` es la segunda víctima del mismo patrón (facturas pisando a otro módulo). La v2 debe aislar módulos (namespaces / módulos ES) para que esto sea imposible por construcción.
- **Sacar `Miravia` del pool de reparto de un envío FBA** (§3.5): es otro canal, no una estantería de picking para Amazon.
- **Decidir el destino de `enviado_fba`** (§3.6): o se recalcula desde los movimientos/informe, o se elimina. Hoy miente (9.584 uds fantasma). `stock_fba` sigue gobernado por el informe de Amazon, no por las salidas.
- **Sanear `movimientos.tipo`** a un vocabulario cerrado y validado (§3.9); `venta_otros` documentado pero con 0 uso indica que el flujo real difiere del pretendido.
- **Devoluciones:** decidir explícitamente si una devolución SELLABLE debe reingresar stock (a qué balda) o quedarse como reporting (§1.5, §3.10).
- **Barrera no-negativos: portarla tal cual.** Está bien pensada (re-lee fresco, bloquea). Es un patrón a replicar en todas las salidas de la v2.

---

*Auditoría de lectura y medida. Ninguna escritura en ninguna base. Lo que no pude verificar queda dicho: no reconcilié `sum(movimientos) == stock` producto a producto porque el log arranca el 2026-06-09 y no cubre el stock previo — `movimientos` es un log de auditoría, no el libro que mueve el stock (eso es `ubicaciones_cant`). La prueba equivalente que sí pude hacer (0 descuadres baldas↔`stock_moloka`, y 124/124 envíos post-tracking con movimiento) cubre lo que importa.*
