# PARTE DE NOCHE — 10-ago-2026 (para leer el 11)

> ✅ **CERRADO el 11-ago-2026.** Los tres fallos que se cuentan aquí abajo están corregidos y medidos: los arregló el PR #135, con el criterio que fijó Fernando esa mañana (cuatro criterios de aborto + una zona gris que pide `forzar`). Esto queda como **parte de una noche concreta**, no como estado de hoy — el estado vive en el repo, no en las notas (§3 de `CLAUDE.md`).

*Escrito por la sesión que trabajó sola desde las ~18:00 UTC. Fernando se fue dejando el
portátil encendido y un encargo con límites. **Paré a mitad, a propósito**, y esto explica
por qué.*

---

## 🔴 LO PRIMERO: LA CARGA DE IT **NO** ENTRÓ

```
demanda_asin en PRODUCCIÓN, ahora mismo:
  ES · 30-jul 18:06   321 filas
  ES ·  7-ago 18:03   346 filas
  FR · 30-jul 18:06   196 filas
  IT · 30-jul 18:06   112 filas
                    ────────────
                      975 filas · 4 lecturas
```

**Exactamente como estaba.** `metric-data (1).xlsx` sigue en el buzón, sigue siendo bueno, y
sigue sin cargar. **No estrena resta contra el 30-jul.**

**Producción no se ha tocado en toda la noche.** Ningún `aplicar` contra producción.

---

## POR QUÉ PARÉ

El encargo decía: *"si algo no sale como esperas, PARA. No improvises un segundo arreglo
encima del primero a las once de la noche y sin nadie mirando."*

Pasé mi propio arreglo por una revisión adversarial (29 agentes, 4 ángulos, cada hallazgo
por un refutador). Sobrevivieron **tres, los tres críticos**. Están en un comentario del
[PR #135](https://github.com/Moloka-Store/moloka-app/pull/135), que he renombrado a
**"NO FUSIONAR"**.

### 1 · Mi arreglo abre un agujero que el código viejo no tenía

Si la última lectura de un país es **vieja** (p. ej. del 10-may) y alguien exporta un
*Custom date range* 10-may→10-ago, los totales sobre los ASIN comunes **suben** —tres meses
de verano venden más que enero-mayo—, así que se clasifica como PUNTUAL y **se carga**.

Es justo el fichero que la guarda existe para parar. **El código anterior lo abortaba.**

Y delata un supuesto mío **sin medir**, escrito en mi propio comentario: *"un export de otro
rango baja los totales sobre los ASIN comunes SIEMPRE"*. **Es falso.** Solo baja si la
lectura anterior acumula más que el rango exportado. El caso que medí (246 vs 321) baja
porque la lectura anterior era de días antes; con una anterior vieja, el signo se invierte.

### 2 · Con cero ASIN comunes, los totales valen `0 → 0` y se clasifica como PUNTUAL

`comunes = set(previo) & set(nuevo)`. Si queda vacío, las nueve sumas dan `0.0`,
`totales_abajo` sale vacío, y el log remata con *"Los totales acumulados SUBEN … SE CARGA"*.

**Ni suben ni bajan: no se ha medido nada**, y el mensaje afirma lo contrario. Es el defecto
exacto que el PR venía a quitar. La versión continua es peor porque no se ve: con 4 ASIN
comunes de 180, los totales se calculan sobre 4 filas y cualquier cosa pasa por "suben".

### 3 · Basta que baje UNA métrica medio céntimo — el bug original, un piso más arriba

`es_global = bool(totales_abajo)`, con holgura **absoluta** de 0,005 y criterio de
*"cualquiera"*.

FR, dos lecturas separadas por 2 días (el panel va 9 días por detrás, así que el incremento
real es pequeño). Se cancelan 3 unidades de 24,99 (−74,97) y las ventas nuevas del tramo
suman 62,47: `facturacion_pedida_eur` baja. **Las otras ocho suben.** Aborta con *"bajan los
totales de facturacion_pedida_eur"* — afirmación que **la tabla impresa dos líneas antes
desmiente** — y sigue culpando al rango del export.

Es la misma clase de falso rojo que rechazó la carga de IT.

---

## ⚠️ ESTO CHOCA CON EL CRITERIO QUE DIO FERNANDO — Y ES SU DECISIÓN

El encargo decía: *"Si algún TOTAL acumulado del fichero BAJA → ABORTAR"*. El fallo 3 dice
que **ese criterio, tal cual, produce falsos rojos en países pequeños**. No lo cambio de
madrugada.

Lo que la revisión propone —y que hay que **medir, no adoptar a ojo**— es un criterio de
**proporción de comparaciones que bajan**, que no depende del signo ni del tamaño del país:

| | |
|---|---|
| carga BUENA de IT | **2 / 1.008 = 0,2 %** |
| export de OTRO RANGO (`CA_ES_02ago`) | **1.583 / 2.214 = 71,5 %** |

Dos órdenes de magnitud de separación. **Pero son dos puntos de datos**, y §3 de `CLAUDE.md`
es explícito: las guardas se miden contra los ficheros reales, no se calibran a ojo.

**La decisión pendiente:** si se añade el criterio de proporción, con qué umbral, y de dónde
salen los datos para calibrarlo. Más el corte por `comunes` vacío (fallo 2), que ese sí es
un arreglo claro sin umbral que inventar.

---

## LO QUE SÍ QUEDÓ HECHO Y VERIFICADO

### Las dos ramas de la guarda, ejercitadas de verdad

Fernando puso la condición: *"lo que no vale es fusionar código que nunca ha corrido"*.

| Rama | Run | Resultado |
|---|---|---|
| **PUNTUAL** | [31417946639](https://github.com/Moloka-Store/moloka-app/actions/runs/31417946639) | `metric-data (1).xlsx` IT · los 9 totales suben · clasifica PUNTUAL · cargaría 128 filas |
| **GLOBAL** | [31419303833](https://github.com/Moloka-Store/moloka-app/actions/runs/31419303833) | `CA_ES_02ago_DISCONTINUO` · las 9 métricas `[BAJA]` · **ABORTA** por GLOBAL · lista completa de 1.583 bajadas |

Para la GLOBAL hizo falta montar el escenario: el fichero que la dispara es del 2-ago,
*anterior* a la lectura de ES del 7-ago, y la 6.14 solo compara hacia adelante. Se borró esa
lectura en staging con un fixture, se probó, y **se restauró staging** ([run
31419495538](https://github.com/Moloka-Store/moloka-app/actions/runs/31419495538), verde,
2m17s).

### Tres frases falsas corregidas en el workflow

Todas en el `.yml` que se lee **justo antes de lanzar**, que es donde más daño hacen:

1. *"la guarda 6.14 rechaza una vieja detrás de una nueva"* — **falso**.
2. *"si se mete primero la del 7 y luego la del 30 de julio, la vieja parece un retroceso y
   se rechaza"* — **falso**.
3. *"6.14 alguna métrica acumulada BAJA → ese export se generó con OTRO periodo"* — el
   diagnóstico que se afirmaba sin medir.

### El agujero «VIEJA DETRÁS DE NUEVA», anotado

La 6.14 **solo compara hacia adelante**. Una lectura anterior a la última la ve la 6.8, que
**grita y sigue**. Medido: `CA_ES_02ago_DISCONTINUO` pasó un ensayo entero sin que nada lo
parase ([run 31416925455](https://github.com/Moloka-Store/moloka-app/actions/runs/31416925455)).
Si entrara, quedaría intercalada y el `lag()` de `v_demanda_asin_ultima` calcularía **7-ago
menos 2-ago**. Está en §2 de `CLAUDE.md`. **Sigue abierto.**

---

## ESTADO DE LOS PR

| PR | Qué | Estado |
|---|---|---|
| [#135](https://github.com/Moloka-Store/moloka-app/pull/135) | Guarda 6.14: GLOBAL vs PUNTUAL | 🛑 **ABIERTO — "NO FUSIONAR"**, con los 3 fallos en un comentario |
| [#136](https://github.com/Moloka-Store/moloka-app/pull/136) | Fixture de staging | ✅ fusionado |

Antes de que Fernando se fuera, esta misma sesión dejó fusionados: #132 (buzón
`custom_analytics`, que desbloqueó la subida desde la app), #133 (regla de invariantes) y
#134 (aviso del reinicio del 1-ene-2027).

---

## DOS COSAS QUE NO ENCONTRÉ

El encargo final pedía empujar `PARTE_NOCHE_11ago.md` y `APLICAR_A_MANO_11ago.sql`.

- **`APLICAR_A_MANO_11ago.sql` no existe** en ninguna rama, ni local ni en origin, y **no lo
  he creado**: no hay nada pendiente de aplicar a mano. Lo que queda es una decisión de
  criterio, no un SQL. No lo invento.
- **`PARTE_NOCHE_11ago.md` tampoco existía.** Es este fichero, escrito ahora.

Si esos dos nombres vienen de otra sesión, su contenido **no está en este repo** y habrá que
buscarlo donde se escribiera.

---

## LO QUE NO SE TOCÓ, POR ORDEN EXPRESA

Ninguna migración, ni esquema, ni permisos, ni storage, ni la app v2. Ni el PR del modelo
(huella + `rn=1`), ni el `--no-privileges` del backup, ni el registro de migraciones, ni el
agujero del 1 de enero. No se subió ni se descargó ningún informe.
