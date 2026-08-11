# «Stock muerto»: la definición canónica

**Decidida el 11-ago-2026.** Fernando pidió elegir un corte y que todo lo que salga de aquí
en adelante lo use, porque había **tres cifras circulando** —8.677 €, 3.550 € y 11.064 €— y
ninguna decisión se puede anclar así.

🔴 **Todo número de «stock muerto» cita esta definición y su FECHA, o no se cita.** El importe
es del día que lo mires: lo que no cambia es el criterio.

---

## La definición

Una ficha (por **ASIN**, sumando todas sus vidas de SKU) es **stock muerto** cuando cumple
las cuatro:

| | criterio | por qué |
|---|---|---|
| 1 | `sum(available) > 10` | **Puerta de volumen.** Sin ella una ficha de 1 unidad pesa igual que una de 90, y la lista se llena de ruido que nadie va a tocar. |
| 2 | `sum(units_shipped_t30) <= 2` **o NULL** | **Filtro de rotación.** El NULL entra —es un candidato— pero **no se mezcla**: ver «las dos partes». |
| 3 | `productos.activo` | Un producto retirado no es stock muerto: es stock retirado. |
| 4 | **el extracto no lo desmiente** | Se descarta toda ficha que `transacciones_movimientos` diga que vendió **más de 2** en 30 días. |

Y **el resultado se presenta SIEMPRE partido en dos**, nunca sumado en un solo número:

- **CONFIRMADO** — `units_shipped_t30` conocido y ≤ 2. Sabemos que no vende.
- **SIN SABER** — `units_shipped_t30` a NULL. **No sabemos**, y decirlo es parte del dato.

### Lo medido el 11-ago-2026

| | fichas | coste |
|---|---|---|
| **Bruto, pasos 1-3** · CONFIRMADO | 50 | 8.149,69 € |
| **Bruto, pasos 1-3** · SIN SABER | 21 | 2.896,65 € |
| **Bruto (1.794 uds)** | **71** | **11.046,34 €** |
| *menos lo que el extracto desmiente (paso 4)* | *−10* | *−1.556,13 €* |
| **STOCK MUERTO** · CONFIRMADO | **41** | **6.758,02 €** |
| **STOCK MUERTO** · SIN SABER | **20** | **2.732,18 €** |
| **STOCK MUERTO · TOTAL** | **61** | **9.490,20 €** |

⚠️ **Las dos filas del final son las que se citan**, no el total. Y nunca sin decir que
2.732,18 € son de fichas sobre las que **no sabemos**, no de fichas que sepamos muertas.

---

## Por qué el paso 4, que no estaba en la propuesta

🔬 **Sin él la cifra sale un 16 % inflada.** El extracto dice que **10 fichas vendieron más
de 2 unidades en 30 días** mientras `units_shipped_t30` decía que ≤2 o NULL: **1.556,13 €**
que se habrían declarado muertos sin estarlo (9 del cubo CONFIRMADO por 1.391,66 € y 1 del
SIN SABER por 164,47 €).

`units_shipped_t30` es de donde salen los NULL; **el extracto no tiene ese agujero**. Cuando
las dos fuentes discrepan sobre si algo se vendió, gana el extracto: es el libro de asientos,
no una métrica de panel.

⚠️ Y no se «promedian» ni se elige la que convenga (§1.3): la discrepancia **es un dato**, y
esas 10 fichas merecen mirarse por sí solas.

🔒 **Al revés, el cruce también confirma:** de las 21 fichas «sin saber», **17 no tienen
rastro en el extracto** ni en 30 ni en 90 días. Ahí las dos fuentes dicen lo mismo y el «no
sé» se convierte, con pruebas, en «no vende».

---

## Las dos funciones de la alerta de Amazon, que NO se contradicen

Aquí hubo un cruce de cables entre Fernando y yo, y las dos observaciones eran correctas
porque **hablan de pasos distintos del mismo cálculo**:

- 🔴 **`salud_fba.alert` NO es criterio de SELECCIÓN.** Filtrar por él perdería **10 fichas y
  1.428 €** que están paradas sin que Amazon las haya marcado. Medido sobre el stock TOTAL,
  las 53 fichas sin alerta acumulan más unidades (3.834) que las 146 de *Low traffic* — pero
  eso **no es un problema, es el negocio funcionando**: 38 de esas 53 venden más de 2 al mes
  y ninguna vende cero. Stock que rota no es stock muerto.
- ✅ **`salud_fba.alert` SÍ es el DIAGNÓSTICO de lo que el filtro de rotación ya encontró.**
  Sobre el stock ya filtrado, **el 87 % de lo parado está en fichas que Amazon ya había
  marcado**: *Low traffic* 6.509,66 € · *Low conversion* 3.126,95 € · sin alerta 1.427,99 €.

**Primero se selecciona por rotación; después se diagnostica por alerta.** Nunca al revés.

### Y los dos cubos de alerta no se suman NUNCA

Piden tratamientos **opuestos**, y no es doctrina: es que son animales distintos. Medido:

| | fichas | t30 NULL | t30 = 0 | t30 1–2 | **t30 > 2** |
|---|---|---|---|---|---|
| **Low traffic** | 146 | 29 | 21 | 31 | **65** |
| **Low conversion** | 23 | 10 | 13 | 0 | **0** |

Las 23 de *Low conversion* tienen t30 **NULL o cero, las 23 sin excepción**. En *Low traffic*,
**65 de 146 venden más de 2**. Son «no la ve nadie» contra «la ven y no la compran»: la
primera se arregla con visibilidad y precio, la segunda con la ficha, la foto o el producto.
Sumarlas da un número que no significa nada.

🔑 **Y los NULL no están repartidos al azar:** los **39** con `units_shipped_t30` a NULL están
**todos dentro de una alerta** —29 en *Low traffic*, 10 en *Low conversion*, **cero** en las
limpias—. Amazon deja de reportar justo donde ya ha marcado el problema. Por eso el NULL
entra como candidato y por eso va declarado, nunca como cero.

---

## Las perillas que se decidieron, y lo que costó cada una

| perilla | decisión | medido |
|---|---|---|
| `available` vs `available + fc_transfer` | **`available` solo** | Con `fc_transfer`: 77 fichas y 12.270,88 €. **+6 fichas, +1.224,54 €.** Se deja fuera porque el FC Transfer es stock que Amazon mueve entre sus centros: no dice nada sobre si el producto se vende, y mezclarlo confunde «nadie lo compra» con «está en una furgoneta». **Pero se declara como línea aparte, no se esconde.** |
| ¿meter también los 90 días? | **NO en la definición** | Exigir además `t90 <= 6` dejaría 54 fichas y 8.094,14 €: quitaría **17 fichas y 2.952 €** que venden flojo a 30 días y bien a 90. Eso no es muerto, es **irregular**, y el tratamiento es otro (calendario de reposición, no liquidación). Va como **segundo eje del informe**, no como filtro. |
| `productos.activo` | **se queda** | 🔬 Hoy **no quita ni una ficha**: los 71 candidatos están activos. Se dice expresamente para que nadie crea que está haciendo trabajo — es una guarda para el futuro, no un filtro vivo. |

---

## Las tres cifras que circulaban, reconciliadas

| cifra | qué era en realidad |
|---|---|
| **11.064 €** (Fernando) | Este corte, pasos 1-3. Mi medida da **11.046,34 €**: 18 € de diferencia por los **7 ASIN con más de una ficha en `productos`**, donde el `max(pvd)` desempata distinto. |
| **3.550 €** (mía, «sin saber») | La parte SIN SABER **contando `fc_transfer`** (3.550,25 €). No era otro universo: era otra perilla. |
| **8.677 €** (mía, «confirmadas») | De una medida anterior con otro corte. **Queda derogada**: con esta definición, el confirmado son **8.149,69 €**. |

---

## 🔴 La trampa que casi cuela un cero, y que va a repetirse

Al cruzar con el extracto la primera vez salió **«71 de 71 sin rastro»**. No era un hallazgo:
era que el filtro decía `tipo_norm = 'Pedido'` y el valor real es **`'pedido'`, en minúscula**.
Cero filas casadas → cero ventas → «todo muerto».

**Un 100 % no es un resultado, es un síntoma.** Un filtro que no casa nada no da error: da
un cero perfectamente plausible que apunta justo en la dirección que uno esperaba. Es el
mismo patrón que el informe caducado (§1.4) y que la vista que no puede ver su fuente.
Antes de creerse un extremo —0 % o 100 %—, se comprueba que el cruce cruza.

---

## El SEGUNDO EJE: el `sales_rank`, al lado de la alerta

🔑 **Un producto con rank 726 y cero ventas no es lo mismo que uno con rank 82.000 y cero
ventas.** El primero tiene demanda demostrada y el problema es NUESTRO; el segundo
sencillamente no le interesa a nadie. Sin el rank al lado, los dos parecen el mismo caso.

🔬 Sobre las **41 confirmadas** (11-ago-2026), el rank las parte en tres montones **casi
iguales de dinero** y de diagnóstico opuesto:

| tramo (`salud_fba.sales_rank`) | fichas | uds | coste | Low **conversion** | Low **traffic** | sin alerta |
|---|---|---|---|---|---|---|
| **≤ 5.000** · demanda demostrada, el problema es nuestro | 7 | 281 | **2.174,96 €** | **4** | 1 | 2 |
| 5.000 – 20.000 · intermedio | 14 | 410 | 2.206,55 € | 4 | 6 | 4 |
| **> 20.000** · no interesa a nadie | 18 | 361 | **2.216,75 €** | 1 | **16** | 1 |
| sin rank | 2 | 26 | 159,76 € | 0 | 1 | 1 |

🔒 **Y aquí hay una confirmación que nadie puso a mano:** *Low conversion* se concentra donde
el rank es BUENO (4 de 7 en el tramo fuerte) y *Low traffic* donde es MALO (16 de 18 en el
flojo). La alerta de Amazon y el rank son dos señales independientes y dicen lo mismo. Eso
es lo que convierte la separación de los dos cubos de §alerta en un hecho, no en doctrina.

⚠️ **DOS FUENTES DE RANK, Y NO SE PROMEDIAN** (§1.3). `salud_fba.sales_rank` y
`keepa_escaparate.rank` son informes distintos tomados en momentos distintos, y discrepan
bastante: Lenor **18.343 vs 9.346**, Coco Miguel **29.245 vs 16.284**, Salah 45.338 vs
56.755. **La vista usa `salud_fba.sales_rank`**, porque vive en la misma fila que `alert` y
que las unidades — la comparación con la alerta sería tramposa si viniera de otra foto.
Citar «rank 726» sin decir de cuál de los dos es, es citar a medias.

---

## Lo NO-COLECCIONABLE: el patrón NO aguanta

Fernando pidió marcar lo no-coleccionable, con la hipótesis de que si el patrón se sostenía
al mirar el cubo entero no sería un problema de fichas sueltas sino de **línea de negocio**.
🔬 Medido sobre las 41: **no se sostiene.**

| categoría (Keepa ES) | fichas | coste | marcas |
|---|---|---|---|
| **Juguetes y juegos** | **34** | **5.297,59 €** | Funko, Hasbro, Hot Wheels, Magic |
| Hogar y cocina | 1 | 472,38 € | **BANDAI SPIRITS** |
| Alimentación y bebidas | 3 | 464,13 € | David Rio, HARIBO, Ricola |
| Salud y cuidado personal | 1 | 413,82 € | LENOR |
| (sin ficha Keepa ES) | 1 | 93,96 € | — |
| Videojuegos | 1 | 16,14 € | AMBROSIANA |

**83 % de las fichas y 78 % del dinero está en el núcleo coleccionable.** Lo no-coleccionable
son ~5 fichas y ~894 € — el **13 %**. Y de los tres de más coste, el mayor —Starter Kit de
Magic, 893 €, el 53 % de esos 1.649 €— **es** coleccionable: son dos de tres, no tres.

🔑 Y el rank lo remata: los coleccionables están en **los dos extremos** (6 de 7 en el tramo
de demanda fuerte, 17 de 18 en el de nadie los quiere). La categoría no separa nada.

⚠️ **Y la categoría de Amazon no vale como marcador tal cual:** la única ficha de «Hogar y
cocina» es un **BANDAI SPIRITS**, un model kit que Amazon clasifica ahí. Marcar por categoría
llamaría «no coleccionable» a un Bandai. Si algún día hace falta el marcador, sale de la
MARCA o de una lista de Fernando, no de `keepa_escaparate.categoria`.

---

## Cómo se recalcula (no se copia)

```sql
with f as (
  select asin, sum(coalesce(available,0)) av, sum(units_shipped_t30) t30
  from salud_fba group by asin
), p as (
  select asin, bool_or(activo) activo, max(pvd) pvd
  from productos where asin is not null group by asin
), cand as (
  select f.asin, f.av, f.t30, p.pvd, (f.t30 is null) sin_saber
  from f join p on p.asin = f.asin
  where f.av > 10 and (f.t30 is null or f.t30 <= 2) and p.activo
), puente as (
  select distinct sku, asin from salud_fba where sku is not null
), ventas as (
  select pu.asin, sum(abs(t.cantidad)) filter (where t.fecha >= (select max(fecha) from transacciones_movimientos) - 30) uds_30
  from transacciones_movimientos t
  join puente pu on pu.sku = t.sku
  where t.tipo_norm = 'pedido'          -- 🔴 minúscula
  group by pu.asin
)
select case when c.sin_saber then 'SIN SABER' else 'CONFIRMADO' end parte,
       count(*) fichas, round(sum(c.av * c.pvd), 2) eur
from cand c left join ventas v on v.asin = c.asin
where coalesce(v.uds_30, 0) <= 2        -- paso 4: el extracto no lo desmiente
group by 1 order by 1;
```

🔒 El puente SKU→ASIN va por `salud_fba` porque **el extracto sólo trae SKU y el SKU no es
llave maestra** (§1.1). 🔬 Casan 192 de los 313 SKU del extracto: los que faltan son vidas
muertas de SKU que ya no están en la foto de inventario.

⚠️ La ventana de 30 días se cuenta desde `max(fecha)` del extracto, **no desde hoy**: el
extracto va por detrás (hoy llega al 9-ago) y usar `current_date` recortaría dos días de
ventas en silencio.
