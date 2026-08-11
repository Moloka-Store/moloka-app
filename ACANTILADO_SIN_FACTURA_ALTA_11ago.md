# EL ACANTILADO SIN MODELO: quién tiene factura del lado alto y quién no

**11-ago-2026.** Medido por SQL de solo lectura contra producción. **Nada aplicado.**

---

## 0. POR QUÉ ESTE DOCUMENTO SUSTITUYE AL DISEÑO ANTERIOR

El diseño en tres niveles (factura → familia de tamaño → desconocido) **se cae**, porque el nivel
del medio no existe: **no hay familia deducible.**

🔬 **Refutado con datos** (los aportó Fernando; confirmado por mi parte con los SKU que tienen fee
facturado desde el 1-abr):

| Tramo de fee | SKU | `item_volume` de mínimo a máximo |
|---|---|---|
| 3,7 € | 12 | 0,0004 – 0,0006 |
| **4,0 €** | **50** | **0,0004 – 0,0077** |
| 4,2 € | 9 | 0,0017 – 0,0026 |
| **4,3 €** | **42** | **0,0005 – 0,0040** |
| **4,6 €** | 26 | **0,0010 – 0,0036** |
| **4,9 €** | 13 | **0,0012 – 0,0045** |

Los tramos 4,0 · 4,2 · 4,3 · 4,6 · 4,9 **se solapan enteros** en la banda 0,0012–0,0036. Un volumen
de 0,0018 cae dentro de cinco tramos a la vez. Con `paq_peso_g` pasa igual: 168 g aparece en 4,5,
en 5,3 y en 6,1.

🔑 **Conclusión: `item_volume` no predice el tramo, y `paq_peso_g` tampoco.** La familia de tamaño
no es derivable de lo que hay en la base. Yo había dejado la hipótesis marcada como *no comprobada*
antes de construir sobre ella — y menos mal, porque era falsa.

---

## 1. EL DISEÑO QUE QUEDA: DOS NIVELES

1. **FACTURA** — donde la haya para ese SKU **a ese lado del escalón**.
2. **DESCONOCIDO** — todo lo demás. **Explícito, nunca rellenado.**

Y de ahí sale la regla operativa, que es **más simple que el modelo que estábamos construyendo**:

> ### 🔑 REGLA
> **Si una recomendación cruza los 20 € y no hay factura del lado alto para ese SKU, no se emite
> con margen: se emite como NO CALCULABLE.**

**El acantilado deja de necesitar un modelo. Solo necesita saber decir «no lo sé».**

Esto es mejor que el diseño de tres niveles por tres razones, y ninguna es de elegancia:

- **No hay nada que estimar, así que no hay nada que pueda estar mal.** Un tramo extrapolado por
  familia habría sido, otra vez, un número inventado indistinguible de uno medido — el `0,1550`
  con otro traje.
- **Se autorrepara con el uso.** Cada venta por encima de 20 € convierte un «no lo sé» en factura.
  La cobertura sube sola sin que nadie mantenga una tabla de familias.
- **Falla en la dirección segura.** Un «no calculable» hace que no se recomiende una subida; una
  familia mal asignada la recomienda con un margen falso. Lo primero cuesta una oportunidad; lo
  segundo cuesta dinero.

---

## 2. EL CENSO: cuántos pueden y cuántos no

Universo repreciable: **176** (activo + stock FBA + ASIN).

| | Productos | |
|---|---|---|
| **Con factura del lado alto (≥ 20 €)** | **72** | 40,9 % — sobre éstos SÍ se puede calcular una subida que cruce |
| **Sin factura del lado alto** | **104** | 59,1 % — sobre éstos, **NO CALCULABLE** |
| *de los 104: hoy por debajo de 20 €* | **76** | ⬅ **la lista del apartado 3** |
| *de los 104: ya por encima de 20 €* | 2 | no cruzan hacia arriba |
| *de los 104: sin precio en `salud_fba`* | 26 | no se puede ni situar |
| **Con el par COMPLETO medido** (ambos lados) | **29** | el escalón está medido al céntimo |

### 🔴 Cuántos están de verdad expuestos hoy

El cerebro topa las subidas en **+10 % por pasada** (`ESCALON_SUBIDA`), así que solo cruzan en una
pasada los que estén en **18,18 € o más**:

| | |
|---|---|
| **Cruzan en UNA pasada** (precio ≥ 18,18 €) | **🔴 35** |
| — de ellos, **clavados en 19,99 €** | **19** |
| Alcanzable en dos pasadas (15 – 18,18 €) | 11 |
| Lejos (< 15 €) | 30 |
| **Unidades de stock en los 35** | **586** |

**19 productos están a UN CÉNTIMO del escalón y ninguno tiene factura del lado alto.** Cualquier
subida que se les proponga cruza, y hoy el margen que se calcularía para esa subida es inventado.

---

## 3. LA LISTA — los 76 sobre los que hoy no se puede recomendar una subida que cruce

Ordenados por proximidad al escalón. `v<20` = ventas facturadas por debajo de 20 € (lo que sí
sabemos); del lado alto no hay ninguna, por definición de esta lista.

### 🔴 Grupo A — cruzan en UNA pasada (precio ≥ 18,18 €) · 35 productos

| ASIN | Producto | Precio | Stock | v<20 | fee bajo |
|---|---|---|---|---|---|
| `B0D98TXCT5` | FUNKO POP League of Legends Jhin 1081 | 19,99 | 20 | 13 | 3,91 |
| `B0CNCZPH6V` | Funko Pop! Dracula – Universal Monsters | 19,99 | 12 | 1 | 3,97 |
| `B0FMF9N3VT` | One Piece POP!&Buddy Animation | 19,99 | 4 | 5 | 4,25 |
| `B0CLFNMZVB` | FUNKO POP Shrek 30th Shrek w/Snake 1594 | 19,99 | 33 | 25 | 4,25 |
| `B00TQ5S6D8` | Funko POP! 06 Lord Voldemort | 19,99 | 32 | 5 | 3,91 |
| `B0CLFGBNN8` | FUNKO POP Shrek 30th Gatto con Stivali | 19,99 | 9 | 21 | 3,97 |
| `B0CLF89N8Z` | FUNKO POP The Pink Panther 1551 | 19,99 | 5 | 1 | 3,97 |
| `B0CGH8Q2KK` | FUNKO POP Harry Potter Azkaban w/Broom | 19,99 | 3 | 3 | 3,97 |
| `B0CYCJ828R` | Funko Pop! Ahri – League of Legends | 19,99 | 11 | 1 | 4,24 |
| `B0D98TB3QW` | Funko POP! Akali – League of Legends | 19,99 | 16 | 17 | 4,24 |
| `B0DSWFXBZZ` | POP! Vinyl – Lingering Will | 19,99 | 11 | 3 | 4,25 |
| `B09S8P7L7H` | FUNKO POP E.T. in Disguise 1253 | 19,99 | 23 | 18 | 4,25 |
| `B07MZPS562` | Funko POP! Vegeta DBZ | 19,99 | 13 | 5 | 3,97 |
| `B08HGXZQ7P` | FUNKO POP MLS Inter Miami Messi 01 | 19,99 | 12 | 12 | 3,91 |
| `B0CND2J282` | Funko UP S2 Rusell 1479 | 19,99 | 8 | **0** | — |
| `B0BBZC4BVJ` | FUNKO POP Star Wars Chewbacca 596 | 19,99 | 12 | **0** | — |
| `B09V85QCNN` | Bridgerton POP! Penelope | 19,99 | 27 | 38 | 3,97 |
| `B07HB4VNVV` | Funko POP! 495 Mufasa – El Rey León | 19,99 | 2 | 10 | 4,25 |
| `B07HB8HGSZ` | FUNKO POP Dragon Trainer 3 Toothless 686 | 19,99 | 4 | 9 | 4,19 |
| `B079TGNNW4` | Funko POP! Tamatoa – Vaiana | 19,95 | 10 | 2 | 4,18 |
| `B08HJD3J9S` | FUNKO POP KPop Demon Hunters Jinu w/Chase | 19,95 | 64 | 57 | 4,25 |
| `B07MZQ36RG` | FUNKO POP Dragon Ball Z Goku 615 | 19,95 | 4 | 11 | 4,19 |
| `B079TL5728` | Funko POP! Deadpool in Scooter | 19,90 | 19 | 25 | 4,25 |
| `B097YP7DH8` | FUNKO POP DB Super Saiyan Rose Goku | 19,90 | 24 | 7 | 4,25 |
| `B09VY4D9H9` | Funko Espeom 884 | 19,90 | 12 | **0** | — |
| `B0D5P7D1RX` | Funko Pop! Chica with cupcake – FNAF | 19,90 | 10 | 20 | 3,91 |
| `B0CND2BXHN` | FUNKO POP Universal Monsters Frankenstein | 19,80 | 11 | 5 | 4,25 |
| `B08HH5V55W` | **FUNKO POP Astro Bot 1089** | 18,99 | 24 | 14 | 3,97 |
| `B0D19MTH5X` | FUNKO POP Dragon Ball Goku w/Tail 1780 | 18,99 | 22 | 2 | 4,24 |
| `B01LAMQ14A` | Enredados POP! Rapunzel | 18,99 | 20 | 14 | 4,25 |
| `B07HBKP7YD` | Funko POP! 498 Pumba – El Rey León | 18,99 | 33 | 13 | 4,25 |
| `B07D58Y2K5` | FUNKO POP Animali Fantastici 2 Newt | 18,99 | 7 | 4 | 3,94 |
| `B0D19NY8ZP` | FUNKO POP Icons Charlie Chaplin 79 | 18,60 | 27 | 17 | 4,24 |
| `B01GIE0QSM` | Crema Adhesiva Protefix 47 g | 18,49 | 30 | 23 | 4,42 |
| `B0CND1XCGZ` | FUNKO POP Rocks Guns N' Roses Slash | 18,19 | 12 | **0** | — |

📌 **`B08HH5V55W` (Astro Bot) está aquí**, y es el caso que veníamos usando: a 18,99 € con fee
facturado de 3,97 € por debajo, y **ninguna venta por encima de 20 €**. Su recomendación de julio
proponía cruzar a 20,37 € con un margen calculado sobre la tarifa de abajo. Con la regla nueva,
esa recomendación sale como **no calculable** — que es la verdad.

📌 **Cinco no tienen factura de NINGÚN lado** (`v<20` = 0): `B0CND2J282`, `B0BBZC4BVJ`,
`B09VY4D9H9`, `B0CND1XCGZ` y —fuera del grupo A— `B0CYCFSBK4`. De ésos no se conoce el fee ni por
debajo: son *desconocido* entero, no solo del lado alto.

### 🟠 Grupo B — alcanzable en dos pasadas (15 – 18,18 €) · 11 productos

`B0DP7BVGBC` KISS POP! The Catman 17,99 · `B0DSWJF579` Pop! Pugsley Addams 17,99 ·
`B0G1N24FDJ` FUNKO Hello Kitty Kuromi Flocked 17,99 · `B0CYCFSBK4` FUNKO Pokemon Alolan Raichu 17,95 ·
`B0FGVPH16L` Sonic POP! Games 17,90 · `B0DSWH7FTR` Garfield POP! Comics 16,99 ·
`B0CVNLPB83` One Piece Roronoa Zoro w/Chase 16,95 · `B089G8S9QZ` Premium POP! Protector Box 15,99 ·
`B08HJ6L3PJ` Lilo & Stitch Stitch in Rocket 15,99 · `B08HGPT8YG` POP! Pennywise (1990) 15,99 ·
`B0CND11MYH` FUNKO POP Terrifier Art the Clown 15,49

### ⚪ Grupo C — lejos del escalón (< 15 €) · 30 productos

No pueden cruzar en una pasada, así que la regla no les afecta hoy. Se listan para que el censo
cuadre: `B0CPNHGQ8Z` · `B0D98TRMV6` · `B0CGGS785Y` · `B0CCBWG1MJ` · `B07GRRYFL1` · `B0DSWJF592` ·
`B0DSWFBQ73` · `B08MQ91PR9` · `B0CNCZGJ9S` · `B0DNRTN731` · `B0BS1R953M` · `B0BJ7NT9TL` ·
`B0BJ7QSBXC` · `B0BJ7PKM2V` · `B0BJ7PMGHP` · `B0BLT6YQ45` · `B001PASC5E` · `B0BDJ3J2YC` ·
`B014JPGAOG` · `B076PFP25F` · `B01GYYJI30` · `B085DNDLC1` · `B0CQRYTQ1R` · `B014DGG0OQ` ·
`B087RWYJN3` · `B0CPH9PSFF` · `B0012PRQE0` · `B00IR0DSG8` · `B0002TT3N4` · `B07MNBKXTH`

---

## 4. LO QUE ESTO CAMBIA EN EL CEREBRO

Hoy `margen_en(px)` recalcula el margen a un precio hipotético manteniendo `fee` fijo. Con la regla
de dos niveles, lo que tiene que hacer es **preguntar si sabe el fee a ese precio**:

- Si el precio objetivo está **al mismo lado** del escalón que el precio actual → el fee facturado
  vale, y el margen se calcula como hoy.
- Si **cruza** y hay factura del lado alto → se usa **esa**, y el margen es real.
- Si **cruza** y no la hay → **`accion = NO_CALCULABLE`**, sin `precio_objetivo` y sin
  `margen_objetivo_pct`. No se propone la subida.

🔑 Ojo a un efecto de segundo orden que conviene tener escrito: **esto reduce lo accionable a corto
plazo**. Las 8 recomendaciones pendientes que cruzan (172,77 €/mes prometidos) pasarían a no
calculables. **No es una pérdida: es dinero que nunca estuvo ahí** — estaba calculado sobre una
tarifa que no aplicaba.

---

## 5. MÉTODO QUE DEBE QUEDAR EN LA DOCTRINA

> 🔒 **Para separar un escalón de precio de una subida general de tarifas: el grupo de control son
> los que NUNCA cruzan.**
>
> Medido el 11-ago-2026: 55 SKU vendidos **siempre** por debajo de 20 € (9.267 movimientos, o sea
> sin acantilado posible) dan mediana ene-mar **3,63 €** y jun-ago **3,69 €** — **+0,06 € en seis
> meses**. Con eso queda descartado que el salto observado al cruzar fuese un cambio del calendario
> de tarifas de Amazon, y el escalón se sostiene: 18 de 21 SKU suben, media **+0,55 €**.
>
> 🔴 **Y el mismo método destapó un falso máximo:** el salto de **+2,53 €** de `68-SW97-Z5WF`
> comparaba **una** venta del 19-mar contra ventas de may-jun. Con n=1 y meses de por medio no mide
> el escalón, mide el ruido. El máximo honesto es **+0,79 €**.
>
> **La regla general: antes de atribuir una diferencia a la causa que buscas, mide el mismo periodo
> en un grupo donde esa causa no puede actuar.** Si allí también aparece, no era tu causa.

*(Va a `monitor_doctrina`. No lo escribo yo: desde una sesión Supabase es solo lectura.)*

---

*Medido el 11-ago-2026. El estado de una base caduca en horas: revalidar antes de decidir.*
