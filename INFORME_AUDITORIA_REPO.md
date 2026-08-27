> **Lo lee Fernando, y cualquier chat que necesite saber qué hay construido de verdad. Escrito el 27-ago-2026, 17:10.** Todo lo de aquí está leído del código, no de las notas. Lo que no he podido comprobar lleva escrito «no verificado» y por qué.

# Auditoría del repo — qué está construido de verdad

## Contra qué se ha medido

| | Repo | Commit | Fecha |
|---|---|---|---|
| A | `Moloka-Store/moloka-app` (público) | **`a6b8d83`** | 26-ago-2026 16:27 |
| B | `Moloka-Store/moloka-app-v2` (privado) | **`ad57313`** | 27-ago-2026 11:45 |

Mi working tree coincide con `origin/main` de A al dígito (`git fetch` hecho al empezar, HEAD == origin/main, árbol limpio, 219 ficheros en git y 0 sin bajar). De B se hizo un clon limpio y verificado (541 ficheros en git, 0 sin bajar).

🔴 **El encargo hablaba de «el repo», en singular, pero pedía cosas de los DOS.** `salud-derivada.yml`, `supabase/migrations/`, `PAISES_INFORME` y el PR #320 viven en la v2; `procesador_internacional.py` y el PR #174 viven en moloka-app. Auditar solo uno habría dejado media pregunta sin contestar, así que están los dos. Detalle que conviene saber: **en moloka-app las migraciones NO están en `supabase/migrations/`, están en `migraciones/`** con otro formato de nombre (`2026-08-26_…` en vez de `20260826…`).

⚠️ **Dos trampas de medición que me pillaron a mí durante esta auditoría**, y que apunto porque le pasarán al siguiente:

1. **Conté 54 workflows a ojo y son 52.** Contar mirando es contar mal.
2. **El clon de la v2 en la carpeta temporal se dejó 18 migraciones sin leer, en silencio**, porque la ruta pasaba del límite de 260 caracteres de Windows. `git show` decía `Filename too long` y mi censo salía con menos objetos sin que nada fallara — *validar la nada siempre sale bien*. Se arregló clonando en una ruta corta y **comprobando que el número de ficheros en disco cuadra con el de git antes de contar nada**.

---

## Resumen: los nueve hallazgos que importan

| # | Qué | Dónde | Gravedad |
|---|---|---|---|
| 1 | **El PR #174 mata el escáner al arrancar.** Una variable que no existe. Probado ejecutándolo | moloka-app | 🔴 dinero + parada |
| 2 | **`procesador_internacional.py` SIGUE sin guarda anti-retroceso.** Son 5 los que la necesitan y solo 4 la tienen | moloka-app | 🔴 |
| 3 | **`salud-derivada.yml` lleva 18 verdes sin comprobar nada.** Medido en el log del 25-ago | v2 | 🔴 |
| 4 | **Un test obligatorio lleva 11 días sin ejecutarse** y el presupuesto del CI no puede cazarlo | v2 | 🔴 |
| 5 | **CLAUDE.md dice que un frente está bloqueado y ya no lo está** (la clave del trackeador) | moloka-app | 🔴 |
| 6 | **Tres tests de Python que ningún workflow lanza**, uno es el de la guarda del contador | moloka-app | 🟠 |
| 7 | **`vigilante-acantilado.yml` no existe** y el CI dice al usuario que existe | v2 | 🟠 |
| 8 | **El Trackeador vive fuera del repo**: 3 objetos que el código usa y ninguna migración crea | los dos | 🟠 |
| 9 | **El auditor de datos no se ha ejecutado NUNCA**, y le falta un secreto que ya existe al lado | v2 | 🟠 |

---

# 1 · WORKFLOWS

## 1.1 El censo

**52 workflows en moloka-app, 5 en moloka-app-v2.** Los 52 están en `origin/main` (ninguno suelto en disco).

**Relojes activos: solo cuatro en todo el proyecto.**

| Workflow | Repo | Cron | Qué hace |
|---|---|---|---|
| `backup-bd.yml` | app | `15 2 * * *` | Copia diaria a R2 (BD + ficheros) |
| `censo-migraciones.yml` | app | `13 5 * * 2` | Martes: qué migración fusionada no está aplicada |
| `salud-derivada.yml` | v2 | `15 7 * * 1-5` | ¿Sigue vivo el trigger de `stock_moloka`? |
| `warm-inventario.yml` | v2 | `15 5 * * 1-5` | ¿Carga /inventario antes de que entre Elena? |

**Relojes apagados a propósito (cron comentado):** `detector-bems.yml` (3 crons), `semanal-bems.yml` (1), `auditor-diario.yml` (1, v2). Todo lo demás es a mano.

## 1.2 Los secretos y las variables SÍ existen — salvo dos, y son las que importan

**moloka-app: cuadra exacto.** Los workflows referencian **28** secretos distintos y en el repo hay **28**, los mismos. Cero variables de repositorio usadas y cero definidas — coherente. Ningún secreto fantasma.

**moloka-app-v2: NO cuadra.**

| Lo que el repo TIENE | Lo que los workflows PIDEN y no está |
|---|---|
| vars: `WARM_APP_URL`, `WARM_SUPABASE_URL`, `WARM_SUPABASE_KEY` | 🔴 vars: **`SUPABASE_URL`**, **`SUPABASE_PUBLISHABLE_KEY`** |
| secrets: `WARMER_EMAIL`, `WARMER_PASSWORD` | 🔴 secret: **`SUPABASE_DB_URL`** |

Las dos primeras son las de `salud-derivada.yml` → hallazgo 3. La tercera es la de `auditor-diario.yml` → hallazgo 8.

## 1.3 🔴 HALLAZGO 3 — `salud-derivada.yml`: 18 verdes sin comprobar nada, y sigue así hoy

**El precedente no está cerrado: sigue abierto, y ya no son 16 sino 18.**

Historia completa del workflow: **19 ejecuciones, 18 en verde y 1 en rojo** (la del 26-ago, que no dejó ni log ni pasos — es un fallo de infraestructura del runner, no del código).

**La prueba, en el log del run del 25-ago-2026** (`32824200972`):

```
env:
  URL:
  KEY:
##[notice] Faltan las variables SUPABASE_URL y/o SUPABASE_PUBLISHABLE_KEY.
          Sin ellas no se puede preguntar a la base: no se comprueba nada.
```

Las dos variables **llegan vacías**, el workflow hace `exit 0`, y GitHub lo pinta **verde**. Es la firma exacta que describe el encargo. En cristiano: es un vigilante nocturno que ficha todos los días y nunca ha salido de la garita — el parte diario dice «sin novedad» porque no ha mirado.

**Lo que esto significa:** el trigger `trg_sync_stock_moloka` deriva `stock_moloka` de `ubicaciones_cant`. Si alguien lo tira, el inventario, las alertas y el envío FBA se ponen a leer un número muerto **y nada avisa**. Ese workflow existe precisamente para eso, y lleva desde el 31-jul-2026 sin hacerlo.

**El arreglo cuesta dos minutos** y no toca código: crear las dos variables en `moloka-app-v2 → Settings → Secrets and variables → Actions → Variables`. No son secretos (la clave publicable ya está en el `index.html` de un repo público, por diseño). ⚠️ Y una vez creadas hay que **mirar el primer run**: si la función `salud_stock_moloka()` no está aplicada en el proyecto al que apunte, dará 404 — que también es un rojo honesto, pero conviene no confundirlo.

🔑 **El fail-open aquí está escrito a propósito y razonado en la cabecera** («un rojo diario que nadie mira es ruido»). El argumento es bueno; lo que falla es que nadie completó el otro extremo. Un aviso que nadie ha ido a leer en 27 días es exactamente lo mismo que no tenerlo.

## 1.4 Otros fail-open encontrados (y los que NO lo son)

**`warm-inventario.yml` (v2) tiene el mismo patrón** — si falta configuración, `ok=false` y todos los pasos siguientes se saltan con `if:`, job verde. **Pero aquí las cinco piezas SÍ existen**, y las ejecuciones programadas del 25 y 26-ago salieron verdes de verdad. Está sano; queda anotado porque el día que alguien renombre una variable, se apagará en silencio igual que su hermano.

**`semanal-bems.yml` (app):** su guarda del «verde vacío» usa `::warning::` y nunca `exit 1`, así que un repaso que no lanza ni una marca sale verde. **Está decidido y escrito así a propósito** (que BEMS no tenga nada que repasar una semana es legítimo). Hoy no hay riesgo porque su cron está comentado. ⚠️ El día que se descomente, vuelve a ser el patrón de siempre.

**`backup-bd.yml` (app), paso 6:** lista cuántos objetos hay en R2 tras el `aws s3 sync` y **nunca compara ese número con nada**. El paso 5 sí tiene número de control externo (pregunta a Postgres cuántos ficheros hay y aborta si no cuadra), así que **la bajada a disco está verificada; la subida de disco a R2 no**. No es equiparable a los otros dos —`sync` fallaría con código distinto de cero si reventase—, pero es el único tramo de la copia sin veredicto propio. Se junta con el pendiente que ya está apuntado en CLAUDE.md: la copia de ficheros a R2 **no tiene simulacro de restauración**.

**`restaurar-staging.yml` (app):** **14 invocaciones reales de `psql` y solo 3 con `ON_ERROR_STOP`** (líneas 475, 1083 y 1084). Las 11 restantes son de solo lectura y **fallan cerrado por otra vía** —el propio script comprueba que el resultado no venga vacío y aborta (línea 799: `if [ -z "$HUELLA_ACL" ]` → `exit 1`)—. No lo cuento como agujero abierto, pero se aparta de la regla que la propia cabecera del fichero declara.

⚠️ *Aquí me equivoqué dos veces y lo dejo escrito porque las dos son la misma familia de error que este informe persigue.* La primera cifra que escribí fue «19 y 4»: salía de un `grep -c 'psql '` que **contaba también las 8 líneas donde la palabra aparece dentro de un comentario o de un `echo`**. Al rehacerlo por líneas de código me salió «14 y 2», porque **truncaba cada línea a 80 caracteres para imprimirla** y la de la 1083 lleva su `ON_ERROR_STOP` en el carácter 100. Lo cazó el auditor independiente. Las dos veces el número era plausible, ninguna dio error, y las dos son literalmente lo que avisa CLAUDE.md: **lo que se lee como texto no distingue código de comentario, y medir sobre una vista recortada es medir otra cosa.**

**Lo que NO está y conviene saber que se buscó:** cero `continue-on-error` en los 52 workflows de moloka-app y cero en los 5 de la v2. Cero `set +e` por descuido (el único caso, en `centinela-despliegue.yml`, está invertido a propósito y razonado). Y el mecanismo exacto que rompió `salud-derivada.yml` —`vars.` inexistentes— **no puede reproducirse en moloka-app: ese repo no usa `vars.` ni una vez.**

**Y un ejemplo de lo contrario, que merece constar:** el `ci.yml` de la v2, cuando `git diff` no devuelve ficheros, **corre el job de SQL igualmente**, con el comentario «se falla del lado caro, que es el único que no miente». Eso es lo que hay que copiar.

## 1.5 🟠 HALLAZGO 6 — el CI de la v2 apunta a un vigilante que no existe

`ci.yml` avisa cuando `lint-test` roza los 60 segundos (cruzarlos **duplica** lo que cuesta cada push, ~765 min/mes) y dice **dos veces** que quien de verdad decide es otro workflow:

> `ci.yml:190` — «Lo que SÍ falla por la razón buena es `vigilante-acantilado.yml`, que mira la MEDIANA»
> `ci.yml:232` — dentro del aviso que lee la persona: «Quien decide es la MEDIANA, y la vigila vigilante-acantilado.yml»

**`vigilante-acantilado.yml` no existe.** No está en el árbol, GitHub devuelve 404, y la lista de workflows de la v2 son cinco y ninguno es ése. O sea: el aviso del acantilado **solo avisa**, y la mitad que tenía que ponerse roja está delegada en un fichero fantasma. Con la particularidad de que el texto falso **se le enseña a quien lee el log**, no es un comentario interno.

---

# 2 · MIGRACIONES

## 2.1 El censo

| | moloka-app (`migraciones/`) | moloka-app-v2 (`supabase/migrations/`) |
|---|---|---|
| Ficheros `.sql` | **68** (2 son `_PRUEBA_…`, no se aplican) | **61** |
| La última | `2026-08-26_keepa_imagen_principal.sql` | `20260817030000_repo_alcanza_a_produccion_buzones.sql` |
| Objetos que crean | 36 | 52 |

📌 **Dato en bruto: la v2 lleva diez días sin una migración nueva** (17-ago) mientras moloka-app llega al 26-ago. No es un defecto por sí solo —el trabajo de la v2 de estas semanas ha sido de pantalla—, pero es la clase de cosa que conviene saber antes de dar por hecho que la capa de datos de la v2 sigue el ritmo de la pantalla.

## 2.2 🟠 HALLAZGO 7 — el Trackeador vive fuera del repo

Crucé **todo lo que el código de la v2 invoca** (35 tablas/vistas por `.from(...)` y 16 funciones por `.rpc(...)`) contra **todo lo que crean las 129 migraciones de los dos repos**, más el DDL que los procesadores llevan escrito dentro. Resultado limpio:

**Tres objetos que el código usa a diario y que NINGUNA migración de NINGÚN repo crea:**

| Objeto | Tipo | Quién lo usa |
|---|---|---|
| `mv_trackeador_pantalla` | materializada | `Cockpit.tsx`, `Table.tsx`, `model.ts`, `lib/trackeador/*` — 13 ficheros de la v2 |
| `v_trackeador_frescura` | vista | `lib/trackeador/query.ts`, `tipos.ts` |
| `fn_trackeador_refrescar` | función | **`foto_comun.py`, en CADA carga de CADA informe** |

Se mencionan en 18 sitios y no se crean en ninguno. Existen solo en la base viva, puestas a mano. **Consecuencia práctica:** si mañana hay que restaurar de una copia, o levantar staging para ensayar algo que toque el Trackeador, esos tres objetos **no vuelven**, y no hay dónde ir a buscarlos salvo la propia base. Es el caso general de la nota que ya existe («el repo no es la verdad»), aquí con nombre y apellidos.

🟢 **Lo que sí está bien hecho:** `foto_comun.py` no da nada por supuesto. Antes de refrescar una materializada pregunta `to_regclass` y, si no existe, lo escribe con todas las letras en vez de seguir como si nada. Y con `fn_trackeador_refrescar` va más lejos: la función devuelve **texto** aunque falle, así que el código comprueba explícitamente si ese texto empieza por `ERROR:` — con el comentario «que devuelva texto no significa que haya ido bien». Eso es exactamente lo que evita un verde prestado.

**Y lo que NO es un hallazgo, aunque lo parezca:** hay 8 tablas del núcleo de la v1 (`productos`, `movimientos`, `facturas`, `compras`, `app_datos`, `canales_producto`, `codigos_proveedor`, `envios_fba`) que tampoco las crea ninguna migración. Son anteriores al versionado y nadie ha prometido nunca lo contrario. Lo apunto para que quede dicho, no como defecto.

**`salud_fba_historico` merece una línea aparte.** Su creador era `procesador_salud_fba.py`, que se borró el 23-ago al jubilar el informe; con el fichero se fue el DDL. **Pero está decidido y escrito**: la migración de jubilación dice «`salud_fba_historico` NO SE BORRA», lo lee `v_nunca_enviado_fba`, y guarda 1.984 filas de 9 fechas que sirvieron para datar una avería al día exacto. Es un archivo **congelado a propósito**. ⚠️ El único cuidado: nadie lo escribe ya, así que cualquier cifra que salga de ahí es del 16-ago y **necesita llevar su fecha pegada** para no mentir.

## 2.3 `v_reglas_arranque` — no existe, y la skill tampoco

`v_reglas_arranque` **no aparece ni una vez en ninguno de los dos repos**. Ni creada, ni consultada, ni mencionada en un comentario.

**La otra mitad no la he podido verificar: la skill `moloka-aprender` no está en esta máquina.** No está en `~/.claude` (que no tiene carpeta de skills), no está en ningún plugin instalado y no está en los repos. El único sitio donde aparece ese nombre es la transcripción de esta propia sesión, o sea el texto del encargo. **No verificado, y por eso: no puedo confirmar ni desmentir que la skill dé por existente esa vista.** Lo que sí queda medido y es la mitad útil: **si alguien la da por existente, se equivoca en los dos repos.** Quien tenga la skill delante puede cerrarlo en diez segundos.

---

# 3 · SCRIPTS Y PROCESADORES — la guarda anti-retroceso

## 3.1 🔴 HALLAZGO 2 — el censo, y el que falta

`guarda_no_retroceder()` está definida **una sola vez** en `foto_comun.py` y se llama desde **cuatro** procesadores. El quinto que la necesita no la tiene.

| Procesador | Cajón | ¿Guarda de fecha? | Dónde |
|---|---|---|---|
| `procesador_all_listings.py` | FOTO | ✅ | `:243` |
| `procesador_paneu_aptos.py` | FOTO | ✅ | `:567` |
| `procesador_inventario_fba.py` | FOTO | ✅ | `:638` |
| `procesador_keepa_escaparate.py` | FOTO | ✅ | `:946` (Guarda 11) |
| **`procesador_internacional.py`** | **FOTO** | 🔴 **NO** | — |
| `procesador_ledger.py` | PELÍCULA | no aplica | carga por rango |
| `procesador_transacciones.py` | PELÍCULA | no aplica | carga por rango |
| `procesador_custom_analytics.py` | contador | ✅ propia | guardas 6.8 / 6.14 / 6.15 |
| `procesador_canal_amazon_es.py` | derivado | no aplica | no lee fichero |

**Comprobado por mí, no heredado:** busqué `guarda_no_retroceder(` sobre el código con los comentarios y los docstrings quitados (para que una guarda comentada no cuente como puesta). Salen 4 llamadas y 1 definición. En `procesador_internacional.py` **la palabra no aparece ni una vez**, ni en código ni en comentario.

**Y sí la necesita, porque es Foto:** importa `guarda_anti_encogimiento` y `barrer_sobrantes`, y en la línea 356 **borra de la base todo lo que no venga en el fichero**. Sin guarda de fecha, cargar un informe viejo tira la foto buena. En términos contables: es un asiento de regularización que sustituye el saldo entero, sin comprobar antes que la hoja que traes es más reciente que la que hay.

⚠️ **Y ahora la parte honesta, que cambia el tamaño del arreglo pero no la conclusión.** En este procesador la fecha del dato **no viene dentro del fichero**: se toma de cuándo se subió al buzón (`fecha_del_dato_por_subida`, línea 276). Así que la guarda **no** protegería del caso «subo hoy un informe de la semana pasada» —ése entraría con fecha de hoy—. Protege del otro: que la carga de hoy sea más vieja que la última registrada, que es lo que pasa si el buzón se queda con un fichero anterior o se relanza sobre un estado ya avanzado. **La guarda hay que ponerla igual** (es la red que tienen sus cuatro hermanos y cuesta una línea), pero conviene ponerla sabiendo qué caza y qué no, que es justo lo que manda la regla de la casa: *las guardas no se copian, se miden contra el informe de cada uno*.

## 3.2 🟠 HALLAZGO 5 — tres tests sanos que nadie ejecuta

En moloka-app **no hay CI**: no existe un `ci.yml`, y los tests se lanzan nombrándolos a mano dentro de los workflows de cada procesador. No hay `pytest` ni comodín en ningún sitio — lo comprobé buscando las cuatro formas posibles de invocarlos. **Consecuencia: un test que nadie nombra, no corre. Y hay tres.**

| Test | Qué prueba | Quién lo lanza |
|---|---|---|
| **`test_guarda_614.py`** | Las 10 ramas de la guarda 6.14 (el contador de Custom Analytics no retrocede) | 🔴 **nadie** |
| `test_reintento_conexion.py` | El reintento de conexión a Postgres | 🔴 **nadie** |
| `test_reintento_storage.py` | El reintento de lecturas de Storage | 🔴 **nadie** |

**Los ejecuté los tres: los tres pasan y salen con código 0.** No están rotos ni obsoletos — simplemente no se lanzan. El más caro de perder es el primero: la guarda 6.14 es la que impide que un export de otro rango destroce la serie del contador, y `procesar-custom-analytics.yml` **solo ejecuta el procesador**, ningún test.

El arreglo son tres líneas: añadir `run: python -u test_guarda_614.py` a `procesar-custom-analytics.yml` y los otros dos donde corresponda, con el mismo formato que ya usan los otros nueve tests.

*(Nota de método: al ejecutarlos en Windows los tres «fallan» por la consola, que no sabe escribir el carácter `→`. No es el test: es `cp1252`. Con `PYTHONIOENCODING=utf-8` pasan limpios, y en los runners de Ubuntu no se daría.)*

## 3.3 🔴 HALLAZGO 4 — en la v2, un test obligatorio lleva 11 días sin ejecutarse

La v2 sí tiene CI y registra sus suites a mano en un array. Hice el censo completo: **165 suites importados, 165 registrados, cero descolgados.** Esa parte está limpia.

**Pero hay un fichero de test que no lo importa nadie:**

`tests/envios-modo-caja-igual-que-antes.test.mjs` — 176 líneas, exporta su `run`, y empieza diciendo de sí mismo:

> «LA VERIFICACIÓN OBLIGATORIA DEL §8: demostrar que un envío en MODO CAJA se monta y se confirma IGUAL QUE ANTES del cambio. No vale "no debería haber cambiado"».

Se añadió el **16-ago-2026** y **nada lo importa ni lo ejecuta** — ni `run.mjs`, ni `package.json`, ni ningún workflow. Once días. Es el mismo caso de §3 de CLAUDE.md, repetido: no es un test que falla, es un test que no existe, y encima da la sensación contraria.

🔑 **Y aquí está la parte que ata los dos hallazgos, que es lo que hace esto útil:** la v2 tiene un guardián que vigila que el CI no engorde, y una de las cuatro cifras que mide son **los asserts de la suite**. Parecería que eso caza un suite perdido. **No puede**, por dos razones que hay que ver juntas:

1. El número sale de `grep -c '^OK'` sobre la salida de la ejecución, o sea que **cuenta los asserts que se ejecutaron**, no los que están escritos.
2. La comparación es `if [ "$hoy" -gt "$presupuesto" ]` → **solo se pone roja cuando el número SUBE.**

O sea: es un techo sin suelo. Un suite que deja de ejecutarse **baja** el recuento, y el guardián lo da por bueno. Es la cara B de «las dos direcciones»: sabe decir «has crecido sin decidirlo» y no sabe decir «has dejado de probar algo». En este caso ni siquiera llegó a bajar —el suite nunca se registró, así que sus asserts nunca se contaron— y por eso no había nada que se moviera.

Cerrar el agujero es barato: que el CI compare **los ficheros `tests/*.test.mjs` que existen** contra los que `run.mjs` importa, y se ponga rojo si sobra alguno. Es una comprobación que sí puede fallar, que es el único tipo que sirve.

---

# 4 · AVISOS CADUCADOS

Un aviso caducado empuja a «arreglar» código sano, o a no arreglar el roto. Estos son los que he verificado uno a uno contra el código de hoy.

## 4.1 Caducados — el texto ya no es cierto

Los he ordenado por lo que cuesta creérselos. Los tres primeros pueden hacer que alguien tome una decisión equivocada; los últimos son referencias colgantes.

### 🔴 El más caro: CLAUDE.md dice que el trackeador NO tiene la clave de servicio, y sí la tiene

`CLAUDE.md` §4 (líneas 665-668), moloka-app:

> «sus dos workflows —`tracker-app.yml` y `tracker-cerebro.yml`— inyectan **ÚNICAMENTE** `secrets.SUPABASE_KEY`, no la de servicio»
> …y por eso: «**no se toca la BD hasta tenerlo**».

**Es falso hoy.** Los dos inyectan también la de servicio: `tracker-app.yml:45` y `tracker-cerebro.yml:53`, las dos líneas `SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}`, y el secreto existe en el repo.

**Por qué importa más que los otros:** ese párrafo describe un **bloqueo**, y el bloqueo ya no está. CLAUDE.md dice que las tablas `monitor_*` no se pueden cerrar frente a `anon` hasta saber con qué clave escribe el trackeador — y el paso previo que exigía ya está dado. Quien lea eso hoy concluye que sigue bloqueado y no lo está.

⚠️ **Ojo, la mitad de fondo SIGUE VIGENTE:** no hay ninguna migración posterior que cierre las `monitor_*`, así que **siguen abiertas a `anon` para borrar**. Lo que caduca es el motivo por el que estaba parado, no el problema. *(Y esto no toca la decisión cerrada de Fernando sobre `productos`/`escaner_memoria`: aquello está aparcado hasta jubilar la v1 y aquí no se reabre.)*

### 🔴 El CI de la v2 apunta a un workflow que no existe

Ya está contado en el hallazgo 6: `ci.yml:190` y `ci.yml:232` citan `vigilante-acantilado.yml`, que no existe. El de la línea 232 **se le enseña a quien lee el log**.

### 🟠 CLAUDE.md dice que de la app v2 «no hay nada todavía»

`CLAUDE.md:786`, moloka-app, §6:

> «De la app v2 en sí (repo, pantallas, Auth) **no hay nada todavía**, y está bien.»

La v2 tiene **541 ficheros versionados**, App Router completo (Inventario, Buzones, Entrada de facturas, Envíos FBA, Informe de rentabilidad), Auth por `@supabase/ssr`, 166 ficheros de test y 61 migraciones. Es la frase del arranque del proyecto y nadie la retiró.

⚠️ **Pero es menos grave de lo que parece, y hay que decirlo:** cinco líneas más abajo, en la 791, la propia sección se pone el descargo — *«Para el estado exacto de cada pieza: míralo en el repo y en la BD. No lo pongas aquí — caduca en horas.»* O sea que el fichero **avisa de que ese apartado caduca**. Lo bajo de 🔴 a 🟠 por eso: la frase es vieja, pero quien la lea tiene la instrucción de no fiarse justo al lado. *(Me lo corrigió el auditor independiente, que fue a leer el párrafo entero en vez de la línea.)*

### 🟠 La tabla de informes de CLAUDE.md §1.3 se quedó en seis

La tabla que dice cuáles son los informes de Amazon lista **seis**, y hoy no cuadra por los dos lados:

| Sobra | Faltan |
|---|---|
| **SALUD_FBA** — jubilado el 23-ago; su procesador ya no existe | **INVENTARIO_FBA** (lo sustituyó), **TRANSACCIONES**, **CUSTOM_ANALYTICS** |

Hoy hay **nueve** procesadores en el repo. La tabla es de las piezas más citadas del fichero —es la que impide sumar dos informes que no se suman— así que conviene que esté al día.

### 🟠 Los avisos que arrastró la jubilación de `salud_fba`

El 23-ago se jubiló el informe y se borró `procesador_salud_fba.py` (commit `b92cb36`), pero el cambio no se propagó a los sitios que lo nombran. Son cuatro, y todos apuntan a un fichero que ya no está:

| Repo | Dónde | Lo que dice |
|---|---|---|
| app | `procesador_inventario_fba.py:25-27` | «`procesador_salud_fba.py` **no se toca**… **Nadie lee `inventario_fba` todavía**» — hoy `salud_fba` es una **vista sobre `inventario_fba`**, y la v2 lo lee directamente |
| app | `procesador_keepa_escaparate.py:36` | «Precedente a imitar: `procesador_salud_fba.py`» — quien lo busque no lo encuentra |
| app | `CLAUDE.md` §2, encodings medidos | «PANEU_APTOS, **SALUD_FBA** y KEEPA → traen BOM» |
| app | `CLAUDE.md` §2, lista de por lotes | «los cinco que iban fila a fila (paneu, internacional, **salud_fba**, all_listings, keepa)» — el hecho sigue siendo cierto, el nombre no existe |

🔑 Es un caso de manual de la propia regla de la casa: **un mismo cambio de estado propagado a mano a varios sitios se queda a medias en algunos**. Aquí se documentó bien en la migración y se olvidó en cuatro cabeceras.

### 🟠 Cabeceras que hablan de antes de fusionarse

| Repo | Dónde | Lo que dice | Prueba |
|---|---|---|---|
| v2 | `salud-derivada.yml:24-25` | «Hasta que esto se fusione a `main`, no se dispara solo» | Está en `main` y lleva **19 ejecuciones, todas `event=schedule`**, desde el 31-jul |
| v2 | `warm-inventario.yml:38-40` | Idéntica frase | Igual: sus ejecuciones del 25 y 26-ago son `event=schedule` |
| v2 | `salud-derivada.yml:22-23` | «La función está aplicada **SOLO EN STAGING**» | Es el aviso del precedente. **No verificable desde el repo** dónde está aplicada hoy. Lo que sí consta: el fichero **tiene un solo commit en toda su historia** (30-jul, `38c391a`), así que ese texto es el del primer día y nadie lo ha revisado en 28 días |

### 🟠 Dos avisos de la v2 que describen bugs ya arreglados

| Dónde | Lo que dice | Prueba |
|---|---|---|
| `docs/pendiente-bb-envio-duplicado.md:1` | «🔴 PENDIENTE · `build.ts:1632` — el envío se suma dos veces» | Hoy `build.ts:1834` es `const bbEfectiva = k.bb_precio ?? null`: **no suma**. Se arregló el 20-ago y el fichero-aviso se quedó |
| `CLAUDE.md:29` (v2) | «un cron usa para calentar `/inventario` **75 veces/día**» y le llama «`warmer@…`» | El cron es `'15 5 * * 1-5'`: **una vez al día** desde el 7-ago. Y el usuario real no es `warmer@…` sino otro, el que nombra `docs/usuario-warmer.md:1` *(no lo copio aquí: `moloka-app` es un repo público y ese correo es la mitad no secreta de unas credenciales de servicio)* |

⚠️ En el segundo, **lo que caduca es la cifra y el nombre, no la regla**: «el warmer NO ESCRIBE, NUNCA» sigue siendo una condición de diseño viva para las futuras RPC de escritura. Corregir el número sin borrar la regla.

## 4.2 Vigentes — lo comprobé y siguen siendo verdad

Los pongo porque un aviso que se retira por error es tan caro como uno que se queda de más.

- **`auditor-diario.yml`** dice que le falta el secreto `SUPABASE_DB_URL` y que en la v2 solo hay `WARMER_EMAIL`/`WARMER_PASSWORD`. **Exacto, hoy sigue siendo así** (comprobado con `gh secret list`). Vigente.
- **`CLAUDE.md` §1.1**: «hoy solo hay UN cruce que usa `moloka_ean_norm` (la vista de `procesador_keepa_escaparate.py`)». **Vigente**, y por poco: la función aparece en cuatro migraciones distintas, pero las cuatro redefinen **la misma vista**, `v_keepa_cruce`. ⚠️ Este casi me hace escribir un hallazgo falso. **Contar ficheros no es contar objetos**, y aquí la diferencia era todo.
- **`CLAUDE.md` §2, el mapa de dominios de Keepa** («3=DE · 4=FR · 8=IT · 9=ES»): **vigente y correcto**. `procesador_keepa_escaparate.py:94` tiene exactamente ese mapa. Este es el aviso que en su día estuvo caducado diez días; hoy el aviso y el código dicen lo mismo.
- **`CLAUDE.md` §4**, el pendiente del backup de ficheros sin simulacro de restauración: **vigente**. No existe ningún `restaurar-ficheros.yml` y `backup-bd.yml:76` sigue volcando con `--no-privileges`.
- **`sql/canario_rls.sql`**, «SON 21 tablas tapadas»: **vigente**, el censo tiene 21 filas y cuadra con el texto.
- **`lib/fecha.ts:68-78` (v2)**, «5 sitios cortan el día en UTC»: **vigente**, los cinco siguen exactamente donde dice.
- **`CLAUDE.md` §5**, la excepción de un día para no restaurar staging (23-ago): venía **con fecha de caducidad escrita dentro** («la ventana es de UN día; a partir del 24-ago la regla se aplica entera»). Hoy es 27. Se ha caducado sola, como estaba previsto. Eso es exactamente cómo hay que escribir una excepción.

🔑 **Y lo que enseña el contraste entre las dos listas:** los avisos que caducan mal son los que **afirman un estado del mundo** («no hay nada todavía», «solo inyectan esta clave», «hasta que se fusione»). Los que aguantan son los que **afirman una regla** («los informes no se suman», «el warmer no escribe») o los que **traen su propia fecha de caducidad dentro**. Es un criterio útil a la hora de escribir el siguiente: si la frase se puede volver falsa sin que nadie la toque, necesita o una fecha o una comprobación que la vigile.

## 4.3 Una trampa de nombre, que no es un aviso pero muerde igual

En `moloka_escaner_nube.py:1164` hay una función llamada **`iva_es_de`**. Se lee «IVA ES/DE» y **no lo es**: es «el IVA **es de**…» — devuelve el tipo de IVA español. Buscar Alemania en el escáner con un grep por `de` la encuentra y hace pensar que ya hay algo hecho. **No hay nada**: ver el punto 6.

---

# 5 · PRs ABIERTOS

## 5.1 El cuadro

**moloka-app: 3 abiertos.**

| PR | Estado | Tamaño | Qué hace |
|---|---|---|---|
| [#174](https://github.com/Moloka-Store/moloka-app/pull/174) | MERGEABLE / CLEAN | +83/-6, 1 fichero | 🔴 Recargo digital francés en el escáner — **NO fusionar, ver 5.2** |
| [#173](https://github.com/Moloka-Store/moloka-app/pull/173) | **CONFLICTING / DIRTY** | +174/-0, 2 ficheros | `entorno()`: que cada base diga su nombre. Conflicta porque `restaurar-staging.yml` ha cambiado 3 veces en `main` desde el 20-ago |
| [#166](https://github.com/Moloka-Store/moloka-app/pull/166) | MERGEABLE / CLEAN | +80/-1, 1 fichero | El sondeo trae PRECIO además de identidad. Su propio título dice «🔴 SIN FUSIONAR» |

**moloka-app-v2: 6 abiertos.**

| PR | Estado | Qué hace |
|---|---|---|
| [#320](https://github.com/Moloka-Store/moloka-app-v2/pull/320) | **MERGEABLE / CLEAN, CI verde** | 🟢 Recargo digital francés en el informe — **listo, ver 5.2** |
| [#291](https://github.com/Moloka-Store/moloka-app-v2/pull/291) | aparcado a propósito | «⛔ NO FUSIONAR NI APLICAR» — el histórico del escáner rompe el escáner de la v1 |
| [#283](https://github.com/Moloka-Store/moloka-app-v2/pull/283) | aparcado a propósito | «🔴 NO FUSIONAR» — Fase 4, migración escrita y sin aplicar |
| [#238](https://github.com/Moloka-Store/moloka-app-v2/pull/238) | aparcado a propósito | «APARCADO (no fusionar)» — retirar tres pestañas del Cockpit |
| [#148](https://github.com/Moloka-Store/moloka-app-v2/pull/148) | informe | Mapa de la Parte D — es solo lectura, no cambia nada |
| [#12](https://github.com/Moloka-Store/moloka-app-v2/pull/12) | aparcado a propósito | «APARCADO (no mergear)» — cierre del bucket `informes` a `anon` |

**Los cinco aparcados lo dicen en su propio título.** No hay ninguno olvidado por descuido salvo los del recargo francés.

## 5.2 🔴 HALLAZGO 1 — el #174 y el #320 NO están en el mismo sitio, y uno de los dos mata el escáner

El encargo daba los dos por «listos y sin fusionar». **Solo uno lo está.**

### #320 (v2) — sí está listo

`MERGEABLE / CLEAN`, CI en verde (`lint-test` ✅, `trigger-postgres` ✅), 7 ficheros, +342/-20. Trae un suite nuevo de 161 líneas **y —esto es lo que lo separa de un PR de mentira— toca también `tests/run.mjs` para registrarlo**, que es justo el paso que se olvida y deja el test muerto. Verificado: el `import` y la entrada en el array van los dos.

**Y no es redundante, que era lo primero que había que descartar.** En `main` de la v2, `ISD_PAIS` ya está corregido **para el Inventario** (`lib/inventory/build.ts`, con Francia en `incluyeFba: true` y su test). Lo que sigue con el 1,03 plano es **la pantalla del informe de rentabilidad**: `lib/informe/rentabilidad.ts:59` en `main` calcula `precioVenta * (refPct/100) * comDigitales` y no sabe nada del país. Eso es lo que arregla el #320.

### #174 (moloka-app) — 🔴 **NO se puede fusionar: revienta el escáner al arrancar**

El PR añade la tabla `ISD_PAIS` y sus comprobaciones de arranque al escáner. La aritmética **está bien** y cuadra contra la factura real. **Pero la última línea del bloque es esta:**

```python
print(f">>> FORMULA OK <<<  (ISD FR cuadrado con la factura: {_isd_con_fba:.4f} = {_ISD_REAL})")
```

**`_isd_con_fba` no existe.** La variable que el propio PR define se llama `_isd_fr`. Busqué el nombre en el fichero entero de la rama, no en el diff: **aparece exactamente una vez, en ese `print`, y no se le asigna valor en ningún sitio.**

**No lo deduje, lo ejecuté** — porque compilar no es ejecutar, y una `f-string` con un nombre que no existe compila perfectamente:

```
python -m py_compile   → compila: OK
python <el bloque>     → NameError: name '_isd_con_fba' is not defined
```

Los tres `assert` anteriores **pasan** (la tabla ISD es correcta). Lo que revienta es la línea de después.

🔴 **Qué pasaría si se fusiona:** eso está en el cuerpo del módulo, así que salta **al importar**, antes de hacer nada. Se caerían de golpe `escaner-app.yml` y los cuatro `director-*.yml` (dbline, heo, ociostock, tcg). El escáner de Elena deja de funcionar, y el mensaje de error no menciona ni Francia ni el ISD: dice que falta una variable.

**El arreglo es una palabra**: cambiar `_isd_con_fba` por `_isd_fr` en esa línea. Pero *no lo he hecho* — el encargo prohíbe tocar el escáner, y con razón: eso va en su propio PR, con alguien mirando.

🔑 **Y la lección, que vale más que el arreglo:** el #320 tenía CI y salió verde de verdad; el #174 **no tiene CI que lo ejecute** —moloka-app no tiene ninguno— así que un fallo que muere en la primera línea pudo quedarse siete días pareciendo «listo para fusionar». No es que nadie lo revisara: es que **leer no es ejecutar**, y en ese repo no hay nada que ejecute.

### Lo que falta, en orden

1. **#320**: se puede fusionar hoy. Está verde y completo.
2. **#174**: arreglar el nombre de la variable, **ejecutar el fichero** (no compilarlo) y solo entonces fusionar.
3. Los dos llevan la misma tabla con **Alemania al 3 % sobre la comisión, marcada como supuesto** («no hay ni una venta alemana contra la que contrastar»). Eso enlaza directo con el punto 6, y es el número que habrá que confirmar contra una factura real en cuanto Alemania venda.

---

# 6 · EL ESCÁNER Y ALEMANIA

## 6.1 `PAISES_INFORME` sigue en `['ES','IT','FR']` — y además no lo usa nadie

**Confirmado**, `lib/informe/types.ts:8` de la v2:

```ts
export const PAISES_INFORME = ['ES', 'IT', 'FR'] as const
```

🔴 **Pero el dato importante es otro: está exportado y NO lo importa nadie.** Busqué su nombre en todo el repo de la v2 y aparece una sola vez — su propia declaración. **Es código muerto.** Cambiarlo a cuatro países no metería Alemania en ningún sitio: no habría cambiado nada.

## 6.2 Dónde está Alemania de verdad, hoy

Alemania **ya está dentro** de media v2 y **fuera** de la otra media. Este es el reparto real:

| Ya incluye DE ✅ | Sigue en ES/IT/FR |
|---|---|
| `lib/inventory/build.ts:52` (`PAISES`) | 🟢 `lib/inventory/build.ts:2069` (`PAISES_RENTAB`) — **decidido, ver abajo** |
| `lib/inventory/build.ts:516` (`ORDEN_PAIS`) | 🔴 `lib/rentabilidad/build.ts:57` (`LOS_PAISES`) |
| `lib/inventory/build.ts:2063` (`PAISES_PANEU`) | 🔴 `lib/rentabilidad/types.ts:10` (`PAISES`) |
| `inventario/model.ts:2080` (`PAISES_ESTRENO`) | ⚪ `lib/informe/types.ts:8` (`PAISES_INFORME`) — muerto, da igual |
| `inventario/reponer/reglas.ts:137` (`PAISES_REPONER`) | 🔴 `scripts/verificacion/cifras-rentabilidad.mjs:48` |
| `procesar-transacciones.yml:30` (buzón, moloka-app) | |

En cristiano: **Alemania ya cuenta para saber qué tienes y qué reponer; no cuenta para saber cuánto ganas.**

🟢 **Y uno de esos «pendientes» NO lo es — casi lo cuento mal.** `PAISES_RENTAB` excluye a Alemania **a propósito, medido y escrito** el 16-ago-2026, en el comentario que tiene justo encima:

> «Alemania no aparece porque todavía no vende allí. Alemania **NO se añade «por simetría»**: un país en esta lista que la fuente no trae sería un `false` que se lee como *«ahí no pierde»*, y eso no se ha medido.»

O sea que esa lista **no se toca** hasta que el extracto traiga euros alemanes. Meterla «para que cuadren las cuatro» produciría exactamente el falso tranquilizador contra el que avisa. *(Lo pilló el auditor independiente: yo lo había puesto en la misma columna que la deuda de verdad, que es justo el error que este informe persigue — un aviso mal encuadrado empuja a «arreglar» código sano.)*

## 6.3 Qué haría falta para meter DE en el escáner

El escáner es `moloka_escaner_nube.py`, en **moloka-app**, y **no tiene Alemania por ningún lado** — ni una mención (la única aparición de `DE` es la trampa de `iva_es_de` del punto 4.3, y una palabra en una lista de artículos). Leído el fichero, esto es lo que hay que tocar:

| # | Qué | Dónde | Coste |
|---|---|---|---|
| 1 | Añadir el IVA alemán (**19 %**) junto a `IVA_IT`/`IVA_FR` | `:421` | 1 línea |
| 2 | Meterlo en el diccionario de IVA por dominio | `:1641` | 1 línea |
| 3 | `DOM_AMZ['DE'] = 'amazon.de'` | `:1684` | 1 línea |
| 4 | Abrir los bucles `for dom in ('ES','IT','FR')` a `'DE'` | `:1568`, `:1617`, `:1651`, `:1694`, `:1816` | **5 sitios** |
| 5 | El dominio de Keepa para DE es el **3** | donde se consulta Keepa | comprobar |
| 6 | El recargo digital alemán | lo trae el PR #174/#320 (3 % sobre comisión, **supuesto**) | ya escrito |

🔴 **Lo que de verdad decide si esto vale la pena no es ninguna de las seis: es el punto 4.** Cinco listas literales repetidas es exactamente «una regla escrita en vez de convertida en función»: quien meta Alemania tiene que acordarse de los cinco sitios, y **si se deja uno, no falla nada** — el escáner sigue funcionando y simplemente no mira Alemania en ese paso. **Antes de añadir el cuarto país conviene sacar la lista a UNA constante**, para que el siguiente país sea una línea y no una búsqueda.

⚠️ **Y un aviso sobre el dinero, que es de lo que va esto:** el escáner calcularía márgenes alemanes con un IVA correcto (19 % es un hecho) pero con un **recargo digital supuesto**, porque no hay ninguna venta alemana contra la que cuadrarlo. El resultado sirve para **ordenar** (qué referencia es mejor que cuál) y **todavía no para firmar un margen al céntimo**. La primera factura alemana con recargo es la que cierra ese número — y merece la pena buscarla a propósito el día que llegue, no esperar a tropezarse con ella.

📌 **Lo que NO he verificado y hay que decir:** el «58 de 199 referencias rentables» del encargo es una cifra de la **base**, no del repo. No la mido yo. Lo que sí queda medido es que **el escáner no puede haberla producido**, porque Alemania no entra en su cálculo por ningún sitio.

---

# 7 · Lo que NO he podido verificar

| Qué | Por qué |
|---|---|
| Si `salud_stock_moloka()` está aplicada en producción o solo en staging | Es la base. Lo mide el otro chat. Desde el repo solo consta que su migración existe (`20260730170000_salud_stock_moloka.sql`) |
| Si los tres objetos del Trackeador existen realmente en la base viva | Igual: solo puedo decir que **el repo no los crea** |
| Si la skill `moloka-aprender` da por existente `v_reglas_arranque` | La skill no está en esta máquina (ni en `~/.claude`, ni en plugins, ni en los repos) |
| El «58 de 199» de Alemania | Cifra de base de datos |
| Qué migraciones están aplicadas en producción | Es la pregunta que responde `censo-migraciones.yml`, y se contesta contra la base |
| El exit code exacto de las 15 llamadas a `psql` sin `ON_ERROR_STOP` ante un fallo parcial | Razonado sobre el diseño del script, **no ejecutado** contra un fallo real |

---

# 8 · Qué haría yo, y en qué orden

**Cuestan minutos y cierran agujeros abiertos:**

1. **Crear las dos variables de `salud-derivada.yml`** en la v2. Dos minutos, y el centinela de `stock_moloka` deja de mentir después de 27 días. *(Y mirar el primer run.)*
2. **Registrar `envios-modo-caja-igual-que-antes.test.mjs`** en `tests/run.mjs`. Dos líneas.
3. **Lanzar los tres tests huérfanos de Python** desde sus workflows, empezando por `test_guarda_614.py`. Tres líneas.
4. **Copiar `SUPABASE_DB_URL` a la v2** y descomentar el cron de `auditor-diario.yml`. El auditor no se ha ejecutado nunca.

**Correcciones de texto, que cuestan cinco minutos y evitan una decisión equivocada:**

5. **Corregir el párrafo del trackeador en `CLAUDE.md` §4** — dice que los dos workflows solo inyectan `SUPABASE_KEY` y es falso: los dos inyectan también la de servicio. Ese párrafo declara un bloqueo que ya no existe. **Sin borrar la mitad vigente**: las `monitor_*` siguen abiertas a `anon`.
6. **Retirar los cuatro avisos que arrastró la jubilación de `salud_fba`** y poner al día la tabla de informes de §1.3 (sobra SALUD_FBA; faltan INVENTARIO_FBA, TRANSACCIONES y CUSTOM_ANALYTICS).
7. **Borrar `docs/pendiente-bb-envio-duplicado.md`** de la v2: el bug que describe se arregló el 20-ago.
8. **Corregir «75 veces/día» y «`warmer@…`» en el CLAUDE.md de la v2** — es una vez al día, y el correo correcto es el que nombra `docs/usuario-warmer.md`. **La regla de que el warmer no escribe se queda.**

**Un PR cada uno, con alguien mirando:**

9. **La guarda anti-retroceso en `procesador_internacional.py`** — con la nota de qué caza y qué no (punto 3.1).
10. **El `_isd_con_fba` del #174**, y ejecutar el fichero antes de fusionar.
11. **Fusionar el #320**, que está listo hoy.
12. **Versionar los tres objetos del Trackeador** en una migración, aunque sea escribiendo lo que ya existe.

**Merecen decidirse en frío, no en caliente:**

13. **Que el CI de la v2 compare los ficheros de test con los registrados**, y que el presupuesto de asserts también sepa ponerse rojo cuando **baja**. Hoy es un techo sin suelo.
14. **Borrar las dos referencias a `vigilante-acantilado.yml`** — o escribir el workflow. Lo que no puede quedarse es el log diciéndole a alguien que existe.
15. **Sacar la lista de países del escáner a una constante** antes de meter Alemania.
16. **Un CI mínimo para moloka-app.** El #174 es la prueba de lo que cuesta no tenerlo: un fallo que muere en la primera línea, siete días pareciendo listo.

---

# 9 · El auditor independiente

Antes de entregar, un auditor que **no había escrito ni una línea de este informe** intentó tumbarlo, con los dos repos delante y la orden de firmar. Comprobó por su cuenta las cifras y los veredictos duros — incluido el más caro, el `NameError` del PR #174, que verificó **contra el diff real de GitHub** antes de leer lo que yo había escrito, y al que llegó por su cuenta.

**Encontró tres cosas, y las tres están ya corregidas arriba:**

1. **Un error numérico mío** en `restaurar-staging.yml`: dije 19 llamadas a `psql` y 4 con `ON_ERROR_STOP`; son **14 y 3**. Corregido en §1.4, con las dos formas en que me equivoqué escritas, porque son las mismas contra las que avisa CLAUDE.md.
2. **`PAISES_RENTAB` no es deuda, es una decisión medida.** Yo lo había listado junto a los pendientes de verdad. Corregido en §6.2 — y era importante, porque un aviso mal encuadrado empuja a «arreglar» código sano, que es literalmente lo que este informe existe para evitar.
3. **El «no hay nada todavía» de CLAUDE.md trae su propio descargo** cinco líneas más abajo. Bajado de 🔴 a 🟠 en §4.1.

**Lo que él tampoco pudo verificar** (su entorno no tenía terminal, así que no pudo ejecutar ni consultar el repo privado): que los 28 secretos existan de verdad en GitHub, el log del run de `salud-derivada.yml`, que los tres tests de Python pasen, y el estado del PR #320. **Esas cuatro sí las ejecuté yo** y están arriba con su resultado; quedan con una sola comprobación, no con dos.

Su firma, literal:

> **FUSIONABLE** — «solo encontré un error numérico de bajo impacto que no cambia ninguna conclusión ni recomendación, y dos matices de encuadre menores que no invalidan ningún hallazgo. No hay credenciales, no se mide la base de datos, y ninguna afirmación falsa cambia una decisión del informe.»

---

*Auditoría hecha leyendo el código de los dos repos en `origin/main`. Todo lo afirmado aquí se ha comprobado ejecutando, contando o leyendo el fichero entero; lo que no, lleva escrito «no verificado». Ninguna medición se ha hecho contra la base de datos y no se ha escrito nada en producción. Ni una credencial en el texto.*
