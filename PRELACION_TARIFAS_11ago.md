# PRELACIÓN DE TARIFAS: de dónde sale la comisión y el fee de cada producto

**11-ago-2026.** Medido por SQL de solo lectura contra producción (`ogfbjjdxcltzpygzuyla`).
Responde a los tres primeros encargos del 11-ago sobre tarifas reales. **Nada aplicado.**

> 🔴 **SP-API queda fuera de este documento y de cualquier diseño.** Ni Moloka ni la app v2 se
> conectan a SP-API bajo ningún concepto. Descartado, no negociable, no se vuelve a plantear.

---

## 0. LA CORRECCIÓN DE PARTIDA

El «94 % sin tarifa real» del informe anterior **era falso**, y el error fue fiarse del comentario
de `seller_observaciones` (*«la única fuente de verdad de tarifas»*) en vez de ir a buscar el dato.
La realidad, medida:

| Fuente | Qué es | Cobertura del universo (176) |
|---|---|---|
| **`transacciones_movimientos`** | **La FACTURA.** `tarifa_venta` y `tarifa_fba` reales | **160 con factura de los últimos 3 meses (90,9 %)** |
| `seller_observaciones` | Captura manual del popup | 10 (5,7 %) |
| `keepa_escaparate` | Estimación de mercado | el resto |

`transacciones_movimientos`: **13.146 movimientos de tipo `pedido`** en ES, del 1-ene al 9-ago-2026,
sobre 304 SKU, con `tarifa_fba` en 12.921 y `tarifa_venta` en 12.882.

🔑 **La lección de método, que vale más que el dato:** un comentario en la base decía «única fuente
de verdad» y se creyó. Es la misma clase de error que la auditoría cometió con `n_tup_del`. **Un
comentario describe una intención, no un censo.**

---

## 1. LA PRELACIÓN — dónde vive y quién la consulta

### 1.1 Lo primero: la prelación YA EXISTE, y funciona

No hay que inventarla. `moloka_tracker_snapshot.py:261-270` ya implementa exactamente la cascada
pedida, con etiqueta de origen para poder auditarla:

```python
com_pct, com_fuente = cascada(
    (vt.get('comision_pct_mediana'), 'real_tx'),   # transacciones
    (p.get(cfg['com_real']),         'real'),      # productos.comision_pct
    (p.get(cfg['com_keepa']),        'keepa_bd'),  # comision_pct_keepa_es
    (k.get('ref_pct'),               'keepa_csv')) # CSV de Keepa
```

Y se usa: de las 576 recomendaciones, **509 salieron de `real_tx`** y solo 42 del relleno.

🔴 **El problema no es que falte la prelación: es DÓNDE vive.** Está dentro de un procesador, y
bebe de `app_datos.clave='rentabilidad'` → un **JSON** (`venta_actual[asin]`), no de la tabla de
transacciones. O sea: la prelación es correcta, pero **la conoce un solo script, la calcula otro, y
viaja en un blob**. Ni `productos` ni el cockpit v2 la ven.

### 1.2 🔴 Y hay un bug en esa cascada, medido

La rama `'real'` lee `productos.comision_pct`, que según la **doctrina 13** es la comisión
**EFECTIVA — ya lleva el 3 % de servicios digitales dentro**. Pero después
`calc_rentabilidad` le aplica `× 1,03` otra vez:

```python
com_amazon = precio_venta * (ref_pct / 100.0) * COM_DIGITALES   # ← 1.03
```

**Es el «3 % duplicado» que la doctrina 13 prohíbe literalmente** (*«NUNCA: precio × comision_pct ×
1,03»*). Las otras tres ramas son NOMINALES y sí necesitan el ×1,03, así que **exactamente una de
las cuatro está mal**. Afecta a 42 recomendaciones (15 ASIN).

📌 Y deja las dos fórmulas de la casa desviadas en sentidos opuestos: el cockpit v2 **omite** el
×1,03 (margen optimista ~0,45 pts) y el trackeador lo **duplica** cuando la fuente es `real`
(margen pesimista ~0,45 pts). **Casi un punto de diferencia entre las dos, y ninguna correcta.**

🔑 **La lección de diseño, y es la que manda en todo lo que sigue:** una fuente de tarifa **no es un
número: es un número + su escala + si lleva el 3 % dentro**. Guardar solo el número es lo que ha
causado dos bugs distintos en direcciones contrarias.

### 1.3 Cómo la implementaría: **una vista canónica**, no una columna en el maestro

**Vista.** Y las tres razones, por orden de peso:

1. 🔴 **Una columna en `productos` volvería a ser un dato sin fecha.** El maestro es un cajón
   MAESTRO (§1.6): guarda identidad, no medidas que caducan. La tarifa cambia cuando Amazon la
   cambia y cuando el producto cruza los 20 €. Congelarla en una columna es fabricar el próximo
   `0,1550`: un número que fue verdad un día y nadie sabe cuándo dejó de serlo.
2. **La derivada se recalcula sola.** Una vista sobre `transacciones_movimientos` incorpora cada
   factura nueva sin que nadie lance nada. Una columna necesita un proceso que la refresque — y ese
   proceso es justo el que hoy no existe.
3. **El cajón correcto ya está lleno.** Las facturas son PELÍCULA y ya se apilan. La vista solo las
   lee.

**Qué debe exponer la vista** — y esto es lo importante, por §1.2:

| Columna | Por qué |
|---|---|
| `asin`, `sku`, `pais` | la llave |
| `comision_nominal_pct` | **SIEMPRE nominal**, una sola escala para todos |
| `fee_fba_eur` | por unidad |
| `fuente` | `factura` / `seller` / `keepa` |
| `medido_en` + `n_movimientos` | *una cifra sin la fecha del dato que la sostiene miente* (§1.4) |
| `fee_bajo_20` / `fee_alto_20` | el par del acantilado (§3) |

🔒 **Uniformar a NOMINAL es la decisión clave**, no un detalle: hace que el consumidor no tenga que
saber de dónde vino el número para saber si aplicarle el ×1,03. Elimina la clase de bug de §1.2, no
una instancia.

**La fórmula de la factura** (doctrina 44 — `tarifa_venta` lleva el 21 % de IVA dentro):

```sql
comision_nominal_pct = -tarifa_venta / (ventas_producto + impuesto_producto) / 1.21 * 100
fee_fba_eur          = -tarifa_fba / cantidad
```

Verificada: da picos limpios en **15,0 · 13,0 · 8,0 · 5,0**, exactamente los tramos de Amazon.

**Dónde debe consultarla el cálculo de margen:** en los **tres** sitios, y ninguno debe volver a
leer `productos.comision_pct`:

| Consumidor | Hoy lee | Debe leer |
|---|---|---|
| `moloka_tracker_snapshot.py` | la cascada del JSON | la vista |
| `calcularMargenVivo` (v2) | `keepa_escaparate.comision_pct` | la vista |
| Informe de factura (v2) | `calc_rentabilidad` portada | la vista |

⚠️ **`productos.comision_pct` no se borra**: se deja de leer para el margen. Sigue siendo el dato
que Fernando teclea, y en 6 productos es lo único que hay.

---

## 2. CUÁNTOS CAMBIAN — y la sorpresa

Aplicando la prelación (**factura de 3 meses > observación de Seller > Keepa**) sobre los 176:

| | |
|---|---|
| Universo | **176** |
| Con factura reciente | **160** (90,9 %) |
| **Cambian de COMISIÓN** (>0,5 pts) | **6** |
| **Cambian de FEE** (>0,05 €) | **152** |
| Comparables con margen (tienen precio en `salud_fba`) | 109 |

### 🔑 Por qué la comisión casi no cambia — y por qué eso no absuelve al relleno

| Tramo nominal REAL | SKU | Dice el maestro | Con el relleno 0,1550 |
|---|---|---|---|
| **15,0 %** | **142** | 15,50 | 127 |
| **8,0 %** | 8 | 11,85 | 4 |
| **5,0 %** | 3 | 9,63 | 1 |
| 13,0 % | 3 | 13,50 | 0 |

**15,0 × 1,03 = 15,45**, y el relleno dice **15,50**. Se desvía **5 centésimas**.

🔴 **El relleno acierta por casualidad en 142 de 160 y es catastrófico en 12.** En los del 8 % se
desvía ~7 puntos y en los del 5 % ~10. Es la peor forma posible de estar mal: **acierta lo
suficiente para que nadie lo mire, y falla justo donde más duele.** Confirma la doctrina 39 y le
pone tamaño.

### 🔴 Lo que de verdad se mueve es el FEE

| | |
|---|---|
| Fee **sube** al aplicar la factura | **95** de 109 |
| Fee baja | 4 |
| Subida media | **+0,63 €/unidad** |
| **Delta medio de margen** | **−3,54 puntos** |
| Márgenes que **empeoran** | **92** de 109 |
| Mejoran | 7 |
| **Parecían rentables y venden a PÉRDIDA** | **🔴 10** |
| Caen por debajo del umbral del 2 % | 12 |

> **Los márgenes de hoy están inflados ~3,5 puntos de media, y no por la comisión: por el fee.**
> `productos` dice 3,28 € donde la factura dice 4,60 €.

### Los 10 que parecen buenos y pierden dinero

| ASIN | Producto | Precio | Fee hoy → real | Margen hoy → **real** |
|---|---|---|---|---|
| `B00IR0DSG8` | Haribo chamallows minis | 5,99 | 3,05 → 3,97 | 2,1 % → **−10,3 %** |
| `B08HHBY7GR` | FUNKO POP KPop Cazadores | 19,95 | 3,51 → 5,95 | 8,1 % → **−4,1 %** |
| `B07MNBKXTH` | Goliat Ztringz | 4,78 | 2,18 → 2,71 | 8,1 % → **−2,9 %** |
| `B0CYCFSBK4` | FUNKO POP Alolan Raichu | 17,95 | 3,51 → 4,78 | 3,1 % → **−3,9 %** |
| `B085DNDLC1` | Fundas Standard (4) | 8,83 | 3,28 → 3,97 | 4,3 % → **−3,5 %** |
| `B0CPNHGQ8Z` | Dragon Ball Super Hero | 14,99 | 3,28 → 4,25 | 4,1 % → **−2,4 %** |
| `B0002TT3N4` | Fundas Standard (1) | 4,99 | 2,35 → 2,74 | 6,4 % → **−1,3 %** |
| `B0CPH9PSFF` | Mini Barbie Land Playset | 7,99 | 3,28 → 3,97 | 8,6 % → **0,0 %** |
| *(+2 más en el umbral)* | | | | |

**Los mayores desplomes de margen**, todos por fee:

| ASIN | Producto | Margen hoy → real | Delta |
|---|---|---|---|
| `B00IR0DSG8` | Haribo chamallows | 2,1 → −10,3 | **−12,4** |
| `B08HHBY7GR` | FUNKO KPop | 8,1 → −4,1 | **−12,2** |
| `B07MNBKXTH` | Ztringz | 8,1 → −2,9 | **−11,0** |
| `B0CPH9PSFF` | Mini Barbie | 8,6 → 0,0 | −8,6 |
| `B01GYYJI30` | Crema castaño 250ml | 13,9 → 5,6 | −8,3 |
| `B07GRRYFL1` | Máquina corte papel | 10,3 → 2,1 | −8,2 |
| `B085DNDLC1` | Fundas Standard (4) | 4,3 → −3,5 | −7,8 |
| `B0002TT3N4` | Fundas Standard (1) | 6,4 → −1,3 | −7,7 |
| `B014JPGAOG` | Ricola té 200 g | 17,5 → 9,9 | −7,6 |
| `B076PFP25F` | Hilo dental dentek | 12,7 → 5,3 | −7,4 |
| `B014DGG0OQ` | Lenor abril fresco | 10,7 → 3,3 | −7,4 |
| `B08T64TTK3` | Funko Mohamed Salah | 13,6 → 6,5 | −7,1 |
| `B0BBZC4BVJ` | Funko Chewbacca | 9,7 → 2,7 | −7,0 |
| `B0CGH1DQZD` | Funko Inside Out 2 | 10,8 → 4,2 | −6,6 |
| `B001PASC5E` | Kukident Active Plus | 8,6 → 2,1 | −6,5 |

⚠️ **Límites de esta lista, para que no se cite de más:**
- **109 de 176 comparables**: 54 no tienen precio en `salud_fba` y 13 les falta alguna pieza.
- El margen usa `salud_fba.your_price`, que puede ir días por detrás.
- El fee de la factura es una **mediana de los últimos 3 meses**, así que para un producto que haya
  cruzado los 20 € en ese periodo mezcla los dos lados del escalón (§3).

---

## 3. EL ACANTILADO, RECONSTRUIDO DESDE LAS FACTURAS

### 3.1 Primero, limpiar el dato

Medido sobre TODO el histórico: **39 SKU** vendidos a ambos lados de 20 €, 33 suben.
Pero ese corte mezcla dos efectos, y hay que separarlos antes de creerse nada:

🔬 **Control — ¿cambian las tarifas con el tiempo?** 55 SKU vendidos **siempre** por debajo de
20 € (9.267 movimientos, o sea sin acantilado posible): mediana ene-mar **3,63 €**, jun-ago
**3,69 €**. **+0,06 € en seis meses.** El calendario de tarifas es estable: el salto no es del tiempo.

⚠️ **Pero los casos extremos SÍ estaban contaminados.** El máximo de +2,50 € (`68-SW97-Z5WF`) compara
una única venta del **19-mar** contra ventas de **may-jun**. Con n=1 y meses de por medio, eso no
mide el escalón.

**Versión limpia** — desde el 1-abr, exigiendo ≥2 ventas a cada lado:

| | Todo el histórico | **Limpio** |
|---|---|---|
| SKU a ambos lados | 39 | **21** |
| Suben al cruzar | 33 (85 %) | **18 (86 %)** |
| Salto medio | +0,51 € | **+0,55 €** |
| Salto máximo | +2,53 € ⚠️ contaminado | **+0,79 €** |

**Conclusión: el escalón es real** (86 % suben, y el control descarta el tiempo), **pero el máximo
de 2,50 € no lo es.** El rango honesto es **+0,27 a +0,79 €**, centrado en ~0,55.

### 3.2 ¿Tramo por producto o por familia de tamaño?

> 🔴 **ESTE APARTADO ESTÁ SUPERADO. La hipótesis de la familia era FALSA y quedó refutada el mismo
> día.** `item_volume` no predice el tramo: los tramos 4,0 / 4,2 / 4,3 / 4,6 / 4,9 se solapan
> enteros entre 0,0012 y 0,0036, y un volumen de 0,0018 cae en cinco a la vez. Con `paq_peso_g`
> igual. **El diseño se queda en DOS niveles: factura o desconocido**, y de ahí sale una regla más
> simple que el modelo — *si cruza y no hay factura del lado alto, no se emite margen: se emite
> NO CALCULABLE*.
>
> 📄 **Ver [`ACANTILADO_SIN_FACTURA_ALTA_11ago.md`](ACANTILADO_SIN_FACTURA_ALTA_11ago.md)**, que lo
> sustituye y trae el censo (72 con factura alta / 104 sin) y la lista de los 76.
>
> *Se deja lo de abajo como estaba, sin retocar, porque explica por qué se llegó a proponer la
> familia y cuál fue la medición que la tumbó. Borrarlo escondería el error.*

**Ninguna de las dos sola. Hacen falta las dos, y en este orden.**

🔬 **Los fees se agrupan en pocos escalones** (movimientos desde el 1-jun): `2,64 · 2,71 · 2,73 ·
2,74 · 3,13 · 3,69 · 3,96 · 3,97 · 4,24 · 4,25 · 4,59 · 4,60 · 4,85 · 4,90`. **No es un continuo:
son ~8 tramos** con variantes de céntimo por el redondeo al dividir pedidos multi-unidad. Eso
confirma que **las familias existen** y son pocas.

🔴 **Pero el par no se deduce del lado bajo.** Medido: `4,25 €` salta a **4,60** en unos SKU y a
**4,85** en otros. Así que conocer el fee de abajo **no basta** para saber el de arriba: dos
productos con la misma tarifa por debajo de 20 € tienen escalones distintos por encima.

**Por tanto:**

1. **Por producto, cuando se puede — y es la vía fiable.** Los **21 SKU** con ventas a ambos lados
   tienen su par **medido en factura**, que es dato duro. Ahí no se estima: se lee.
2. **Por familia para el resto**, y la familia hay que construirla — pero **el dato ya está en la
   base**: 🔬 `salud_fba` tiene `item_volume` y `storage_volume` en **las 223 filas**, y
   `storage_type` con 2 valores. Con eso se agrupan los productos por tamaño y se le asigna a cada
   familia el par observado en los SKU de esa familia que sí han cruzado.
3. **Y lo que no encaje en ninguna, se marca como desconocido.** No se rellena. Es exactamente el
   error del `0,1550`: **un tramo inventado sería indistinguible de uno medido.**

⚠️ **Lo que NO se puede afirmar todavía, y hay que medirlo antes de construir:** que `item_volume`
prediga la familia. Es la hipótesis razonable —el escalón es de tamaño de caja según la doctrina 7—
pero **no lo he cruzado**. La comprobación es directa y va antes del diseño: agrupar los 21 SKU de
par conocido por `item_volume`/`storage_type` y ver si los de la misma familia comparten par. Si
comparten, la familia es derivable; si no, solo vale la vía 1 y el resto queda como desconocido.

📌 **Nota sobre el mecanismo:** el escalón se comporta como un **umbral de precio** (misma caja,
tarifa distinta según el precio), no como un cambio de tamaño. Lo consistente con la doctrina 7 es
que cada familia tiene **un par** `(fee_bajo, fee_alto)` y **el precio elige el lado** — que es
justo lo que el cerebro no hace hoy.

---

## 4. QUÉ HARÍA, EN ORDEN

| # | Qué | Por qué |
|---|---|---|
| ~~1~~ | ~~Cruzar `item_volume` × par conocido~~ | ✅ **HECHO — y salió que NO.** La familia no es derivable |
| 2 | **La vista canónica**, en NOMINAL, con `fuente`, `medido_en` y `fee_bajo_20`/`fee_alto_20` **que pueden ser NULL** | Es la pieza de la que cuelgan las otras tres. El NULL **es** la respuesta cuando no hay factura de ese lado |
| 3 | **Arreglar el 3 % duplicado** de la rama `'real'` del trackeador | Bug medido, 42 recos |
| 4 | **Que los tres consumidores lean la vista** | Hasta entonces siguen los ~3,5 puntos de inflación |
| 5 | **Revisar los 10 que venden a pérdida** | No es deuda técnica: es dinero saliendo hoy |

🔴 **Y el 5 no espera a nada.** Los otros cuatro son cañería; ése es que hay diez productos con
stock cuyo precio actual no cubre el coste.

---

*Medido el 11-ago-2026. El estado de una base caduca en horas: revalidar antes de decidir.*
