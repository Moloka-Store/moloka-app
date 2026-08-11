# TANDA DE CAPTURA: el lado alto del escalón, desde el popup del Seller

**11-ago-2026.** 23 fichas para capturar de una sentada. **Nada aplicado.**

---

## 0. POR QUÉ ESTO EXISTE

El acantilado se resolvió en dos niveles —factura o desconocido— porque no hay familia de tamaño
deducible. Eso deja **104 de 176** productos sin poder calcular una subida que cruce los 20 €.

Pero hay un tercer nivel disponible **sin API y sin esperar a que se venda**: el popup de Seller
Central da la tarifa estimada **al precio que le pongas**. Es la misma captura que ya alimenta
`seller_observaciones`, apuntada al **lado alto** del escalón en vez de al precio vigente.

Con eso, la prelación pasa a:

> ### `factura` > `seller_estimado_a_precio` > `desconocido`

🔑 Y sigue sin haber estimación inventada: **el popup es la estimación de Amazon para tu cuenta**,
no una extrapolación nuestra. Lo que cambia es que ahora se pregunta *«¿cuánto me cobrarías a
20,99 €?»* en vez de dar por bueno el fee de 19,99 €.

---

## 1. LA TANDA — 23 fichas, dos precios

### Precio a consultar en el popup

**Para todas: `21,99 €`.** Un solo número, y no es arbitrario:

- Está **por encima del escalón**, que es lo que hace falta medir.
- Es el **techo de lo que el cerebro puede proponer en una pasada** sobre una ficha de 19,99 €
  (`ESCALON_SUBIDA = +10 %` → 19,99 × 1,10 = 21,99). O sea que cubre toda la banda alcanzable.

⚠️ **El supuesto que lleva dentro, dicho en alto:** que la tarifa es **plana** entre 20,00 € y
21,99 €. Es lo esperable —el escalón medido está en los 20 €— pero **si hubiera otro umbral
intermedio**, capturar a 21,99 daría un fee más caro del que aplica a 20,50. Eso **falla en la
dirección segura** (margen subestimado → no se recomienda una subida que sí valía), pero conviene
saberlo. Si al capturar dos fichas sale un fee distinto del esperado, es la señal para mirar un
segundo umbral.

### 🔴 Grupo 1 — sin factura de NINGÚN lado · 6 fichas · capturar **DOS** precios

Aquí no se conoce el fee ni por debajo. Hay que preguntar el popup **dos veces**: a `19,99 €` y a
`21,99 €`.

| ASIN | SKU | Producto | Precio hoy | Stock | PVD |
|---|---|---|---|---|---|
| `B00TQ5KPNC` | `CH-SOY5-FJSH` | FUNKO POP Harry Potter Severus Piton 05 | **21,99** | 12 | 7,83 |
| `B0BBZC4BVJ` | `N8-3KAH-NCGB` | FUNKO POP Star Wars Chewbacca Bobble 596 | 19,99 | 12 | 7,83 |
| `B0CND2J282` | `9G-Q7HY-6V9U` | Funko UP S2 Rusell 1479 | 19,99 | 8 | 7,56 |
| `B09VY4D9H9` | `9Z-D9ID-JEOD` | Funko Espeom 884 | 19,90 | 12 | 7,93 |
| `B0CND1XCGZ` | `W5-KHCR-JL0P` | FUNKO POP Rocks Guns N' Roses Slash | 18,19 | 12 | 7,83 |
| `B0CYCFSBK4` | `EQ-YN4T-K5XD` | FUNKO POP Pokemon Alolan Raichu 1011 | 17,95 | 23 | 7,83 |

📌 `B00TQ5KPNC` **no estaba en la lista de los 19**: está a 21,99 €, ya por encima del escalón, y aun
así **no tiene ninguna venta facturada**. Hoy su margen se calcula entero sobre estimación de Keepa.

### 🟠 Grupo 2 — clavados en 19,99 € con fee bajo medido · 17 fichas · capturar **solo 21,99 €**

De éstos ya sabemos el lado bajo por factura; falta el alto.

| ASIN | SKU | Producto | Stock | Fee bajo (factura) | Últ. venta baja |
|---|---|---|---|---|---|
| `B0CLFNMZVB` | `4S-IC6O-AZY9` | FUNKO POP Shrek 30th Shrek w/Snake 1594 | 33 | 4,25 | 19-jul |
| `B00TQ5S6D8` | `9S-C5RP-H7ZX` | Funko POP! 06 Lord Voldemort | 32 | 3,91 | 26-jul |
| `B09V85QCNN` | `W8-CP8S-V8F8` | Bridgerton POP! Penelope | 27 | 3,97 | 09-ago |
| `B09S8P7L7H` | `KS-TALS-F53K` | FUNKO POP E.T. in Disguise 1253 | 23 | 4,25 | 30-jul |
| `B0D98TXCT5` | `BL-P0QP-GT5P` | FUNKO POP League of Legends Jhin 1081 | 20 | 3,91 | 09-ago |
| `B0D98TB3QW` | `IH-G6DV-607K` | Funko POP! Akali – League of Legends | 16 | 4,24 | 12-jul |
| `B07MZPS562` | `XH-RVT9-5HVA` | Funko POP! Vegeta DBZ | 13 | 3,97 | 19-abr |
| `B08HGXZQ7P` | `SW-IJUQ-25WW` | FUNKO POP MLS Inter Miami Messi 01 | 12 | 3,91 | 19-mar |
| `B0CNCZPH6V` | `9I-6TNA-8EAI` | Funko Pop! Dracula – Universal Monsters | 12 | 3,97 | 01-jul |
| `B0CYCJ828R` | `QY-IH7M-H06O` | Funko Pop! Ahri – League of Legends | 11 | 4,24 | 19-abr |
| `B0DSWFXBZZ` | `R4-WWLK-W753` | POP! Vinyl – Lingering Will | 11 | 4,25 | 17-jun |
| `B0CLFGBNN8` | `VO-GRHS-XQ10` | FUNKO POP Shrek 30th Gatto con Stivali | 9 | 3,97 | 08-ago |
| `B0CLF89N8Z` | `D6-FBA8-BD6E` | FUNKO POP The Pink Panther 1551 | 5 | 3,97 | 10-jun |
| `B07HB8HGSZ` | `XV-SL09-WGC3` | FUNKO POP Dragon Trainer 3 Toothless 686 | 4 | 4,19 | 26-mar |
| `B0FMF9N3VT` | `CX-RY0F-2IJR` | One Piece POP!&Buddy Animation | 4 | 4,25 | 09-ago |
| `B0CGH8Q2KK` | `KK-CLX3-XJX4` | FUNKO POP Harry Potter Azkaban w/Broom | 3 | 3,97 | 07-jul |
| `B07HB4VNVV` | `VK-UZDD-A5JV` | Funko POP! 495 Mufasa – El Rey León | 2 | 4,25 | 10-jul |

**Total de la tanda: 23 fichas · 29 consultas al popup** (6 × 2 + 17 × 1).

📌 **Lo que se gana con eso, dimensionado:** de los 35 productos que hoy pueden cruzar en una pasada
sin poder calcular el margen, esta tanda cubre **23**. Los 12 restantes están entre 18,18 y 19,90 €
y merecen una segunda tanda, pero son menos urgentes: ninguno está clavado en el escalón.

---

## 2. LA COLUMNA QUE HACE FALTA

`seller_observaciones` ya tiene `precio`, `tarifa_fba`, `comision_eur`, `comision_pct_efectiva`,
`comision_pct_nominal` y `tarifas_totales`. **Lo que no tiene es a qué precio corresponden esas
tarifas** — hoy se asume que al `precio` vigente, porque es lo único que se capturaba.

### 🔒 Una sola columna

```sql
alter table public.seller_observaciones
  add column precio_tarifado numeric;

comment on column public.seller_observaciones.precio_tarifado is
'Precio al que corresponden tarifa_fba / comision_eur / comision_pct_* / tarifas_totales, tal y
como los devolvió el popup del Seller. NO es necesariamente el precio del listing.
  · precio_tarifado = precio  -> lectura del estado ACTUAL (el popup se leyó al precio vigente).
  · precio_tarifado <> precio -> SIMULACIÓN a un precio hipotético (p.ej. el lado alto del
    escalón de 20 EUR, para poder calcular una subida que cruce antes de que haya factura).
NULL solo en las filas anteriores al 11-ago-2026, que son todas lecturas al precio vigente.';
```

**Por qué UNA y no dos** (una para el precio y otra para un `es_simulacion boolean`): el booleano
sería **derivable de la misma fila** (`precio_tarifado <> precio`), y dos columnas que dicen lo
mismo es exactamente donde empiezan las divergencias — dos códigos que hoy coinciden es una
coincidencia, no una garantía. Con una columna no hay nada que pueda desincronizarse.

### El relleno de lo que ya hay

```sql
update public.seller_observaciones
   set precio_tarifado = precio
 where precio_tarifado is null;
```

⚠️ **Esto lleva un supuesto y hay que confirmarlo antes de aplicarlo: que las 65 observaciones
existentes se capturaron con el popup al precio vigente**, sin tocar el campo de precio. Lo sabe
Fernando, que las hizo. **Si alguna fue una simulación, este `update` la convierte en una
observación real y miente.** Si hay duda, el relleno se deja sin hacer y el NULL se lee como
«no consta» — que es más honesto y no rompe nada: la vista puede tratar NULL como «= precio» sin
escribirlo.

📌 **No propongo un `NOT NULL` ni un `CHECK`**: el día que alguien capture sin anotar el precio, es
mejor una fila con NULL visible que un `insert` que falla y se pierde la captura.

---

## 3. QUE EL MARGEN ESTIMADO NO SE MEZCLE CON EL FACTURADO

La pieza ya existe y **no hay que inventar nada**: `monitor_recomendaciones` tiene `fuente_margen`
y `confianza`, y el cockpit ya pinta un semáforo con ellas (`index.html:3181-3184`).

Solo hay que **añadir el valor nuevo y su grado**:

| `fuente_margen` | De dónde sale | `confianza` | Qué significa |
|---|---|---|---|
| `factura` | `transacciones_movimientos` (lo cobrado de verdad) | **alta** | Medido |
| **`seller_estimado`** | **popup, al precio consultado** | **media** | **Estimación de Amazon para tu cuenta** |
| `keepa` | `keepa_escaparate` | baja | Estimación de mercado |
| *(sin valor)* | — | — | **`NO_CALCULABLE`** — no se emite margen |

🔴 **Y la regla de no mezclar, escrita para que no se diluya:** una recomendación cuyo margen salga
de `seller_estimado` **no puede presentarse junto a una de factura como si fueran lo mismo**. En
concreto:

1. **En la fila**, el semáforo ya lo distingue — basta con que `seller_estimado` pinte en ámbar y no
   en verde. El verde queda reservado a `factura`.
2. **En los totales, no se suman en el mismo número.** Hoy la pestaña acumula
   `impacto_eur_mes` de todo lo accionable en un solo total. Un total que mezcla euros medidos con
   euros estimados **es un número que no se puede auditar**. Deben ir en dos subtotales, o el total
   debe llevar al lado cuánto de él es estimado.
3. **La vista canónica lleva `fuente` y `medido_en`**, así que el dato viaja con su procedencia y
   nadie tiene que acordarse.

🔑 Es la misma regla que el `gap_dias` de la serie y que el «no calculable» del acantilado:
**el dato viaja con lo que hace falta para saber cuánto vale.** Un margen sin su procedencia es un
margen que miente por omisión.

---

## 4. DOS AVISOS QUE SALIERON DE ESTO Y VALEN PARA CUALQUIER PANTALLA

### 🔴 Antes de vaciar un campo, mira qué hace el cálculo con el vacío

Al quitar el relleno de `15,5` de la calculadora, la línea del cálculo era:

```js
const comisionPct = (parseFloat(document.getElementById('bb-comision-pct').value) || 0) / 100;
```

**Con la caja vacía, `|| 0` hacía la comisión CERO**, y el margen salía **inflado ~15 puntos**.
Vaciar el campo sin tocar esa línea habría **cambiado un relleno del 15,5 % por un cero silencioso**
— mucho peor, porque el 15,5 al menos era casi correcto en 142 de 160 productos, y el cero no lo es
en ninguno.

🔬 Verificado en el DOM real: con comisión `0` explícita el cálculo da comisión **0,00 €** y tarifas
**3,97 €** en vez de 7,85 €.

> **Regla: `|| 0` y `|| valor` sobre un input convierten «no lo sé» en un número. Antes de permitir
> que un campo quede vacío, hay que ir a ver qué hace el cálculo con ese vacío.** El hueco solo es
> honesto si el que lo lee sabe tratarlo.

### 🔴 Un campo que escribe en el maestro sin que nadie pulse nada

```html
<input id="bb-comision-pct" ... onchange="guardarComisionProducto()">
```

`guardarComisionProducto()` hace un `update` directo sobre `productos.comision_pct`. **No hay botón
de guardar**: basta con modificar el campo y salir de él. Y como el campo venía **pre-rellenado con
15,5**, era una **segunda vía de entrada del relleno al maestro**, distinta del formulario de
edición y mucho menos visible.

> **Regla: al auditar de dónde sale un valor sucio, no basta con encontrar el formulario que lo
> guarda. Hay que buscar TODOS los `onchange`/`oninput` que escriben.** Una escritura sin botón no
> se parece a una escritura, y por eso no se busca.

---

*Medido el 11-ago-2026. Revalidar antes de decidir.*
