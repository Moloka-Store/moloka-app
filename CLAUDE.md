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

## LO QUE NO SE REINTERPRETA

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

### El estado vive en el repo, no en las notas
- Antes de afirmar el estado de cualquier pieza: **míralo**. Las notas de ayer mienten hoy.

---

## SEGURIDAD

- 🔴 **Las credenciales NUNCA van en el código ni en un mensaje.** Viven en GitHub Secrets, Vercel
  y R2. Una llave que aparece en un chat está quemada y se regenera.
  **Introducir credenciales no es algo que hagas tú: se lo pides a Fernando.**
- **Supabase es PRODUCCIÓN.** Desde una sesión: **solo lectura**. Toda escritura va por
  rama → PR → Fernando aprueba → ensayo en staging → producción.
- **Todo lo NUEVO nace CERRADO:** RLS activo y 0 políticas. Vistas `security_invoker`. Funciones
  `IMMUTABLE`, sin `SECURITY DEFINER`.
- **La v1 tiene escritura anónima abierta** (deuda estructural). **No se toca a mitad de vuelo**:
  se cierra en la v2 con Auth + RPC. El problema no es la llave `publishable` (es pública por
  diseño): son las políticas.
- **Confirmar una factura SIEMPRE inyecta stock.** Nunca subir facturas antiguas retroactivamente.

---

## CÓMO SE TRABAJA AQUÍ

- **UN PR, UNA COSA.** Sin excepciones.
- 🔴 **AL TERMINAR UN TRABAJO, EL PARTE SE DEJA EN LA BANDEJA.** Además del PR, se escribe
  una copia del informe en `G:\Mi unidad\Moloka\bandeja\` con el nombre
  **`AAAA-MM-DD-HHMM-tema.md`** (hora española). **Primera línea del fichero: quién lo lee y
  cuándo.** Sin esa copia, el trabajo solo existe dentro del repo y Fernando tiene que hacer de
  correveidile entre Code y los chats. La bandeja es lo que lo evita, y **no depende de que
  nadie se acuerde de pedirlo en el encargo**.
- **Una regla nueva no se escribe aquí ni en `docs/reglas/`: va al parte, y entra por el consolidador con su encargo.**
- **Antes de picar: lee cómo se hizo lo anterior.** Hay procesadores en producción que funcionan;
  el siguiente se les tiene que parecer. Si algo se aparta del patrón, dilo y explica por qué.
- **Las dudas de diseño no se resuelven en caliente.** Se anotan en una línea y se deciden en frío.
- **Cuando Fernando dice "esto no me cuadra", PARA y baja al dato.** Acierta ~95% de las veces.
  Casos reales: un bug oficial de la API de Amazon (FBA_CORE), un envío perdido de 24 uds, un ASIN
  borrado con 12 uds dentro. En los cuatro, la explicación cómoda era la equivocada.
- **Darle la razón sin medir es fallarle.** Si tienes el dato y contradice lo que dice, enséñaselo.

---

## DÓNDE ESTÁ EL PROYECTO

Orden de mudanza acordado: Inventario → Inicio → Alertas → Movimientos → Rotación+Rentabilidad →
*(frontera lectura/escritura)* → Entrada → Facturas → Envío FBA → Motores.

---

## EL RESTO, EN `docs/reglas/` — SE ABRE CUANDO TOCA

Nada se ha perdido ni reescrito: se ha **movido tal cual**, con los títulos numerados
dentro, así que una referencia vieja como «CLAUDE.md §3» sigue valiendo.
Cotejo, línea a línea, en [`COTEJO.md`](docs/reglas/COTEJO.md).

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
| §5 | vas a ensayar una migración | [`escalera-de-migraciones.md`](docs/reglas/escalera-de-migraciones.md) |
| §5 | lanzas un workflow o un `.yml` | [`gotchas-del-entorno.md`](docs/reglas/gotchas-del-entorno.md) |
| §6 | preguntas por dónde va la v2 | [`donde-esta-el-proyecto.md`](docs/reglas/donde-esta-el-proyecto.md) |

---

*Para el estado exacto de cada pieza: míralo en el repo y en la BD. No lo pongas aquí — caduca en horas.*
