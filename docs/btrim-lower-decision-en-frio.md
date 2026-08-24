# Los `btrim()`/`lower()` de `salud_fba`: la decisión que se toma EN FRÍO

**Esto NO se hace hoy.** Es la nota que pidió Fernando el 24-ago-2026, el día que el LATERAL de
Keepa tumbó la pestaña Inventario y se arregló con un índice funcional
(`migraciones/2026-08-24_keepa_indice_lateral_salud_fba.sql`, PR #198). Todo lo de aquí está
**medido en producción ese día**; lo que no se pudo medir se dice.

---

## 0. La pregunta

`salud_fba` cierra con un LATERAL que envuelve las dos columnas del filtro:

```sql
WHERE btrim(ke.asin) = btrim(i.asin) AND lower(ke.dominio) = 'es'
```

Envueltas en funciones, las columnas dejan ciego a todo índice — incluido el PK
`UNIQUE (asin, dominio)` de `keepa_escaparate`. **Si se quitaran los envoltorios, el PK haría el
trabajo solo y el índice funcional sobraría.** ¿Se pueden quitar?

---

## 1. La respuesta corta

**Hoy son INERTES. Pero «inerte» no es «se puede quitar», y la diferencia está medida.**

Quitarlos no pierde ninguna garantía **porque no había ninguna**: la limpieza no la impone la
base, la impone un `.strip()` de Python. Quitarlos cambia *redundante* por *apostado*.

---

## 2. Lo que se midió, y por fin los DOS lados

El 24-ago por la mañana solo se había medido `keepa_escaparate`. Fernando señaló que el `btrim`
se aplica **también a `inventario_fba.asin`**, y que ese lado no estaba medido. Tenía razón, y
ése era el lado que decide. Ya está medido:

| columna | filas | difieren de `btrim` | fuera de caja |
|---|---|---|---|
| `inventario_fba.asin` ← **el que faltaba** | 354 | **0** | 0 |
| `keepa_escaparate.asin` | 1.653 | 0 | 0 |
| `keepa_escaparate.dominio` | 1.653 | 0 | 0 (4 valores: de/es/fr/it) |
| `v_ventas_ventanas.asin` | 292 | 0 | 0 |
| `listings_amazon.seller_sku` / `.asin` | 382 | 0 | 0 |
| `transacciones_movimientos.sku` | 16.685 | 0 | (1.007 NULL) |
| `ledger_movimientos.asin` | 20.191 | 0 | 0 |

🔑 **Y la prueba que de verdad decide, que no es contar espacios sino contar EMPAREJAMIENTOS:**
sobre las 354 filas de `inventario_fba`, el LATERAL empareja **339 con los envoltorios y 339 sin
ellos. 0 filas cambian.** Y no cambia bajo *ninguna* normalización: exacto 339 = `btrim` 339 =
ignorando caja 339 = recorte ancho (tab/CR/LF/NBSP) 339 = solo alfanuméricos 339. Los 14 que no
casan no los recupera nada: son ausencias reales (no tienen ficha de Keepa en `es`).

🔒 **La comprobación PUEDE ponerse roja, y se comprobó rompiéndola a mano** (§3, las dos
direcciones): inyectando un espacio en el lado inventario, el cruce exacto cae de 339 a **0** y
el de `btrim` se queda en 339. O sea que el «0 filas cambian» es una medición, no un verde
prestado.

📏 Y el `ORDER BY ke.fecha_foto DESC LIMIT 1` del LATERAL **no desempata nunca**: sobre 1.653
pares `(asin, dominio)`, el máximo de filas por par es 1 — lo garantiza el PK. Es decorativo.

---

## 3. Por qué esto NO es un «sí», con las dos objeciones medidas

### 3.1 🔴 La limpieza NO es una propiedad de la casa: hay 454 contraejemplos vivos

El argumento cómodo es *«no es suerte, lo garantiza el `_clean()` de los procesadores»*. **Eso
es cierto de `procesador_inventario_fba.py` y falso de la casa.** Censo del esquema entero —544
columnas de texto, 75 tablas, 1.051.781 valores no nulos— y salen **tres columnas sucias**:

| columna | no nulos | con blanco en los extremos | con NBSP |
|---|---|---|---|
| `escaner_detalle.nombre` | 5.412 | **444** | **6** |
| `escaner_chase_asin.nombre` | 106 | 1 | 0 |
| `bak_viewdefs.definicion` | 9 | 9 | 0 |

*(Las cifras de `escaner_detalle` se volvieron a medir a mano antes de escribir esto: 5.412 /
444 / 6. No es un dato de segunda mano.)*

Y **no es un resto histórico**: 19-ago 129 sucias de 1.608 · 12-ago 153 de 1.680 · 5-ago 153 de
1.767. El escritor está vivo y es de este repo: `moloka_escaner_nube.py:1031` guarda
`'nombre': row.get(cN,'')` **crudo, sin `strip()`** — en el mismo fichero que avisa en la línea
930 de que *«BEMS trae espacios en los nombres»*.

🔑 O sea: **la suciedad de la clase EXACTA que el `btrim` caza existe hoy en producción, escrita
por un procesador Python de esta casa.** Apoyar el borrado en «los procesadores limpian» es
apoyarse en algo que tiene 454 contraejemplos.

### 3.2 🔴 El lado que decide tiene una muestra de n=1

`inventario_fba` tiene **UNA sola foto**: 354 filas, **1 `fecha_foto` (23-ago-2026), 1 fichero**.
La cañería nació el día antes. Contraste: `keepa_escaparate_hist` lleva 9.331 filas, **14 fotos
y 51 ficheros** (20-jul → 23-ago).

O sea que la cifra que desbloquea la decisión —«`inventario_fba.asin` no trae ni un espacio»— se
ha medido sobre **una pasada de un procesador de un día de vida**. Es exactamente el aviso de
CLAUDE.md §2 sobre ese mismo fichero: heredar supuestos sobre él (el peso «97-107 KB») habría
rechazado el fichero bueno.
*Atenuante honesto:* `inventario_internacional_historico` —otro TSV del Seller con ASIN— lleva
3.153 filas y 10 fotos con 0 sucias. Es evidencia de que esa familia de ficheros no ensucia,
pero de otro informe y otro procesador.

### 3.3 🔴 Y si fallara, NO lo caza nadie

Ésta es la peor de las tres, porque convierte un fallo raro en un fallo **mudo**:

- **En la base no hay nada que se ponga rojo.** Censo de vistas, funciones, CHECK y triggers que
  condicionen algo a `sales_rank`: **0**. Es columna de paso en los 11 objetos que la mencionan.
- **Los testigos que YA existen salen verdes con el dato destruido.** El bloque de verificación
  de `2026-08-23_salud_fba_pasa_a_vista.sql` comprueba 6 cosas y **ninguna mira `sales_rank`**.
  Un PR que reutilice ese bloque —lo natural— saldría **VERDE con las 354 filas a NULL**. Es el
  patrón de §3: *la comprobación que mira lo que no cambia*.
- **Los tests de la v2 tampoco.** Los 23 suites que citan `sales_rank` lo **inyectan ellos mismos
  como fixture**. Prueban el builder, no que la base entregue el dato. Es
  «medir por `cargarInventario`, no por `construirInventario`» otra vez.
- **Y el fallo realista no es ruidoso.** No es 339→0: es **una fila** con un espacio, 339→338, un
  0,28 % que aterriza junto a los 15 NULL que YA existen (4,24 %) y que la vista no distingue.
  Ninguna guarda de recuento se mueve: `inventario_fba` sigue en 354 filas y `keepa_escaparate`
  en 1.653.

⚠️ Eso **invierte** el argumento: el `btrim` no es una redundancia, es la única **tolerancia** que
hay. Hoy la casa tiene tolerancia y cero detección. Quitarlo deja **cero tolerancia y cero
detección**.

---

## 4. Qué convertiría el «no» en un «sí»

En este orden. Las tres primeras son las que cambian la respuesta.

1. **El CHECK, y verlo saltar.** Que el mismo PR añada
   `CHECK (asin = btrim(asin))` a `inventario_fba` y a `keepa_escaparate`, más
   `CHECK (dominio = lower(dominio))`. Eso **muda la garantía del SQL a la base**, que es donde
   hoy no está: las dos tablas tienen **0 CHECK y 0 triggers**. Y mueve el fallo del sitio mudo
   (`sales_rank` a NULL) al sitio que grita (el momento de escribir).
   🔴 **No basta con escribirlo: hay que hacerlo saltar a propósito en staging** con un insert de
   `'B01234567 '`. Un CHECK que solo se ha visto en verde no se ha probado.
   ⚠️ Y falta una cosa que nadie midió: **qué pasa el día que salte.** Una violación de CHECK no
   es un `Aborta` de la casa — sale como excepción de `psycopg2` dentro del `execute_values`, con
   todo el lote en un solo comando. Hay que saber si deja la foto de ayer intacta o la tabla a
   medias, y si el mensaje es legible.
2. **Una segunda (y tercera) foto de `inventario_fba`.** Repetir el contraste 339-vs-339 sobre
   varias pasadas convierte n=1 en una serie. Mejor aún: **instrumentar `_clean()` para que
   GRITE cuántas celdas ha recortado** — hoy recorta y calla, así que el trabajo que hace es
   invisible y no hay forma de saber si la fuente ensucia.
3. **La huella md5 de `salud_fba` antes y después** — copiando el bloque de
   `2026-08-24_keepa_indice_lateral_salud_fba.sql`, **no** el de la migración de la vista. Y un
   assert de **cobertura**, no de «≠0 filas»:
   `select count(*), count(sales_rank) from public.salud_fba` → hoy **354 / 339 (95,76 %)**, que
   aborte si baja del suelo. Hoy no existe en ningún sitio.
4. **Decidir a la vez el SEGUNDO `btrim` de la misma vista.** `salud_fba` tiene además
   `LEFT JOIN v_ventas_ventanas v ON btrim(v.asin) = btrim(i.asin)`, y `v_ventas_ventanas` usa
   `btrim` tres veces más por dentro. Si el PR toca uno solo, queda medio arreglado y con dos
   criterios para el mismo dato.
5. **El `DROP INDEX` va DESPUÉS, no en la misma migración**, hasta que el CHECK esté vivo y
   medido. `idx_keepa_asin_dominio_foto` es hoy lo único que sostiene la pestaña: una vuelta
   atrás sin él vuelve a tumbar Inventario.

---

## 5. 🔴 El hallazgo que no se buscaba: el mismo bug está vivo y es PEOR en otro sitio

Censando el patrón por toda la base aparecen otros sitios con columnas envueltas dentro de un
cruce. Dos ya cuestan **más que el bug que tumbó Inventario**, y están vivos hoy
(medido a mano el 24-ago, caché caliente):

| vista | buffers | ms | causa |
|---|---|---|---|
| **`v_keepa_cruce`** | **89.239** | **1.786** | dos EXISTS correlacionados hacen Seq Scan sobre `productos` 1.649 y 1.240 veces por `btrim(p.asin) = btrim(k.asin)`; `idx_productos_asin` queda ciego |
| **`v_salud_fba_cruce`** | **26.038** | **263** | Seq Scan sobre `inventario_fba` repetido 341 veces por `btrim(i_2.asin)=btrim(i.asin)` |
| `salud_fba` *(ya arreglada)* | 3.220 | ~100 | — |

**`v_keepa_cruce` cuesta 28× lo que cuesta `salud_fba` ya arreglada.** Y `productos.asin` está
limpio en sus 470 filas, así que ahí el `btrim` tampoco compra nada.

⚠️ Y uno más por reloj: `v_nunca_enviado_fba`, donde `btrim(la.seller_sku) = btrim(t.sku)`
impide el merge join y fuerza ordenar 15.148 filas de `transacciones_movimientos` — la tabla
mayor (16.685 filas, 52 MB) y **la única que crece sin techo**. Por riesgo estructural es la
primera, aunque hoy no sea la más cara.

🔑 **Y el matiz que evita que alguien «arregle» de más:** los ~20 `btrim(x) <> ''` repartidos por
`v_presencia_pais` y compañía **NO son la misma enfermedad**. Son pruebas de «está en blanco», no
llaves de cruce: ningún índice de igualdad los serviría. Quitarlos no gana nada y podría cambiar
el resultado.

---

## 6. Lo que NO se pudo medir, dicho a la cara

- **El fichero fuente no lo abrió nadie.** Todos los ceros de limpieza miden el `.strip()` de
  `_clean()`, no lo que manda Amazon. Se demostró para el crudo de Keepa (0 blancos en los
  extremos **por construcción**, 152.822 interiores). La única medida que contestaría «¿puede la
  fuente ensuciarse?» es bajar el `.txt` del buzón —`informes/inventario_fba/<fichero>`— y
  contar ANTES de `_clean`. Está a una descarga y no se hizo.
- **El plan que ve Elena no se pudo medir.** `salud_fba` es `security_invoker=true`, así que con
  `authenticated` se aplica la RLS de las tablas de debajo. Desde esta sesión el rol es
  `supabase_read_only_user` con `rolbypassrls=true` y **`SET ROLE authenticated` da
  `permission denied`**. Todas las cifras de plan de este documento son de un rol que salta la
  RLS: valen para comparar entre sí, no para afirmar lo que cuesta la consulta de la app.
- **El censo por uso no se pudo cerrar.** `extensions.pg_stat_statements` se reseteó el
  24-ago a las 07:26:46 UTC, así que la ventana de «quién ESCRIBE de verdad» era de menos de una
  hora. (Sí se puede preguntar «quién LEE y a qué coste», que es otra cosa.)
- **No se midió staging**, que es donde primero se aplicaría el CHECK.
- **No se midieron las tablas históricas** salvo las citadas: pueden traer filas cargadas antes
  de que `_clean()` existiera.
