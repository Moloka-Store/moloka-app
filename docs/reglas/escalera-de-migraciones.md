# Antes de ensayar una migración, se restaura staging

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
