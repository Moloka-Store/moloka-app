# Tests, falsos verdes y las dos direcciones

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)

## 3. VALIDACIÓN: QUÉ CUENTA COMO PRUEBA


- 🔴 **UN TEST VERDE SOLO CUENTA SI HAS VISTO SU NOMBRE EN LA SALIDA.** El «✅ TODO OK» del final
  **no demuestra que tu suite se haya ejecutado**: demuestra que no falló ninguno de los que
  corrieron. Si el tuyo no está en la lista, no ha corrido — y el runner no tiene forma de saber
  que falta. **Es el falso verde peor de todos: no es un test que falla, es un test que no existe**,
  y encima te da la sensación contraria.
  *Medido el 10-ago-2026 en `moloka-app-v2`: un suite nuevo quedó con el `import` puesto y sin su
  entrada en el array `SUITES` de `tests/run.mjs`. `npm test` dio «TODO OK» con 16 casos sin
  ejecutar. Se cazó al ir a leer el suite por su nombre en la salida en vez de fiarse del verde.*
  Regla práctica: después de añadir un suite, `npm test | grep "<su cabecera>"`. Si no sale, no
  existe. Vale igual para cualquier runner en el que registrar el test sea un paso aparte de
  escribirlo.
- 🔴 **ANTES DE CREAR RAMA, `git fetch`.** Una rama nacida de un `origin/main` viejo construye
  sobre un bug **ya arreglado**, y los tests no lo cazan porque el arreglo simplemente **no está**:
  no hay nada que se ponga rojo. Sales con todo en verde y devuelves el fallo a `main` por la
  puerta de atrás, encima con la firma de haberlo verificado.
  *Medido el 10-ago-2026: la rama de las seis correcciones de pantalla se creó de un `origin/main`
  que no tenía el PR recién fusionado con el arreglo del doble conteo de la tira de país. Se
  descubrió por casualidad, buscando otra cosa —el suite que no aparecía por su nombre, la regla de
  arriba— y se integró antes de seguir.*
  🔑 Y de ahí, lo que hay que hacer cuando pasa: **integrar `origin/main` EN CUANTO se detecta**, no
  al final. Cuanto más tarde, más código escrito sobre la base equivocada. Ojo también con `gh pr
  merge`: fusiona en GitHub y **no actualiza tu `origin/main` local** — hace falta el `fetch`.
- 🔴 **HAY VARIAS SESIONES SOBRE ESTE REPO A LA VEZ, y el accidente típico se lleva trabajo
  ajeno por delante.** El worktree que vas a crear puede tener el nombre ya cogido por otra
  sesión; entonces `git worktree add` falla, y si lo encadenaste con `&&`, **el `cd` no se
  ejecuta y todo lo que venga después corre en el repo principal** — que está en LA RAMA DE
  OTRO. Un `git add -A && git commit` ahí se lleva sus ficheros sin tocar dentro de tu commit.
  *Medido el 11-ago-2026: pasó exactamente eso, y el commit cayó en `claude/buzon-keepa-url`.
  Se salvó porque el `push` falló solo (la rama no tenía remoto) y se deshizo con `git reset
  --mixed HEAD~1`, que quita el commit SIN tocar los ficheros — el `--hard` habría borrado el
  trabajo de la otra sesión.*
  🔑 Las tres cosas que lo evitan, por orden de utilidad:
  1. **Nombre de worktree único por encargo** (`moloka-v2-<tema>`), y si `add` falla, PARAR —
     no seguir con los comandos encadenados.
  2. **`git add <fichero>`, no `git add -A`**, cuando el cambio son uno o dos ficheros. Es lo
     único que habría hecho inofensivo el accidente.
  3. Antes de commitear en un sitio del que no vienes: `git branch --show-current`.
- 🔴 **EL CI EN VERDE NO PRUEBA QUE UNA FEATURE ESTÉ VIVA.** Prueba que compila y que lo
  que hay escrito pasa; no que lo que escribiste llegue a ejecutarse.
  *Medido el 11-ago-2026: al fusionar dos ramas que tocaban la misma función, el merge dejó
  **dos `return construirInventario(...)` seguidos**. El primero ganaba, el segundo era
  código muerto, y con él se anulaba una feature entera —el envío de la buy box no llegaba
  al builder—. TypeScript no dice nada de eso, el lint tampoco, y el CI salió verde.*
  🔑 **Toda feature nueva necesita al menos UN assert que falle si se desactiva.** No basta
  con que haya tests del cálculo: tiene que haber uno que compruebe que el dato **llega**.
  Los que cazaron aquello fueron los del suite, que sí miran el resultado con el dato
  puesto — el mismo día había 1.887 y por eso saltó a la primera.
  ⚠️ Y el corolario, que es el que se olvida: **si desactivas la feature a mano y el suite
  sigue verde, el suite no la está probando.** Es la versión de «haz saltar las guardas a
  propósito» aplicada a las funcionalidades, no solo a las guardas.
  🔴 **Y NO BASTA CON QUE EL TEST PASE: HAY QUE ROMPER LA COSA A MANO Y VERLO PONERSE ROJO.**
  Las DOS direcciones, siempre, y la segunda es la que prueba algo — un test que sólo se ha
  visto en verde no se ha probado, se ha ejecutado.
  *Medido el 11-ago-2026, y el ejemplo es el test que venía a cazar justo esto: se escribió
  un test para que ninguna alerta se quedara sin filtro en el Cockpit; pasó a la primera.
  Al comentar la línea `// tipo: 'BB_DISCREPA_FUENTES',` para verlo morir, **siguió en
  verde**: buscaba el patrón sobre el fichero crudo y el regex casa igual dentro de un
  comentario, así que daba por vivo el código comentado. El vicio que el test perseguía
  estaba dentro del test.*
  ⚠️ Ojo al patrón, porque se repite: **lo que se lee como texto (grep, regex, anclas) no
  distingue código de comentario.** Si un test mira el fichero como cadena, quita los
  comentarios antes de mirar — o comprobará que algo está escrito, no que se ejecuta.
  🔑 Vale para todo, no sólo para tests: una guarda nueva se hace saltar, un aviso nuevo se
  provoca, y una feature nueva se desactiva. Si al romperla no pasa nada, no estaba puesta.
- 🔴 **CUANDO UNA REGLA SE REPITE, DEJA DE ESCRIBIRSE Y SE CONVIERTE EN FUNCIÓN.**
  Una regla escrita **se olvida en veinte minutos**; una regla convertida en herramienta se
  aplica sola.
  *Medido el 12-ago-2026, y el caso es contra mí: por la mañana se escribió la regla «lo
  que se lee como texto no distingue código de comentario», se le puso un test al censo y
  se corrigió una atribución por ella. **Veinte minutos después**, al escribir un detector
  en SQL a mano, el mismo fallo: un regex casó la palabra «ventas» dentro de la prosa
  española de un `comment on column` y clasificó la tabla como creada por el conector.
  La regla estaba escrita, probada y aplicada en Python — y no protegió al SQL de al lado.*
  🔑 **La forma de saber que toca:** si al escribir algo piensas «esto ya lo sé», es la
  segunda vez. La tercera no la vas a ver venir.
  ⚠️ Y el corolario que evita el daño peor: **una sola implementación por regla.** Dos
  parseos distintos que miden lo mismo son dos verdades esperando a discrepar; y cuando se
  encuentra una trampa, se arregla en un sitio y queda arreglada en todos.
  🔬 Sin nombrarlo, este movimiento ya se hizo cuatro veces: `v_salud_escaner` (la regla
  del `presente=true` como objeto, no como nota), el centinela de despliegue (la regla del
  merge, en el repo y no en la memoria de alguien), el canario RLS (el checklist como
  fichero) y `sin_comentarios()` (la regla del comentario, como código con test).
- 🔴 **LA COMPROBACIÓN QUE NO PUEDE FALLAR: el error más repetido, y siempre sale VERDE.**
  Antes de fiarte de una comprobación, pregúntate **qué la pondría roja**. Si no hay
  respuesta —si el resultado sale igual mida lo que mida— no comprueba nada, y encima
  tranquiliza. Es el peor de los fallos: no da error, da permiso.
  *Tres veces en dos días, con tres caras distintas y la misma forma:*
  | | la comprobación | por qué no podía fallar |
  |---|---|---|
  | 1 | El pin del `search_path`: longitud **con** y **sin** pin en el mismo `UNION` | `set_config(…, true)` es de **transacción**: fijado en la primera rama, la segunda ya lo tiene. Salía **379 y 379** siempre |
  | 2 | Testigo de entorno: `current_database()` y `count(*) from productos` | staging es un **clon restaurado** de producción: coinciden **por construcción**. `postgres` y **455** en las dos |
  | 3 | La huella `es_case` para saber si `v_escaner_ultimo` estaba al día | ese texto está en la versión **vieja y en la nueva** (es una columna del `SELECT`). Lo que cambió fue la cláusula de dedup. Daba `vigente` sobre la vista vieja |
  | 4 | `bash -n` sobre el script extraído de un `.yml`, para validar su sintaxis | el extractor había petado por el encoding y no escribió nada. **Validar la nada siempre sale bien.** El `-n` decía OK sobre 0 bytes |
  🔑 **La forma común: la entrada no puede producir un resultado distinto** — porque se
  comparan dos cosas iguales por construcción (1, 2, 3) o porque directamente **no hay
  entrada** (4). ⚠️ De ahí el reflejo que hay que coger: **antes de creerse un OK,
  mirar que había algo que comprobar.** Un recuento a cero, un fichero vacío o una
  lista sin filas convierten cualquier validación en un trámite.
  Dicho del otro modo: se comparan dos cosas que son iguales por construcción. Dos ramas
  de la misma transacción, dos copias de la misma base, dos versiones que comparten ese
  texto. El resultado no depende del estado que se quería medir.
  ⚠️ Y el corolario para el caso 3, que aplica a toda huella o marcador de versión: **se
  elige contra la versión VIEJA, no contra la nueva.** Que aparezca en la actual no prueba
  nada; hay que comprobar que **NO** aparece en la anterior. La huella va sobre lo que
  **cambió** —la cláusula, la condición, la firma—, nunca sobre un nombre que las dos
  versiones mencionan.
  🔬 Las tres las destapó **medir con otra vía**, no la propia comprobación: el pin, porque
  el número no cuadraba con uno ya conocido; el testigo, porque se midieron las dos bases a
  la vez antes de escribirlo; y la huella, porque el cruce de `md5` entre entornos vio una
  diferencia que la huella daba por buena.
  🔴 **LA FORMA MÁS FRECUENTE, MEDIDA CINCO VECES EN UN SOLO DÍA: LA COMPROBACIÓN QUE
  MIRA LO QUE NO CAMBIA.** Un assert que busca un texto presente en las DOS versiones —el
  prefijo de una firma, el nombre de una función, una columna del `SELECT`— sale verde
  hagas lo que hagas. 🔑 **Se ancla contra lo que NO debe aparecer**, que es la única mitad
  que se mueve: no «¿está el parámetro?» sino «¿tiene default?»; no «¿existe la marca?»
  sino «¿sigue la excepción que la tapaba?».
  *Los cinco del 20-ago-2026, todos cazados por la MISMA maniobra —romper la cosa a mano y
  ver que no saltaba nada—:*
  | | la comprobación | por qué no podía fallar |
  |---|---|---|
  | 1 | el test de la paginación | los asserts usaban el fixture del propio test, que calculaba con SU copia de la cascada |
  | 2 | el test de la velocidad efectiva | el servidor de mentira nunca llegaba a descuadrar |
  | 3 | el test del criterio del negro | el caso real no discriminaba: sus motivos estaban en países que la app no mira |
  | 4 | `isd` sin default | el regex casaba el PREFIJO de la firma, así que daba verde con el default puesto |
  | 5 | el assert del ISD en el escáner | sumaba la tarifa FBA **a mano** en vez de leer `incluye_fba`, así que la tabla podía decir lo contrario |
  ⚠️ Los cinco eran tests **nuevos, escritos ese día, para cazar un bug recién medido** — y
  ninguno lo habría cazado. Escribir el test no es la prueba; verlo rojo sí.

  ⚠️ **Y la cara B, que es la misma enfermedad: la que SIEMPRE está roja.** Un aviso que
  salta en cada ejecución tampoco informa — se aprende a ignorarlo, y el día que salte por
  algo de verdad ya nadie lo lee.
  *Medido el 12-ago-2026: el censo de `sql/canario_rls.sql` llevaba **20** tablas tapadas
  porque se armó con «las 20 que tienen datos dentro», dejando fuera `web_formato` por
  estar vacía. Tapadas hay **21**. Con ella fuera, el canario reportaba `web_formato` como
  **🔴 TAPADA NUEVA** en cada pasada, para siempre.*
  🔑 **Estar vacía hoy no es motivo para excluir nada de un censo.** «Con datos» y «tapada»
  son dos estadísticas distintas: mezclarlas mete un falso positivo permanente. El recuento
  de filas ya lo da la consulta, columna a columna.
  ⇒ **«Las dos direcciones» son DOS, y la segunda es la que se olvida:**
  | | qué se prueba | cómo |
  |---|---|---|
  | 1 | **que se ponga ROJA cuando toca** | se rompe la cosa a mano y tiene que saltar |
  | 2 | **que esté CALLADA cuando no toca** | se corre con **todo en orden** y tiene que no decir nada |
  La 1 la hacemos casi siempre; **la 2 se nos escapó** — y es la que llevaba al canario
  gritando desde el 11-ago. Las dos cuestan una ejecución cada una, y sin las dos no se
  sabe si la alarma mide algo o sólo hace ruido en una dirección fija.
- 🔴 **UNA VISTA QUE NO PUEDE VER SU FUENTE DEBE CONFESARLO, NO RELLENAR CON UN FALSO.**
  El caso general de «0 filas por RLS ≠ 0 filas porque no hay»: si una vista se apoya en
  una tabla que puede estar tapada, tiene que **distinguir los dos ceros dentro del propio
  dato** —columna a `null` y un veredicto que diga *«no puedo leerla»*— en vez de devolver
  el valor que sale por defecto.
  *Medido el 11-ago-2026: `v_salud_escaner` cruza con `reglas_director` para decir si un
  proveedor tiene director. Esa tabla es una de las 20 con RLS y cero políticas, así que
  con `security_invoker` el join no devolvía nada y la vista decía «sin director» de los
  CUATRO que sí lo tienen. La vista construida para evitar una trampa se metió dentro.*
  🔑 Y de ahí lo que hay que hacer: la comprobación va **en el dato, no en un script
  aparte**. Un canario externo hay que acordarse de mirarlo; una columna a `null` con su
  motivo la ve quien consulta, cuando consulta, sin saber nada de esto.
  ⚠️ Corolario, porque es el que se olvida: **las 20 tablas tapadas contaminan todo lo que
  se apoye en ellas.** Antes de cruzar con una tabla, mírala en `sql/canario_rls.sql`.
- **Los datos sintéticos no prueban nada.** Una vista se prueba con la tabla **poblada**.
- **Escribe los números esperados ANTES de correr.** Si no salen, di lo que sale — no ajustes la
  expectativa al resultado.
- **"Lo ha revisado un agente" NO es prueba.** Un revisor lee código, no lo ejecuta.
