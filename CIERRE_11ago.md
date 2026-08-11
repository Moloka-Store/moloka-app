# CIERRE DEL 11-AGO-2026 — el día entero, en un documento

**Para leerlo dentro de tres meses sin nada más al lado.** Empezó como una auditoría del trackeador
y acabó en la fórmula del margen. Todo medido por SQL de solo lectura contra producción
(`ogfbjjdxcltzpygzuyla`), salvo lo que se dice explícitamente.

**Al cerrar el día no se había aplicado nada:** dos PR abiertos (#143, #149), cinco migraciones
escritas y ninguna ejecutada, ninguna fórmula tocada, ninguna tabla borrada.

📄 Los detalles viven en cuatro documentos; esto es el mapa:
[`RESPUESTA_ENCARGO_TRACKEADOR_11ago.md`](RESPUESTA_ENCARGO_TRACKEADOR_11ago.md) ·
[`PRELACION_TARIFAS_11ago.md`](PRELACION_TARIFAS_11ago.md) ·
[`ACANTILADO_SIN_FACTURA_ALTA_11ago.md`](ACANTILADO_SIN_FACTURA_ALTA_11ago.md) ·
[`CAPTURA_SELLER_LADO_ALTO_11ago.md`](CAPTURA_SELLER_LADO_ALTO_11ago.md) ·
y para ejecutar, [`EJECUTAR_11ago.md`](EJECUTAR_11ago.md).

---

## 1. LO QUE SE MIDIÓ

### 1.1 El trackeador no estaba roto — la auditoría lo estaba

| Creencia de partida | Lo medido |
|---|---|
| «Vive en su propio repositorio» | Vive en **`moloka-app`**: `moloka_tracker_snapshot.py`, `_nube.py`, `_cerebro.py` |
| «`monitor_snapshots` borra su histórico» | **Nunca ha borrado una fila de una carga real.** Tres cargas intactas |
| «Se paró por una avería» | **21 runs, 21 éxitos.** No tiene reloj: es 100 % botón, y nadie lo pulsó |
| «Escribe en `productos`» | **Solo lee.** No escribe una sola vez |

**La prueba de que no borra**, y es la que cierra la discusión: los ids van **1747→2322** y
**972→1547**, contiguos, **sin un solo hueco**. Los 1.746 y 970 «borrados» de
`pg_stat_user_tables` son **un bloque único por debajo de todo lo vivo** — la limpieza de la tanda
de pruebas del 8-jul (ocho ejecuciones en una mañana). Y la columna que nadie miró:
`monitor_recomendaciones` tiene **385 actualizaciones**, que son exactamente sus 385 filas
`OBSOLETA`. El código hace lo que su comentario dice.

> 🔑 **Lección:** `n_tup_del` no prueba un patrón de borrado. Sin huecos en el rango de ids, es una
> purga única, no una sobrescritura recurrente.

### 1.2 La clave del trackeador es `anon`

`SUPABASE_KEY` es `sb_publishable_…` (46 caracteres), rol **`anon`**. Se resolvió **sin ver el
secreto**, porque las claves de Supabase declaran su rol dentro del valor. El trackeador escribe
como anónimo y **no tiene otra vía** (ni `psycopg2` ni `DB_URL`).

### 1.3 El margen está inflado, y no por lo que parecía

`transacciones_movimientos` tiene las tarifas **reales, de factura**: 13.146 movimientos, 1-ene →
9-ago. **160 de los 176 del universo (90,9 %)** con factura reciente. Aplicando la prelación real:

| | |
|---|---|
| Cambian de **comisión** | **6** de 176 |
| Cambian de **fee** | **152** de 176 |
| Fee sube | 95 de 109 · **+0,63 €** de media |
| **Delta de margen** | **−3,54 puntos** |
| 🔴 **Parecen rentables y venden a pérdida** | **10** |

**Por qué la comisión casi no cambia:** 142 de los 160 están de verdad en el tramo del 15 %, y
`15,0 × 1,03 = 15,45` contra el `15,50` del relleno. **Acierta por casualidad en 142 de 160** y
falla 7 y 10 puntos en los tramos del 8 % y el 5 %. La peor forma de estar mal.

### 1.4 El acantilado de 20 € — y la confirmación con el umbral corregido

> ### 🔒 CONFIRMADO POR ESCRITO: EL ESCALÓN AGUANTA
>
> A mitad del día apareció la duda de si las mediciones estaban hechas con la escala cruzada, porque
> **`ventas_producto` viene SIN IVA**. Se rehízo el corte con las dos escalas sobre los mismos datos
> (ventana desde 1-abr, n≥2 a cada lado):
>
> | Corte | SKU | Suben | Salto medio | Máximo |
> |---|---|---|---|---|
> | **La medición VIEJA** — umbral 20 sobre precio **con IVA** | **21** | **18** | **+0,55 €** | **+0,79 €** |
> | **La medición NUEVA** — umbral **16,53** sobre `ventas_producto` (= 20 sin IVA) | **20** | **18** | **+0,55 €** | **+0,79 €** |
> | *(la escala cruzada: umbral 20 sobre `ventas_producto`)* | *7* | *2* | *+0,35 €* | *+0,63 €* |
>
> **Las dos primeras son la misma medición** — la diferencia de un SKU es un caso justo en el borde.
> Las consultas originales ya usaban `(ventas_producto + impuesto_producto)`, o sea el precio con
> IVA, que es el corte correcto. **No hubo que rehacer nada.**
>
> Reverificadas también: grupo de control **55 SKU** (3,63 → 3,69), censo **72 / 104**, **35** que
> cruzan en una pasada, **19** clavados en 19,99 €. Idénticas.
>
> **Nadie tiene que volver a preguntárselo.**

**Y el bug que bloquea reactivar:** el cerebro recalcula el margen a un precio hipotético
**manteniendo fija la tarifa FBA**. Caso `B08HH5V55W` (FUNKO POP Astro Bot): propone 19,99 → 20,37
prometiendo pasar de 10,35 % a 11,40 %; con la tarifa que de verdad aplica arriba, **baja a ~8,85 %**.
No es un número mal puesto: **le cambia el signo a la decisión**.

📌 La **dirección** es un hecho (se deduce de que `margen_en()` no recalcula `fee`); el **8,85 %** es
una estimación que depende de que 3,80 € sea el tramo correcto.

### 1.5 La seguridad

- `v_analisis_auditable` y `v_scoreboard_reglas` son vistas DEFINER, **auto-actualizables**, con
  `anon = arwdDxtm`. Un `DELETE` con la clave publicable **borra `monitor_analisis`** — las 284
  filas de criterio. **Fue arrastre del default ACL, no un grant deliberado**: el ACL es letra por
  letra el de las tablas.
- El event trigger `ensure_rls` **no cubre `CREATE VIEW`**. Por eso nacieron abiertas.
- `ensure_rls` **solo existe en la base**, en ningún repositorio: un restore se lo lleva.

---

## 2. LO QUE SE DECIDIÓ

| Decisión | En una línea |
|---|---|
| **El trackeador se reactiva, no se jubila** | Sus tablas ya son Película; no necesitan `_hist` |
| **Pero no se enciende para repreciar** | Hasta que el cerebro recalcule la tarifa al cruzar los 20 € |
| **Prelación de tarifas** | `factura` > `seller_estimado_a_precio` > `desconocido` |
| **Vive en una VISTA, no en una columna** | Una columna en el maestro sería otro dato sin fecha |
| **Todo en escala NOMINAL** | Que el consumidor no tenga que saber de dónde vino para aplicar el ×1,03 |
| **`precio_tarifado`: una sola columna** | `es_simulacion` no se guarda; no hace falta operativamente |
| **`seller_estimado` en ámbar** | El verde se reserva a factura |
| **Dos subtotales, no un total con nota** | Una nota se lee una vez y se deja de leer |
| **El gap viaja en la fila** | `gap_dias` como columna dondequiera que se sirva un delta |
| **La caja de comisión nace vacía** | Y sin bloquear: lo que se bloquea es el margen |

---

## 3. LO QUE SE DESCARTÓ, Y POR QUÉ

### 3.1 🔴 SP-API — descartado, no negociable

**Ni Moloka ni la app v2 se conectan a SP-API bajo ningún concepto.** Decisión de Fernando, cerrada
el 11-ago. No es una vía a valorar ni para tarifas, ni para comisiones, ni para automatizar la carga
diaria del informe. **No se vuelve a plantear.**

*Consecuencia asumida: la serie de `salud_fba_historico` seguirá siendo irregular (7 fotos en 20
días, con un hueco de 8). El diseño trata eso como permanente, no como algo a arreglar.*

### 3.2 La extrapolación por familia de tamaño — refutada con datos

Se propuso deducir el tramo de tarifa a partir del tamaño, para los productos sin factura del lado
alto. **`item_volume` no predice el tramo:** los tramos 4,0 / 4,2 / 4,3 / 4,6 / 4,9 se solapan
enteros entre 0,0012 y 0,0040; un volumen de 0,0018 cae en cinco a la vez. Con `paq_peso_g` igual.

**Lo que quedó en su lugar es más simple y mejor:** dos niveles y una regla —
*si cruza los 20 € y no hay factura del lado alto, no se emite margen: se emite **NO CALCULABLE***.

> No hay nada que estimar, así que nada puede estar mal. Se autorrepara con el uso. Y falla en la
> dirección segura: un «no calculable» cuesta una oportunidad; una familia mal asignada cuesta
> dinero.

### 3.3 Bloquear el guardado del formulario — descartado

La primera versión del PR #149 impedía guardar una ficha sin comisión. **Se retiró.** Con 99 fichas
activas sin comisión, obligar a rellenarla para poder tocar el nombre o el stock **llevaría a poner
un número cualquiera — que es exactamente cómo nació el 0,1550.**

**Lo que se bloquea es el margen, no el formulario.**

---

## 4. LO QUE QUEDA ABIERTO

### Listo para ejecutar → [`EJECUTAR_11ago.md`](EJECUTAR_11ago.md)

| | Estado |
|---|---|
| Merge #143 · #149 | escritos, sin fusionar |
| Migración `precio_tarifado` | escrita, sin aplicar |
| `SUPABASE_SERVICE_KEY` | pendiente (lo hace Fernando) |
| Gate D1 (`anon` en las dos vistas) | escrito, sin aplicar |
| Las 4 normas de doctrina | escritas, sin insertar |

### Escrito pero sin PR

- 🔴 **El PR del acantilado en el cerebro.** Es la condición de reactivación.
- **El `×1,03` del cockpit v2** (bug confirmado el 3-ago, aún diferido). Hoy el trackeador y el
  cockpit dan márgenes distintos: uno lo omite, el otro lo **duplica** en la rama `'real'`.
- **La vista canónica de tarifas.**
- **`permitir_retroceso` como input** de los procesadores-Foto: hoy **no hay vía soportada para
  reproducir un informe histórico** (medido: la Guarda 10 aborta y su válvula no llega al workflow).
- **Versionar `ensure_rls`** a `migraciones/`.
- **Jubilar `salud_fba_hist`** — depende de lo anterior.
- **`gap_dias`** dondequiera que se sirva un delta.
- **Migración D2** (default ACL) — la más delicada: cambia cómo nace todo objeto futuro.

### Decisiones que dependen de Fernando

1. **La observación id 5** de `seller_observaciones` (4,78 contra 4,60 en ficha). Queda en NULL.
2. **La tanda de captura**: 23 fichas, 29 consultas al popup del Seller.
3. **Los 10 productos que venden a pérdida.** No es deuda técnica: es dinero saliendo hoy.

---

## 5. LAS CUATRO NORMAS QUE SALIERON DEL DÍA

Redactadas para `monitor_doctrina` en
[`migraciones/2026-08-11_doctrina_cuatro_normas.sql`](migraciones/2026-08-11_doctrina_cuatro_normas.sql):

1. **El grupo de control para aislar un escalón** — mide el mismo periodo donde la causa no puede
   actuar. *(55 SKU que nunca cruzan → +0,06 € en seis meses.)*
2. **`|| 0` convierte «no lo sé» en un número** — y el margen sale inflado quince puntos.
3. **Una escritura sin botón no parece una escritura** — barre todos los `onchange`, no solo los
   formularios.
4. **`ventas_producto` no declara su escala** — viene sin IVA. Hermana de la 13.

---

## 6. EL HILO QUE ATRAVIESA TODO EL DÍA

Las cuatro cosas grandes que se encontraron son la misma cosa:

| | |
|---|---|
| El `0,1550` | un valor por defecto de formulario que parece medido |
| El `|| 0` | un cero que parece una comisión |
| El fee del acantilado | una tarifa de un tramo que parece la del otro |
| La familia de tamaño | una extrapolación que habría parecido una medición |

> ### 🔑 **En una base de datos, un número inventado es indistinguible de uno medido.**
> Por eso la respuesta correcta casi siempre fue la misma: **decir «no lo sé» de forma explícita** —
> `NO_CALCULABLE`, `precio_tarifado` en NULL, la caja vacía, el `gap_dias` en la fila.
>
> **Un hueco visible se arregla. Un número inventado se propaga.**

---

*Medido el 11-ago-2026. El estado de una base caduca en horas: si algo de aquí se va a usar para
decidir, vuelve a medirlo.*
