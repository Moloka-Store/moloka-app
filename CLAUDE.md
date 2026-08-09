# CLAUDE.md — moloka-app

Este fichero contiene lo que **no puedes deducir leyendo el código**: el porqué, las trampas y las
convenciones no estándar de esta casa. La estructura del repo, las dependencias y la arquitectura
las ves tú solo — no están aquí a propósito.

---

## 0. QUIÉN USA ESTO

**Elena usa esta app a diario para operar un almacén real.** Moloka Store S.L.U. vende en Amazon
FBA Pan-EU (ES/IT/FR), Miravia y web propia. Si rompes la app, se para el almacén.

- **`index.html` (v1) está CONGELADO.** Solo bugs críticos. Es un monolito y no se refactoriza.
  Si tu cambio lo toca, párate y pregunta.
- **Cualquier cambio que roce la operativa de Elena se avisa ANTES de desplegar.**
- **Fernando no es programador.** Es economista y contable. Explica en cristiano, con analogías
  contables si ayudan. Él aprueba todos los PR.

---

## 1. LAS REGLAS QUE NO SE REINTERPRETAN

### 1.1 Identidad: dos ejes, no un maestro único
- **EAN = el producto físico.** Universal, cero huecos. Lo escribe la **factura** (fuente dura).
- **ASIN = la capa Amazon**, por país. Lo pega Fernando a mano desde el Seller.
- **SKU = un traductor de los informes del Seller. JAMÁS llave maestra.** Fue el error de la v1:
  cruzar por SKU dejó fuera al 41,7% del catálogo. El SKU **nace y muere**; un mismo ASIN puede
  tener dos vidas de SKU con stock en países distintos.
- **La llave de la capa Amazon es (ASIN, país).** Nunca el SKU.
- **"ASIN→EAN es 1:1" es la regla DE MOLOKA, no un hecho de Amazon.** Keepa devuelve varios EAN
  para algunos ASIN. Ir siempre ASIN→EAN, nunca EAN→ASIN (ambiguo con los packs).
- **Ningún informe del Seller trae EAN.** El puente EAN↔ASIN es responsabilidad de Moloka.
- **Fuentes duras escriben identidad; las blandas nunca.** Factura → EAN. All Listings → ASIN/SKU.
  **Keepa NO escribe identidad**, solo rellena huecos, y **NADA en fichas `es_chase=true`**.
- **`moloka_ean_norm()` ya existe en producción** (esquema `public`, `IMMUTABLE`, sin
  `SECURITY DEFINER`): úsala, no la reescribas.
  **REGLA para lo que se construya: va a los DOS lados de todo cruce por EAN.** No es una
  descripción de hoy — hoy solo hay UN cruce que la usa (la vista de `procesador_keepa_escaparate.py`).
  Es la regla para el siguiente.

### 1.2 El país es una FILA, nunca un sufijo de columna
Sin excepciones. Si una tabla necesita `stock_es`, `stock_it`, está mal diseñada.

### 1.3 Los informes de Amazon JAMÁS se suman entre sí
Cada uno responde **una** pregunta y son universos distintos:

| Informe | Es | Responde |
|---|---|---|
| **INTERNACIONAL** | El INVENTARIO (replica la pantalla del Seller) | ¿Cuánto tengo y dónde? |
| **SALUD_FBA** | GESTIÓN (rotación, alertas). Solo ES. Llega ~10 días tarde con altas | ¿Cómo de sano está? |
| **PANEU_APTOS** | La dimensión Pan-EU. Es película: cambia en horas | ¿Qué me deja Amazon? |
| **LEDGER** | El EXTRACTO. Libro append, no foto | ¿De dónde salió y a dónde fue? |
| **ALL_LISTINGS** | La identidad (ASIN/SKU) | ¿Qué tengo listado? |
| **KEEPA (CSV)** | Mercado, fotos, competencia | ¿Qué pasa fuera? |

Si tu código suma dos de estos, está mal. Si dos discrepan, **no promedies ni lo achaques al
desfase: es un dato, y hay que explicarlo al dígito.**

### 1.4 Un informe caducado no da información incompleta: da información FALSA
Hermano de: **una cifra sin la fecha del dato que la sostiene es una cifra que miente.**

### 1.5 Los cálculos de rentabilidad de Amazon NO entran
Fernando: *"los míos son los buenos"*. Las fórmulas de rentabilidad, IVA y alertas están validadas
al céntimo y **no se reinterpretan**. `estimated-cost-savings-*` de salud_fba es **marketing**
(prometía 10.747 € con un almacenamiento real de 94,86 €/mes): jamás usarlo como "ahorro".

### 1.6 Los TRES CAJONES: cada tabla se escribe de UNA manera
Antes de escribir en una tabla, mira **en qué cajón está**. El cajón decide qué pasa con lo que ya
había, y los cajones no se mezclan:

| Cajón | Qué se hace con lo viejo | Quién vive aquí |
|---|---|---|
| **FOTO** | **Se tira la hoja vieja.** Lo que no viene en el fichero se **BORRA** | `salud_fba`, `listings_amazon`, `keepa_escaparate`, `paneu_aptos` + `paneu_oferta_pais`, custom analytics |
| **PELÍCULA** | **Se apila. NUNCA se borra** | `movimientos`, el ledger |
| **MAESTRO** | **Se MARCA. Ni se borra ni se sustituye** | `productos` |

- Una **FOTO** contesta *"¿cómo está esto AHORA?"*. Una fila que sobrevive a su fichero es un
  fantasma que descuadra el cruce. La memoria histórica **no vive aquí**: vive en la Película.
- Una **PELÍCULA** es un libro de asientos: append, jamás update destructivo. Borrar una línea del
  ledger es falsificar el extracto.
- Un **MAESTRO** es la identidad. Un producto que deja de venderse no se borra: se **marca**
  (`activo=false`). Borrarlo deja huérfanos los movimientos que lo citan.

🔴 **El error caro es tratar un cajón como si fuera otro.** Un upsert-sin-DELETE convierte una Foto
en un collage de dos días (fue el caso real de salud_fba, §2); un DELETE en una Película destruye
el histórico y no hay de dónde recuperarlo.

---

## 2. LOS PROCESADORES: EL PATRÓN

**El procesador nuevo se tiene que parecer a los que ya están en producción. Míralos antes de picar.**

- **NO HAY CABOS SUELTOS: el procesador no elige. O ABORTA o GRITA en el dato.**
  Fichero que no se entiende → aborta. Fichero que cuenta algo nuevo → guarda y avisa.
  Un aviso que solo vive en el log NO es un aviso.
- **Las guardas NO se copian entre procesadores: se MIDEN contra el fichero real de ese informe.**
  También para descartarlas (la guarda "una sola fecha" no vale para Keepa: su fecha vive en el
  nombre del fichero).
- **Cada fichero tiene SU encoding. No lo copies entre procesadores: mídelo contra el fichero real.**
  Lo que hay medido hoy, según el procesador de cada uno:
  - **PANEU_APTOS, SALUD_FBA y KEEPA → traen BOM** (`utf-8-sig`, con `cp1252` de reserva).
  - **ALL_LISTINGS → no consta medido.** Su procesador solo decodifica de forma tolerante; que no
    reviente no demuestra que el fichero lleve BOM.
  - **INTERNACIONAL → sin BOM** (medido en el PR #2; hoy solo vive como comentario en
    `procesador_paneu_aptos.py`). **LEDGER → no consta.** Ninguno de los dos tiene procesador en
    este repo todavía: cuando lo tengan, se mide, no se hereda de aquí.
- **El LEDGER se descarga SIEMPRE en `.txt`.** El `.csv` se come los ceros a la izquierda de
  MSKU/ASIN/FNSKU. Lo avisa el propio Seller.
- **La DESPENSA COMÚN:** `crudo` guarda todas las columnas aunque hoy no se usen. Caso real: el
  `sales-rank` llevaba semanas descargándose sin mirarse — y resultó ser el detector de ASIN muertos.
- 🔴 **Los CSV de Keepa en Storage (`informes/keepa_escaparate/`) NO SE BORRAN NUNCA.** Dejaron de
  ser fichero temporal el día que `keepa_escaparate_hist` dejó de guardar `crudo` (29-jul-2026):
  pasaron a ser **el archivo histórico permanente**. Ese `crudo` era copia byte a byte del CSV y se
  sacó de la base porque estaba duplicado con 25× menos margen (BD 500 MB vs Storage 1 GB), pero las
  512 claves que solo viven ahí siguen siendo munición del trackeador. **El rescate de cualquiera se
  hace por `keepa_escaparate_hist.fichero` → `informes/keepa_escaparate/<fichero>`.** Borrar esos CSV
  para "hacer sitio" es borrar el histórico sin vuelta atrás. Es la CONTRAPARTIDA del `DROP COLUMN
  crudo` (migración `2026-07-29_keepa_hist_drop_crudo.sql`): el DROP solo fue seguro porque el CSV se
  conserva. La misma regla aplica a cualquier `crudo` que en el futuro se mueva de la BD al Storage.

### Trampas medidas (no re-descubrir)
- **Filas fantasma: RESUELTO (PR #33, 20-jul-2026).** Antes las tablas-foto se cargaban con upsert
  **sin DELETE**: si el informe encogía (salud_fba: 195→188 SKU en dos días), quedaban filas viejas
  conviviendo con las nuevas. **Ya no. La Foto tira la hoja vieja** (§1.6). Las cuatro cañerías
  heredan el patrón de `foto_comun.py`: lo que no viene en el fichero se BORRA, con guarda
  anti-encogimiento (<50% de las filas previas → ABORTA) **antes** del borrado, y borrado y carga en
  la misma transacción.
  ✅ **El ACUERDO de "no se lanza salud_fba en `aplicar`" queda LEVANTADO.** La decisión que
  esperaba ya está tomada: se lanza como cualquier otro.
  ⚠️ Lo que sí sigue mereciendo aviso: **la PRIMERA pasada `produccion`+`aplicar` de cada cañería
  dará de baja los fantasmas acumulados**. Es lo que se busca, pero mira las bajas que anuncia el
  ensayo antes de aplicar.
  El ledger no tiene este problema: es Película, no Foto.
- **Escritura masiva: SIEMPRE por lotes (`execute_values`), JAMÁS un `cur.execute()` por fila
  (PRs #65-#68 y #70, 29-jul-2026).** El runner de Actions está en EEUU y Supabase en `eu-west-1`
  (Irlanda): cada `cur.execute()` es un viaje transatlántico de **~90 ms**. Un
  `for fila in filas: cur.execute(...)` de 3.806 filas = **5 m 48 s esperando a la red** (PanEU,
  medido en el run #14); el mismo volcado con `psycopg2.extras.execute_values` baja a **<10 s** y la
  ventana de locks sobre la tabla de Elena de ~6 min a segundos. Los cinco que iban fila a fila
  (paneu, internacional, salud_fba, all_listings, keepa) ya están por lotes; el patrón está calcado
  de `procesador_ledger.py`, que nació así. **Si mañana nace un procesador nuevo, nace por lotes.**
  🔴 **La trampa del lote:** con `execute_values` todas las filas van en UN comando, así que dos con
  la misma clave del `ON CONFLICT` abortan con `ON CONFLICT DO UPDATE command cannot affect row a
  second time` (fila a fila no saltaba: la segunda pisaba a la primera en silencio). Qué significa un
  duplicado se decide POR PROCESADOR y NO se copia entre ellos:
  - **Duplicado = "la última gana"** (paneu, all_listings: el informe puede repetir clave y es
    legítimo) → **deduplicar en Python** por la clave del `ON CONFLICT` antes del lote, quedándote con
    la última; y si descartas algo, GRÍTALO al log (fila a fila era invisible).
  - **Duplicado = informe CORRUPTO** con una guarda que ya ABORTA por él (salud_fba y keepa: Guarda 2,
    *"el procesador NO elige"*) → **NO deduplicar**: dedup enmascararía justo lo que la guarda manda
    gritar. Y dedup por la clave REAL de cada tabla, nunca una "colapsada" que dependa de un supuesto
    (internacional: el histórico se deduplica por `(sku, country, fecha_foto)`, no por `(sku, country)`).
  🔒 **Prueba de que el cambio no movió ni un dato:** mismo fichero, viejo(`main`) vs nuevo, `md5` del
  CONTENIDO de la tabla —`md5(string_agg((to_jsonb(t) - '<col now()>')::text, '|' order by pk))`,
  excluyendo la columna `now()` (`procesado_en`/`procesado_at`/`capturado_en`, cada tabla la suya)—
  idéntico. El diff de logs solo prueba los recuentos, NO que cada columna caiga en su sitio (el
  riesgo real al pasar a tuplas en `execute_values`).
- **Dos fórmulas de stock que NO se unifican.** Son asientos distintos y ninguna "corrige" a la otra:
  - **La columna de Amazon** (`Inventory Supply at FBA`, en salud_fba) `= available + fc-transfer +
    inbound-quantity`, **SIN `reserved`**. Verificado fila a fila; lo comprueba la Guarda 6. Es la
    aritmética interna del informe — **no es el stock de Moloka**.
  - **El stock de Moloka** (v1, `moloka_actualizar_nube.py`) `= available + reserved`, con
    **`fc-transfer` DENTRO de `reserved`** e **`inbound` aparte** (está de camino). El v1 rechaza a
    propósito la columna de Amazon: "inflaba el stock".
  🔴 **`fc-transfer` cambia de bando entre las dos.** Llevar el "SIN `reserved`" de la primera al v1
  borra el FC Transfer del stock — el error exacto contra el que el v1 avisa por escrito.
- ⚠️ **`productos.unidades_compradas` cuenta unidades FÍSICAS, no facturadas: el nombre engaña.**
  "Compradas" suena a lo que dice el papel y no lo es. Con los packs se ve a la vista: una línea de
  400 paquetes facturados que son 100 unidades físicas deja `unidades_compradas = 100`.
  **Está BIEN así y no se cambia.** Su único uso real es elegir la ficha principal al consolidar
  duplicados (*"Principal: la que tiene mas unidades_compradas historicas"*, `index.html:10171-10172`)
  y ahí las físicas son lo correcto: contando facturadas, la ficha de packs ganaría artificialmente.
  **No entra en costes ni en rentabilidad**, así que no hay riesgo contable — solo un nombre que
  miente. Medido el 30-jul-2026.
- **`FNSKU = ASIN` ⇒ listing commingled** (pozo común por EAN entre vendedores). FNSKU propio
  (`X0…`) ⇒ etiquetado. Explica stock que aparece en países donde no enviaste nada.
- **El "país" del INTERNACIONAL puede ser de PROGRAMA, no físico** (stock en Praga contado como DE).
  Y CZ/SK no existen para ese informe, pero el ledger demuestra stock físico allí.
- **Dominios de Keepa: 3=DE · 4=FR · 8=IT · 9=ES** (10 es India). Ojo con el 8: es IT, no FR.
  *(Aquí vivió un aviso de "bug latente en `DOMINIO_NUM`" que se quedó mintiendo **10 días**
  después de estar arreglado — el mapa se corrigió el 20-jul-2026 en `007632c` y la nota siguió
  diciendo que estaba mal. Es el ejemplo de andar por casa de §3: **el estado vive en el repo, no
  en las notas**. Si dudas del mapa, míralo en el fichero; si lo cambias, borra la nota.)*

---

## 3. VALIDACIÓN: QUÉ CUENTA COMO PRUEBA

🔴 **PROHIBIDO TEORIZAR.** Si no lo puedes medir en esta respuesta, di **"no lo sé"** y di qué
fichero o consulta lo contestaría. No inventes explicaciones plausibles.

- **La verificación final es SQL contra la BD. NUNCA el log.**
- **Compilar no es ejecutar.** `py_compile` pasa un script que redefine un built-in y peta en
  runtime. Ejecuta contra **el fichero real**.
- **Los datos sintéticos no prueban nada.** Una vista se prueba con la tabla **poblada**.
- **Escribe los números esperados ANTES de correr.** Si no salen, di lo que sale — no ajustes la
  expectativa al resultado.
- **Haz saltar las guardas a propósito** antes de dar un procesador por bueno.
- **"Lo ha revisado un agente" NO es prueba.** Un revisor lee código, no lo ejecuta.
- **Greps parciales no son lectura.** Si te preguntan "¿seguro que el código hace X?", lee el
  fichero entero.

### El estado vive en el repo, no en las notas
- Antes de afirmar el estado de cualquier pieza: **míralo**. Las notas de ayer mienten hoy.
- `raw.githubusercontent.com` tiene retraso de caché tras un commit. Para leer el repo desde fuera:
  **tarball por `codeload.github.com`**. La API de GitHub sin token da 60 peticiones/hora por IP.

---

## 4. SEGURIDAD

- 🔴 **Las credenciales NUNCA van en el código ni en un mensaje.** Viven en GitHub Secrets, Vercel
  y R2. Una llave que aparece en un chat está quemada y se regenera.
  **Introducir credenciales no es algo que hagas tú: se lo pides a Fernando.**
- **Supabase es PRODUCCIÓN.** Desde una sesión: **solo lectura**. Toda escritura va por
  rama → PR → Fernando aprueba → ensayo en staging → producción.
- **Todo lo NUEVO nace CERRADO:** RLS activo y 0 políticas. Vistas `security_invoker`. Funciones
  `IMMUTABLE`, sin `SECURITY DEFINER`.
- 🔴 **Pero "nace cerrado" NO es el estado por defecto: hay que REVOCAR antes de conceder.**
  Medido el 30-jul-2026 en `pg_default_acl` de las DOS bases: en `public`, toda **tabla o vista**
  nueva nace con **`arwdDxtm` concedido a `anon` Y a `authenticated`**, y toda **función** nueva con
  `EXECUTE` para `anon`. Son DEFAULT PRIVILEGES de Supabase y **un `revoke … from public` NO los
  quita** (son grants explícitos a un rol, no a `public`). Si escribes `grant select, insert to
  authenticated` y te quedas ahí, **el grant no añade nada porque ya lo tenía todo**: el `relacl`
  sigue diciendo `authenticated=arwdDxtm`. Hay que revocar a **cada rol por su nombre** antes de
  conceder — `revoke all on <objeto> from public, anon, authenticated;` y luego el `grant` mínimo —
  y **MEDIR** el resultado (`pg_class.relacl` / `pg_proc.proacl`), no suponerlo.
  Afecta a **todo objeto nuevo**, también a las tablas que crean los procesadores.
- 🔴 **Y no basta con revocar AL CREAR: hay que revocar CADA VEZ QUE SE RECREA.**
  `CREATE OR REPLACE` **conserva** el ACL; **`DROP` + `CREATE` lo PIERDE**, y el objeto vuelve a nacer
  con el default puesto, o sea con `anon` dentro. Caso real medido el 30-jul-2026:
  `entrada_factura_pvd` tenía `anon=X` en **staging** y no en producción, **aunque su migración lleva
  el `revoke`** — alguien la había recreado con DROP+CREATE y aquel revoke ya no aplicaba a la función
  nueva. No era explotable (aritmética pura, `IMMUTABLE`, no lee tablas), pero **las dos bases dejaron
  de ser iguales, y entonces un ensayo en staging ya no demuestra nada sobre producción**. Corregido
  con un `revoke … from anon` en staging.
  Regla práctica: **si la migración lleva un `drop`, el `revoke` va DESPUÉS del `create`, en la misma
  migración, y se mide el ACL al terminar.**
- **La v1 tiene escritura anónima abierta** (deuda estructural). **No se toca a mitad de vuelo**:
  se cierra en la v2 con Auth + RPC. El problema no es la llave `publishable` (es pública por
  diseño): son las políticas.
- **SP-API: jamás con credenciales de Moloka SL.** Decidido y cerrado. Las cuentas de Moloka
  (Elena) y Fernando (autónomo) están separadas a nivel de credenciales.
- **Confirmar una factura SIEMPRE inyecta stock.** Nunca subir facturas antiguas retroactivamente.
- 🔴 **PENDIENTE — el backup NO copia los permisos: restaurar te deja la base ABIERTA.**
  `backup-bd.yml` vuelca con `--no-privileges`, así que el fichero **no contiene ni un `GRANT` ni un
  `REVOKE`**. Dicho en alto y sin adornos: **el día que haya que restaurar de verdad, la base vuelve
  con los ACL por defecto de Supabase — o sea, con `anon` dentro de todo** (es el mismo
  `pg_default_acl` de los dos puntos de arriba: los objetos nacen con `arwdDxtm` para `anon` y
  `authenticated`, y aquí nadie revoca después). Restauras el incendio y te queda la casa abierta.
  **Esto no es una nota al pie: es un frente propio y hoy está abierto.** Lo que falta por decidir en
  frío es cuál de los dos caminos: que el volcado se lleve los privilegios (quitar `--no-privileges`,
  y entonces el dump arrastra dueños y ACL, con lo que eso implica al restaurar en otro proyecto), o
  que el restore aplique al terminar un guion de permisos propio y **medido**. Sin cerrar desde el
  9-ago-2026.
- ⚠️ **PENDIENTE — la copia de FICHEROS a R2 no tiene simulacro de restauración.** Desde el
  30-jul-2026 el backup diario (`backup-bd.yml` + `backup_storage.py`) copia a R2 los buckets
  `facturas-pdfs` e `informes` (las facturas de proveedor y el archivo histórico de Keepa). Pero
  `restaurar-staging.yml` solo ensaya el incendio de la **BD**: **esos ficheros no los recupera ni
  los abre nadie nunca.** Es el MISMO agujero que motivó todo esto (una copia en la que se confía y
  que nadie ha probado), en el otro activo. Falta un `restaurar-ficheros` que baje de R2 una muestra
  y compruebe que abre. Hasta que exista, la copia de ficheros está **hecha pero no verificada de
  extremo a extremo**. *(El backup sí tiene número de control externo contra `storage.objects`, así
  que una copia CORTA no pasa por buena — pero eso valida la subida, no la restauración.)*

---

## 5. CÓMO SE TRABAJA AQUÍ

- **UN PR, UNA COSA.** Sin excepciones.
- **Antes de picar: lee cómo se hizo lo anterior.** Hay procesadores en producción que funcionan;
  el siguiente se les tiene que parecer. Si algo se aparta del patrón, dilo y explica por qué.
- **Las dudas de diseño no se resuelven en caliente.** Se anotan en una línea y se deciden en frío.
- **Cuando Fernando dice "esto no me cuadra", PARA y baja al dato.** Acierta ~95% de las veces.
  Casos reales: un bug oficial de la API de Amazon (FBA_CORE), un envío perdido de 24 uds, un ASIN
  borrado con 12 uds dentro. En los cuatro, la explicación cómoda era la equivocada.
- **Darle la razón sin medir es fallarle.** Si tienes el dato y contradice lo que dice, enséñaselo.
- **Distingue "podría" de "está documentado".** Una hipótesis bien redactada no es un hecho.
  Si no lo has verificado ahora mismo, dilo.
- **Antes de decir "no se puede":** eso es una hipótesis. Agota la búsqueda (documentación oficial,
  la propia herramienta, la web). *"No conozco una manera"* ≠ *"no existe una manera"*.

### Gotchas del entorno
- **La máquina de Fernando es Windows y su terminal es PowerShell**, pero las herramientas ejecutan
  **Bash**. `&&` no funciona en su terminal; las here-strings de PowerShell (`@'...'@`) corrompen
  los mensajes de commit si las usas en Bash. Comandos de una línea, sintaxis Bash.
- **`workflow_dispatch` exige que el `.yml` esté en la rama por defecto.** Orden forzoso:
  fichero → merge → ensayo.
- **Los commits de este repo se firman con la dirección noreply de GitHub.** El repo es PÚBLICO:
  no publiques correos reales en la historia. La identidad está en `git config --local`, nunca
  `--global`.

---

## 6. DÓNDE ESTÁ EL PROYECTO AHORA

La v2 ("el bicho") se construye con **patrón estrangulador**: nace al lado de la v1, sobre la misma
Supabase, y Elena se muda pestaña a pestaña. **Los datos no se mudan: se curan.** Una BD nueva serían
dos verdades y un descuadre garantizado.

**Fase 0 (la capa de datos) va PRIMERO** y está a medias. De la app v2 en sí (repo, pantallas, Auth)
no hay nada todavía, y está bien.

Orden de mudanza acordado: Inventario → Inicio → Alertas → Movimientos → Rotación+Rentabilidad →
*(frontera lectura/escritura)* → Entrada → Facturas → Envío FBA → Motores.

*Para el estado exacto de cada pieza: míralo en el repo y en la BD. No lo pongas aquí — caduca en horas.*
