# Guardas que miden algo, y ensayos que prueban algo

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)

- 🔴 **UNA GUARDA COMPARA INVARIANTES, NO CIFRAS ABSOLUTAS** — y con más motivo si mide algo que
  el backup no copia. `backup-bd.yml` vuelca con `--schema=public`, así que `storage`, `auth` y
  todo lo demás **no están en la copia** y `restaurar-staging.yml` no los repone. Cualquier número
  fijo sobre lo que no se copia da **rojo en staging por el alcance del backup, no por la
  migración**: un falso rojo esperando su día.
  *Medido el 10-ago-2026 en `2026-08-10_buzon_custom_analytics.sql`: el encargo pedía comprobar
  `n_politicas <> 4` sobre `storage.objects`. Se cambió a guardar el recuento ANTES y compararlo
  DESPUÉS, porque el invariante real de un `CREATE OR REPLACE` es "no se llevó ninguna política
  por delante", y eso es cierto valgan 4 o valga otra cosa.*
  🔑 **La regla de la que esto es un caso: una comprobación que puede saltar por una causa
  distinta de la que dice medir no es una guarda, es ruido futuro.** Se deja de mirar en dos
  semanas — es el `ON_ERROR_STOP=0` por el otro extremo. El 10-ago-2026 el mismo patrón apareció
  **tres veces por caminos que no se parecen en nada**: los tipos (`Decimal` contra `float`, §2),
  un `LIKE` más ancho de lo que decía medir, y este número fijo de políticas. Antes de dar una
  guarda por buena, pregúntale: *¿puedes ponerte roja por el entorno, por el tipo de dato o por
  el alcance de una copia?* Si la respuesta es sí, todavía no es una guarda.
- 🔴 **UN ENSAYO SOBRE UN ESTADO QUE YA ES EL DE DESTINO NO PRUEBA NADA.** Sale verde,
  parece una verificación y no lo es: solo dice que el destino ya estaba como se quería.
  *Caso real del 10-ago-2026, y es mío: la migración de los comentarios de `demanda_asin` se
  probó primero "en humo" escribiéndola a mano en staging para ver si el SQL parseaba. Luego
  iba a correr el `aplicar` encima — sobre unos comentarios que ya eran los nuevos. Habría
  dado verde verificando algo que ya era cierto antes de empezar. Se salvó devolviendo
  staging al texto viejo ANTES del ensayo, y entonces sí midió algo.*
  **Antes de fiarte de un ensayo, mira en qué estado está el destino.** Aplica a todo lo
  idempotente: `CREATE OR REPLACE`, `IF NOT EXISTS`, `COMMENT ON`, un `setval` que ya estaba
  bien, un upsert que no cambia una fila. Y es hermano del simulacro de restauración: una
  copia en la que se confía y que nadie ha probado **contra un estado distinto** no está
  probada.
  📌 **PENDIENTE — convertirlo en guarda, que es mejor que en regla.** `aplicar-migracion.yml`
  puede detectarlo solo: si en modo `ensayo` la migración no cambia NADA —cero filas
  afectadas, cero objetos tocados— que lo GRITE (*"este ensayo no ha cambiado nada; o la
  migración es un no-op o el destino ya estaba en el estado final, y en los dos casos esto
  NO prueba que funcione"*). **Sin abortar**: hay migraciones legítimamente idempotentes que
  se relanzan a propósito. Pero que un verde mudo no pueda hacerse pasar por una
  verificación. Va **detrás** del registro de migraciones de §4.
