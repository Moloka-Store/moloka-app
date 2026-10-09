# La cadena de una migración (sin staging desde el 30-sep-2026)

> **Reescrito el 30-sep-2026 (encargo A):** Fernando jubila la base de pruebas (staging,
> proyecto `lusujlzyndsydibkeija`). Lo que había aquí antes —restaurar staging y ensayar
> encima— queda más abajo, **literal**, como historia fechada: vale hasta el 30-sep-2026.

Toda escritura en la base sigue esta cadena, y no hay otra:

**rama → PR → auditoría de Cowork (lee el diff entero) → fusión por Code → CI → producción con
Fernando delante, primero en modo ensayo → verificación SQL en producción después.**

- **CI.** En la v1 corre `.github/workflows/ci-tests-python.yml` (job `tests`) y **no levanta
  ninguna base**. En la v2, el job `trigger-postgres` prueba, en un Postgres propio que nace y muere en el run, lo ligado a lo que cambia el PR (o la batería
  entera si toca algo compartido); la entera corre además cada noche (detalle en `docs/reglas/revision-de-pr-y-merge.md` de la v2).
- **Producción, en modo ensayo primero.** Una migración de la v1 llega a la base por
  `.github/workflows/aplicar-migracion.yml` (o por el conector de escritura, con Fernando delante):
  primero `modo=ensayo` —corre de verdad contra la base y se **deshace** con rollback— y, si sale
  bien, `aplicar`. Desde el 30-sep-2026 ese workflow y los `procesar-*.yml` van a producción por
  defecto y en modo ensayo por defecto: la opción staging ya no existe.
- **Verificación después**, en producción y por SQL: objetos, permisos y filas. Nunca el log.
- **¿Y la copia de seguridad?** Se prueba restaurándola en una base desechable que nace y muere
  dentro de la ejecución de `simulacro-copia.yml` (antes se llamaba `restaurar-staging.yml`; el paso a
  paso, en su cabecera). No hay ninguna base compartida sobre la que ensayar.

## Se fusiona a cualquier hora, y el parte dice si puede perderse un envío a medias

> Decidido por Fernando el 30-sep-2026 (encargo A).

Se fusiona **a cualquier hora, también con Elena trabajando**. A cambio, **todo parte de Code lleva
una línea «¿Puede perderse un envío a medias?: sí/no, y por qué»**. Es **«sí»** si el cambio toca la
pantalla de Envíos, el envío que Elena está montando o las funciones que confirman cajas y
descuentan stock. **Con «sí», Cowork avisa a Fernando antes de fusionar.** Aplicar una migración en
producción sigue siendo con Fernando delante.

Sustituye, en `CLAUDE.md`, a esta línea (vale hasta el 30-sep-2026):

- **Cualquier cambio que roce la operativa de Elena se avisa ANTES de desplegar.**

---

## HISTORIA — vale hasta el 30-sep-2026 (había staging)

### Antes de ensayar una migración, se restaura staging

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)

- 🔴 **ANTES DE ENSAYAR UNA MIGRACIÓN EN STAGING, SE RESTAURA STAGING.** Se lanza
  `restaurar-staging.yml` y se espera a que salga en VERDE. La escalera entera es:
  **restaurar staging → staging ensayo → staging aplicar → verificación SQL → producción ensayo →
  producción aplicar → verificación SQL**, con Elena avisada antes de tocar producción.
  **Por qué:** un ensayo en staging solo demuestra algo sobre producción si las dos bases se parecen.
  El 9-ago-2026 staging tenía 54 objetos contra los 83 de producción — faltaban 29, entre ellos
  `v_salud_asin` y `v_trackeador_cola` — y con eso los ensayos de semanas enteras no demostraban
  nada. El caso concreto: el ensayo de `2026-08-07_demanda_asin_contador.sql` murió con
  `ERROR: relation "v_salud_asin" does not exist`, que no era un problema de la migración sino de la
  base contra la que se probaba.
  **Y por qué así y no con un vigilante de deriva:** porque la deriva no se mide, se **elimina**. Una
  alarma diaria cuya única acción posible es siempre la misma —restaurar staging— se deja de leer en
  dos semanas. Es el `ON_ERROR_STOP=0` por el otro extremo. Restaurando antes de cada ensayo, staging
  nunca es más viejo que el backup de anoche y no queda deriva que vigilar.
  ⚠️ **LA ÚNICA EXCEPCIÓN, y viene con su fecha para que no se haga costumbre: el día en que el
  volcado va POR DETRÁS de lo que se acaba de crear.** El 23-ago-2026, con la migración
  `2026-08-23_jubilar_salud_fba.sql`, restaurar staging lo habría dejado **PEOR**: el backup de
  anoche es anterior a `inventario_fba`, así que la tabla no existiría allí y la primera guarda de
  la migración habría abortado por una causa que no tiene nada que ver con la migración.
  🔑 **No se desactiva la regla: se esquiva el único día en que el volcado va por detrás de la
  base.** La regla existe para que staging se PAREZCA a producción, y ese día se parecía —medido
  desde las dos bases antes de decidir: `inventario_fba` 354 filas y foto del 23-ago,
  `inventario_fba_historico` 354 y 1 fecha, `salud_fba` con `relkind='v'`, `salud_fba_amazon` 219,
  `salud_fba_historico` 1.984 filas y 9 fechas, `v_ventas_ventanas` viva, y los 8 buzones—; era
  restaurar lo que la habría alejado.
  ⏳ **Y la ventana es de UN día**: el backup de esa noche ya incluye `inventario_fba`, así que a
  partir del 24-ago el restaurado vuelve a hacer lo que promete y la regla se aplica entera.
  📌 La forma de saber si vuelve a tocar: **mirar el estado del destino antes de decidir**, no la
  fecha. Si lo que la migración necesita nació DESPUÉS del último volcado, restaurar borra el
  suelo sobre el que se iba a ensayar; en cualquier otro caso, se restaura.

### La cadena de una migración, y por qué staging no es testigo (29-sep-2026)

> **Añadido, no movido.** Sustituye en `CLAUDE.md` al tramo «Toda escritura va por rama → PR →
> auditoría de Cowork → fusión por Code → ensayo en staging → producción», que allí queda como
> remisión a este apartado. Aprobado por Fernando el 29-sep-2026.
> ⚠️ El título de este fichero y lo de arriba (restaurar staging antes de ensayar) son anteriores,
> chocan con este apartado y no se han tocado en este cambio.

Toda escritura va por rama → PR → auditoría de Cowork → fusión por Code → la migración **no se ensaya
en ningún Postgres del CI** → se aplica en producción con Fernando delante → los permisos se miden en producción después de aplicar (Seguridad 1-2 del cerebro). La base de pruebas (staging) no es testigo mientras no se rehaga: el 29-sep le faltaban 30 de las 59 migraciones desde el 19-sep y tenía registradas migraciones cuyos objetos no existen.

- **Por qué no dice «se ensaya en el Postgres del CI»** (medido el 29-sep-2026): el único CI que corre
  en un PR de la v1 es `.github/workflows/ci-tests-python.yml` (job `tests`), y no levanta ninguna
  base. Las migraciones de la v1 viven en `migraciones/` (no hay `supabase/migrations/`) y solo llegan
  a una base por `.github/workflows/aplicar-migracion.yml`, lanzado a mano (`workflow_dispatch`,
  staging o producción, `ensayo` con rollback o `aplicar`).

- Funciones que hoy incumplen algún candado (auditoría del 29-sep-2026): se arreglan una por PR cuando toque; lista en el parte 2026-09-29-1844 §C.
