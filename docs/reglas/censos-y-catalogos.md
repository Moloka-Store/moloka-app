# Censos y catálogo de Postgres

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)

- 🔴 **LAS OPCIONES DE UN OBJETO SE LEEN POR OPCIÓN, NUNCA CON UN `like` SOBRE SU TEXTO.**
  Postgres guarda en `reloptions` **literalmente lo que se escribió**, y acepta sinónimos:
  `security_invoker=true` y `security_invoker=on` significan lo mismo y se almacenan
  distinto. Un `... not like '%security_invoker=true%'` cuenta las de `on` como definer.
  *Medido el 12-ago-2026: el censo de vistas definer decía **18**. Son **13**. Las cuatro
  de más eran `v_escaparate`, `v_factura_cuadre`, `v_factura_escaneo` y `v_salud_asin`, que
  sí son invoker — con `on`. Reparto real de las 30: 13 sin poner · 13 `true` · 4 `on`.*
  🔑 **Y lo que lo convierte en regla y no en anécdota: Fernando y yo escribimos el mismo
  `like '…=true%'` por separado, sin vernos, y los dos contamos 18.** Cuando dos personas
  caen igual en el mismo sitio, no es un despiste: es que la forma obvia está mal. Se lee
  así, y devuelve lo mismo se escriba como se escriba:
  ```sql
  exists (select 1 from unnest(coalesce(c.reloptions,'{}')) o
           where lower(split_part(o,'=',1)) = 'security_invoker'
             and lower(split_part(o,'=',2)) in ('true','on','yes','1'))
  ```
  ⚠️ Vale para **cualquier** `reloptions` (`fillfactor`, `autovacuum_*`, `check_option`…),
  no solo para ésta, y para todo catálogo que guarde texto libre. El fallo no da error: da
  un recuento plausible, que es el peor.
- 🔴 **EL CENSO POR CÓDIGO NO BASTA: HAY QUE CRUZARLO CON EL CENSO POR USO.** El grep dice
  qué está **escrito**; `pg_stat_statements` dice qué se **ejecuta**. No responden a la
  misma pregunta y ninguno de los dos sustituye al otro.
  *Medido el 11-ago-2026: el censo de qué lee la v1 se hizo con un grep de `.from('…')`
  sobre `index.html` y dio 17 tablas. Parseando el FROM de las 511 consultas que el rol
  `anon` ha ejecutado de verdad salen **19**, y **seis no estaban** — entre ellas
  `escaner_memoria`, con **5.767 llamadas**. Un grep de literales no ve lo que no está
  escrito como literal, y sobre todo no ve a los consumidores que están FUERA del fichero
  que estás mirando.*
  🔑 Las dos consultas que lo hacen, y conviene tenerlas a mano:
    · **quién ejecuta** — `pg_stat_statements` cruzado con `pg_roles` por `userid`: dice
      CON QUÉ ROL, que es lo que suele decidir (un `revoke` a `anon` no toca lo que hizo
      `authenticated`).
    · **cuánto histórico** — mucho mayor que los logs de la API: 🔬 105 días contra una
      hora, y además cubre conector, `psql` y cron, no sólo PostgREST.
  ⚠️ Y al revés también: que algo se ejecute **no** significa que esté en el repo. Ahí es
  donde aparecen los consumidores no versionados, que es justo lo que un censo de
  jubilación tiene que encontrar.
