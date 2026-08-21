# El guion anti-cero

> **¿Qué entrada concreta pondría este recuento a distinto de cero?**

Ésa es la pregunta. Literal, y antes de creerse cualquier verde. Si no hay respuesta —si el
resultado sale igual mida lo que mida— la comprobación **no comprueba nada, y encima
tranquiliza**. Es el peor de los fallos: no da error, da permiso.

Este guion no se lo tiene que imaginar nadie. Los seis casos de abajo están **medidos**, los
seis el 21-ago-2026, y ninguno se buscó: aparecieron haciendo otra cosa.

---

## Cómo se usa

Se le hace a **tres** cosas, no solo a los tests:

| a qué | la pregunta |
|---|---|
| un **test** | ¿qué tendría que romperse para que se pusiera rojo? Rómpelo y míralo. |
| una **guarda** | ¿puede ponerse roja por una causa distinta de la que dice medir? |
| un **medidor** | ¿tenía delante todo lo que la app usa? ¿había población que contar? |

Y tiene **dos direcciones**, siempre. La segunda es la que se olvida:

1. que se ponga **roja** cuando toca — se rompe la cosa a mano y tiene que saltar;
2. que esté **callada** cuando no toca — se corre con todo en orden y tiene que no decir nada.

Una alarma que siempre está roja tampoco informa: se aprende a ignorarla, y el día que salte
por algo de verdad ya nadie la lee.

---

## Los seis casos medidos

### 1 · Una regla escrita que nadie ejecuta

`enviar-por-la-canieria.sql` avisaba **por escrito** desde su día:

> `enviar_a_amazon` va la última y no es opcional: sin ella el script la lee `undefined`, y
> `undefined !== false` da `true` … es de los que no pueden fallar hasta que fallan.

El aviso se escribió **en la consulta** y no se aplicó **en el fichero de al lado**. El
medidor decía **53** donde la pantalla enseña **42**.

⚠️ Y lo que lo hace peor: el mismo comentario añadía *«hoy en producción lo están las
469/469»*. Mientras eso fue cierto, el fallo era **inofensivo**. Empezó a mentir **solo**, el
día que Fernando marcó la primera ficha, sin que nadie tocara el código y sin que nada
saltara.

> **No es un cero: es una regla escrita que nadie ejecuta.** Una regla en prosa se olvida en
> veinte minutos. La única forma de que se aplique es que sea código — ver §3 de CLAUDE.md.

### 2 · El medidor al que le falta la columna del arreglo

Tres veces el mismo día, con la misma forma exacta: `pendiente_evaluacion`, `enviar_a_amazon`
y `v_nunca_enviado_fba`. **La app usa un dato que el medidor no lee, y el medidor no se queja
— da un número.**

Un medidor al que le falta una columna **no mide de menos: mide OTRA PANTALLA**, y la presenta
con la misma cara de siempre.

🔴 Y el falso positivo del **signo contrario**, que es el que más engaña: un extracto al que
le falta la columna del arreglo **mide el bug y lo da por bueno**. Si el medidor de «Enviar»
no trae `pendiente_evaluacion`, mide una pantalla donde la regla del primer envío no se
aplica — y habría dado por bueno el desplome de 289 uds que el arreglo vino a evitar.

**Cerrado en código:** `scripts/verificacion/contrato-extracto.mjs` (moloka-app-v2) deriva las
dos listas —lo que la app lee y lo que el extracto trae— y **aborta** nombrando lo que falta.
Al enchufarlo salieron **dieciséis columnas más** que nadie sabía que faltaban, entre ellas
`v_keepa_bb_envio` entera.

### 3 · Contar filas cuando lo que cambia son las celdas

Al medir el paso a `QUOTE_NONE` de los TSV, cuatro casos sintéticos. El tercero decidió el
encargo:

| | caso | hoy | QUOTE_NONE |
|---|---|---|---|
| A | comilla que **abre** un campo y no cierra | 2 filas | **3 filas** |
| B | comilla en medio (`10" Deluxe`) | igual | igual |
| **C** | **campo entero entre comillas** | `Funko` | **`"Funko"`** |
| D | limpio | igual | igual |

**El C da el MISMO número de filas y distinto valor.** Comparando recuentos habría salido «no
cambia nada» — y el ledger, que trae **cada campo entrecomillado**, se habría roto entero en
sus 24.287 filas.

> Un recuento igual no es un contenido igual. Si lo que puede cambiar es el valor, compara el
> valor.

### 4 · Un cambio inerte no se puede verificar por su resultado

Si el cambio no mueve nada, **todo sale igual esté bien o mal**, y «no ha cambiado nada»
significa las dos cosas a la vez: **que funciona y que no se ha ejecutado**.

**Cerrado en código:** `sql/huella_tablas_foto.sql` devuelve **dos** columnas y hacen falta
las dos — la `huella` del contenido (excluyendo el reloj) dice que es inerte; el `reloj`,
mirado aparte, dice que **corrió**.

🔬 En la verificación real, `salud_fba` enseñó la otra mitad del argumento: su contenido no
cambió *porque no se ejecutó*, y se vio en que su reloj seguía en el 16-ago.

### 5 · Restaurar staging deshace lo del día

El backup es de anoche. Restaurar **deshace lo aplicado a producción hoy**, y justo después
viene un ensayo encima.

> «Puede ser una migración que se aplique **limpiamente** en un staging al que le falta la
> columna con la que iba a chocar en producción.»

Ese ensayo sale **verde sin probar nada**. No es una molestia: es **la escalera mintiendo**, y
la escalera es la única red que hay para no romper la operativa de Elena.

⚠️ Y lo que la demostración destapó vale más que la guarda: esa mañana **se pasó una migración
entera** —la recién aplicada— y solo se vio la otra porque **chocó con un procesador**. Sin
ese choque, ninguna de las dos se habría visto.

**Cerrado en código:** paso 10 de `restaurar-staging.yml` + `scripts/comparar_censos.py`.

### 6 · La comprobación cuyos dos lados son iguales por construcción

No que falte entrada: que los dos lados **no puedan diferir**.

| | la comprobación | por qué no podía fallar |
|---|---|---|
| 1 | el pin del `search_path`, con y sin pin en el mismo `UNION` | `set_config(…, true)` es de **transacción**: fijado en la primera rama, la segunda ya lo tiene. Salía 379 y 379 |
| 2 | testigo de entorno: `current_database()` y `count(*)` | staging es un **clon restaurado** de producción: coinciden **por construcción** |
| 3 | la huella `es_case` para saber si una vista estaba al día | ese texto está en la versión **vieja y en la nueva** |
| 4 | `bash -n` sobre un script extraído de un `.yml` | el extractor había petado y no escribió nada. **Validar la nada siempre sale bien** |

🔑 **La forma común:** la entrada no puede producir un resultado distinto — porque se comparan
dos cosas iguales por construcción (1, 2, 3) o porque **no hay entrada** (4).

⚠️ Corolario para toda huella o marcador de versión: **se elige contra la versión VIEJA, no
contra la nueva.** Que aparezca en la actual no prueba nada; hay que comprobar que **NO**
aparece en la anterior.

---

## Lo que ya está cerrado en código

Las reglas de esta casa no se quedan escritas: cuando se repiten, se convierten en
herramienta. Una regla escrita se olvida en veinte minutos; una regla convertida en función
se aplica sola.

| pieza | qué cierra |
|---|---|
| `scripts/anti_cero.py` · `exigir_poblacion()` | el resultado calculado sobre una población **vacía** (caso 6.4) |
| `scripts/anti_cero.py` · `exigir_discriminacion()` | comparar una cosa **consigo misma** (caso 6, subcaso mecánico) |
| `scripts/comparar_censos.py` | staging por detrás de producción (caso 5) |
| `sql/huella_tablas_foto.sql` | el cambio inerte que no se verifica por su resultado (caso 4) |
| `contrato-extracto.mjs` *(v2)* | el medidor sin la columna que la app usa (caso 2) |
| `sin_comentarios()` *(v2)* | lo que se lee como texto no distingue código de comentario |

---

## Lo que NO se puede automatizar, y por eso esto es un guion

`exigir_poblacion()` detecta que **no había entrada**. No detecta que la entrada que había
**no discrimina** — que es el caso 6 en general, y el que costó los cinco falsos verdes del
20-ago.

Para eso solo hay una cosa que funcione, y es de una línea:

> **Rómpelo a mano y míralo ponerse rojo.**

Un test que sólo se ha visto en verde no se ha probado: se ha ejecutado. Y si al romperlo no
pasa nada, no estaba puesto.

⚠️ Ojo al patrón que más se repite: **la comprobación que mira lo que NO cambia.** Un assert
que busca un texto presente en las **dos** versiones —el prefijo de una firma, el nombre de
una función, una columna del `SELECT`— sale verde hagas lo que hagas. Se ancla contra **lo que
no debe aparecer**, que es la única mitad que se mueve.
