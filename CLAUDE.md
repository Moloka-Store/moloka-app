# CLAUDE.md — moloka-app

Este fichero contiene lo que **no puedes deducir leyendo el código**: el porqué, las trampas y las
convenciones no estándar de esta casa. La estructura del repo, las dependencias y la arquitectura
las ves tú solo — no están aquí a propósito.

---

## 0. QUIÉN USA ESTO

**Esta app (v1) está congelada y ya no la abre nadie (Fernando, 20-sep-2026).** Moloka Store S.L.U. vende casi todo por Amazon
(FBA Pan-EU en seis mercados: ES/IT/FR/DE/NL/BE); Miravia vende poco (su stock lo escribe el cartero desde el 27-oct-2026).

- **`index.html` (v1) está CONGELADO.** Solo bugs críticos. Es un monolito y no se refactoriza.
  Si tu cambio lo toca, párate y pregunta.
- **Se fusiona a cualquier hora**; el parte dice si puede perderse un envío a medias (`escalera-de-migraciones.md`).
- **Fernando no es programador.** Es economista y contable. Explícaselo aterrizado, en lenguaje llano, con analogías
  contables si ayudan. Él decide qué encargo se lanza; el PR lo audita Cowork y lo fusiona Code en una sesión NUEVA, con el recuadro autosuficiente de Cowork (PR, rama, SHA probado, diff vacío contra él, mensaje de fusión); después de fusionar no se repiten las pruebas.

---

## LO QUE NO SE REINTERPRETA

### 1.1 Identidad: dos ejes, no un maestro único
- **EAN = el producto físico.** Universal, cero huecos. Lo escribe la **factura** (fuente dura).
- **ASIN = la capa Amazon**, mismo en los 6 mercados. A mano, del Seller (hasta el 19-oct-2026: ver identidad.md).
- **SKU = un traductor de los informes del Seller. JAMÁS llave maestra.** Fue el error de la v1:
  cruzar por SKU dejó fuera al 41,7% del catálogo. El SKU **nace y muere**; un mismo ASIN puede
  tener dos vidas de SKU con stock en países distintos.
- **La llave de la capa Amazon es el ASIN** (el país es una fila). Nunca el SKU.
- **"ASIN→EAN es 1:1" es la regla DE MOLOKA, no un hecho de Amazon.** Keepa da varios EAN
  a algunos ASIN. Siempre ASIN→EAN, nunca EAN→ASIN (hasta el 19-oct-2026).
- **Ningún informe del Seller trae EAN.** El puente EAN↔ASIN es responsabilidad de Moloka.
- **Fuentes duras escriben identidad; las blandas nunca.** Factura → EAN. All Listings → solo el SKU vacío, y nunca igual al ASIN ni al EAN de la ficha (3-nov-2026, PR #864 de la v2): la base lo rechaza y el cargador de anuncios lo manda a «conflictos».
  **Keepa NO escribe identidad**, solo huecos (hasta el 19-oct-2026), y **NADA en `es_chase`**.

### 1.2 El país es una FILA, nunca un sufijo de columna
Sin excepciones. Si una tabla necesita `stock_es`, `stock_it`, está mal diseñada.

### 1.4 Un informe caducado no da información incompleta: da información FALSA
Hermano de: **una cifra sin la fecha del dato que la sostiene es una cifra que miente.**

### Los tres cajones (§1.6)

| Cajón | Qué se hace con lo viejo | Quién vive aquí |
|---|---|---|
| **FOTO** | **Se tira la hoja vieja.** Lo que no viene en el fichero se **BORRA** | `inventario_fba`, `inventario_internacional`, `listings_amazon`, `keepa_escaparate`, `paneu_aptos` + `paneu_oferta_pais` |
| **PELÍCULA** | **Se apila. NUNCA se borra** | `movimientos`, el ledger, `transacciones_movimientos`, y `demanda_asin` (custom analytics) como **película de LECTURAS** |
| **MAESTRO** | **Se MARCA. Ni se borra ni se sustituye** | `productos` |

---

## VALIDACIÓN: QUÉ CUENTA COMO PRUEBA

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

---

## SEGURIDAD

- 🔴 **Las credenciales NUNCA van en el código ni en un mensaje.** Viven en GitHub Secrets, Vercel
  y R2. Una llave que aparece en un chat está quemada y se regenera.
  **Introducir credenciales no es algo que hagas tú: se lo pides a Fernando.**
- **Supabase es PRODUCCIÓN.** Desde una sesión: **solo lectura**. Cómo llega un cambio a producción
  (sin staging desde el 30-sep-2026): `docs/reglas/escalera-de-migraciones.md`.
- **Todo lo NUEVO nace CERRADO**; `SECURITY DEFINER` solo por uno de tres motivos y con candados:
  ver `docs/reglas/seguridad-permisos.md`.
- **La v1 tiene escritura anónima abierta** (deuda estructural). **No se toca a mitad de vuelo**:
  se cierra en la v2 con Auth + RPC (la llave `publishable` no es el problema: ver `seguridad-permisos.md`).
- **Confirmar una factura SIEMPRE inyecta stock.** Nunca subir facturas antiguas retroactivamente.

---

## CÓMO SE TRABAJA AQUÍ

- **UN PR, UNA COSA.** Sin excepciones.
- 🔴 **EL PARTE SE DEJA EN LA BANDEJA, EN DOS TIEMPOS** (además del PR; `~/Mi unidad/Moloka/bandeja/`,
  sin letra de unidad; hora española). **PROVISIONAL** al empujar: `AAAA-MM-DD-HHMM-PARTE-PROVISIONAL-<tema>.md`,
  con la versión exacta y «pruebas en marcha». **DEFINITIVO** `AAAA-MM-DD-HHMM-tema.md`: pruebas en verde sobre
  la versión final y, uno por uno, lo añadido después. **Primera línea, una sola:** para quién es y cuándo /
  modelo y esfuerzo leídos de la ficha de tu sesión (o «esfuerzo: no lo sé»). Sin esa copia, Fernando hace
  de correveidile: **no depende de que el encargo lo pida**.
- **Una regla nueva no se escribe aquí ni en `docs/reglas/`: va al parte, y entra por el consolidador con su encargo.**
- **Antes de picar: lee cómo se hizo lo anterior.** Hay procesadores en producción que funcionan;
  el siguiente se les tiene que parecer. Si algo se aparta del patrón, dilo y explica por qué.
- **Las dudas de diseño no se resuelven en caliente.** Se anotan en una línea y se deciden en frío.
- **Cuando Fernando dice "esto no me cuadra", PARA y baja al dato.** Acierta ~95% de las veces
  (casos reales: `docs/reglas/como-se-trabaja.md`).
- **Darle la razón sin medir es fallarle.** Si tienes el dato y contradice lo que dice, enséñaselo.

---

## EL RESTO, EN `docs/reglas/` — SE ABRE CUANDO TOCA

Se **movió tal cual** (lo reescrito lleva fecha en su cabecera); «CLAUDE.md §3» sigue valiendo. Cotejo: [`COTEJO.md`](docs/reglas/COTEJO.md).

| § viejo | se abre cuando… | fichero |
|---|---|---|
| §1 | cruzas o escribes identidad | [`identidad.md`](docs/reglas/identidad.md) |
| §1 | tocas un informe del Seller | [`informes-amazon.md`](docs/reglas/informes-amazon.md) |
| §1 | calculas rentabilidad o IVA | [`rentabilidad-amazon.md`](docs/reglas/rentabilidad-amazon.md) |
| §1 | dudas de qué cajón es una tabla | [`tres-cajones.md`](docs/reglas/tres-cajones.md) |
| §2 | tocas o escribes un procesador | [`procesadores.md`](docs/reglas/procesadores.md) |
| §2 | encoding, lotes, stock, FNSKU | [`trampas-medidas.md`](docs/reglas/trampas-medidas.md) |
| §3 | escribes un test o ves un verde | [`tests-y-falsos-verdes.md`](docs/reglas/tests-y-falsos-verdes.md) |
| §3 | escribes una guarda o un ensayo | [`guardas-y-ensayos.md`](docs/reglas/guardas-y-ensayos.md) |
| §3 | haces un censo del catálogo | [`censos-y-catalogos.md`](docs/reglas/censos-y-catalogos.md) |
| §3 | dices «no cambia nada» | [`huellas-y-cambios-inertes.md`](docs/reglas/huellas-y-cambios-inertes.md) |
| §4 | creas o recreas un objeto | [`seguridad-permisos.md`](docs/reglas/seguridad-permisos.md) |
| §4 | tocas backup, restore o `monitor_*` | [`pendientes-backup-y-permisos.md`](docs/reglas/pendientes-backup-y-permisos.md) |
| §5 | abres o cierras un worktree | [`como-se-trabaja.md`](docs/reglas/como-se-trabaja.md) |
| §5 | fusionas, o una migración va a producción | [`escalera-de-migraciones.md`](docs/reglas/escalera-de-migraciones.md) |
| §5 | lanzas un workflow o un `.yml` | [`gotchas-del-entorno.md`](docs/reglas/gotchas-del-entorno.md) |
| §6 | preguntas por dónde va la v2 | [`donde-esta-el-proyecto.md`](docs/reglas/donde-esta-el-proyecto.md) |

---

*Para el estado exacto de cada pieza: míralo en el repo y en la BD. No lo pongas aquí — caduca en horas.*
