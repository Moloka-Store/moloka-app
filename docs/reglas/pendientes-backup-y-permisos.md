# Los frentes abiertos: backup, permisos y `monitor_*`

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)

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
  🔬 **YA NO ES HIPOTÉTICO: medido el 10-ago en staging, recién restaurado.** `v_velocidad_ventas` y
  `v_producto_amazon` tenían ahí `anon=arwdDxtm`, y en producción las dos tienen `authenticated=r`
  sin `anon`. La restauración las devolvió abiertas, exactamente como dice el párrafo de arriba.
  🔒 **Y de ahí sale una REGLA para cualquier migración que se ensaye:** *un test de ACL en staging
  NO prueba nada sobre producción.* Staging viene del dump sin privilegios, así que sus ACL son los
  de Supabase por defecto, no los de prod. La ÚNICA excepción es el objeto que crea la propia
  migración que estás ensayando, porque lleva su `revoke` dentro y por eso sí nace bien allí.
  **Conclusión práctica: el ACL se verifica EN PRODUCCIÓN, después de aplicar** — `relacl` y
  `has_table_privilege('anon', …)`, no en el ensayo. Con `v_presencia_pais` se hizo así.
- ⚠️ **PENDIENTE — el simulacro comprueba que las SECUENCIAS existan, y eso no es lo que importa.**
  Una secuencia puede volver de la copia **existiendo y con el contador a 1 sobre una tabla llena**:
  la primera inserción del día del incendio choca con clave duplicada. Por nombre, eso sale **verde**.
  El contraste que vale es de **valores**: los `setval` que emite el dump contra
  `pg_sequences.last_value`. Medido el 9-ago-2026: las **23** secuencias de producción tienen el
  contador avanzado (0 sin estrenar), así que le aplica a las 23. `restaurar-staging.yml` ya
  imprime en cada ejecución cuántos `setval` trae el dump, para que el agujero se vea. Es otro
  diseño y merece su propio PR.
- ⚠️ **PENDIENTE — el simulacro no compara las RESTRICCIONES, y son las que deciden si un ensayo vale.**
  Lo que importa de un índice no es el índice: es la **garantía**. Si staging admite un duplicado que
  producción rechaza, un ensayo sale verde y la migración revienta al aplicarla de verdad — que es
  exactamente el agujero que el simulacro existe para cerrar. Y las garantías viven en
  `pg_constraint` (PK, UNIQUE, FK, CHECK), con nombre, y en el dump como `ADD CONSTRAINT`:
  comparación limpia. Ojo al detalle que hace inútil el atajo: **los índices que respaldan una PK o
  un UNIQUE NO aparecen en el dump como `CREATE INDEX`**, sino dentro de un `ALTER TABLE … ADD
  CONSTRAINT`, así que contar `CREATE INDEX` da de menos y se inventa un rojo falso. Los índices de
  puro rendimiento no cambian si un ensayo es válido. Ese PR se llama **restricciones**, no índices.
- ⚠️ **PENDIENTE — la copia de FICHEROS a R2 no tiene simulacro de restauración.** Desde el
  30-jul-2026 el backup diario (`backup-bd.yml` + `backup_storage.py`) copia a R2 los buckets
  `facturas-pdfs` e `informes` (las facturas de proveedor y el archivo histórico de Keepa). Pero
  `restaurar-staging.yml` solo ensaya el incendio de la **BD**: **esos ficheros no los recupera ni
  los abre nadie nunca.** Es el MISMO agujero que motivó todo esto (una copia en la que se confía y
  que nadie ha probado), en el otro activo. Falta un `restaurar-ficheros` que baje de R2 una muestra
  y compruebe que abre. Hasta que exista, la copia de ficheros está **hecha pero no verificada de
  extremo a extremo**. *(El backup sí tiene número de control externo contra `storage.objects`, así
  que una copia CORTA no pasa por buena — pero eso valida la subida, no la restauración.)*
- 🔴 **PENDIENTE — las tablas `monitor_*` del trackeador están abiertas a `anon`, y no solo para
  leer: para BORRAR.** Medido el 10-ago en producción, al cerrar el gate de las tres vistas (§6):

  | Tabla | Política | Rol | Qué permite |
  |---|---|---|---|
  | `monitor_reglas` | `anon_all_regla` `ALL using(true)` | **anon** | leer, MODIFICAR y **BORRAR** |
  | `monitor_snapshots` | `anon_all_snap` `ALL using(true)` | **anon** | leer, MODIFICAR y **BORRAR** |
  | `monitor_resultados` | `p_resultados_all` `ALL using(true)` | **PUBLIC** | leer, MODIFICAR y **BORRAR** |
  | `monitor_recomendaciones` | 2 políticas `anon` | **anon** | leer y ACTUALIZAR |
  | `monitor_analisis` · `monitor_doctrina` · `monitor_reponibilidad_manual` | — | — | ✅ RLS y 0 políticas: cerradas |

  `monitor_reglas` son **las 21 reglas del trackeador**: la doctrina de precios de la casa, expuesta a
  un `DELETE` anónimo. La clave publicable viaja en el JavaScript de la app por diseño, así que esto
  no es teórico.

  ✅ **EL PASO PREVIO QUE ESTO EXIGÍA YA ESTÁ DADO** (11-ago-2026, `ef6e72e`, PR #153 — *«El
  trackeador deja de escribir como anon»*). Aquí vivía un párrafo que decía que los dos workflows
  del trackeador *«inyectan ÚNICAMENTE `secrets.SUPABASE_KEY`»* y que por tanto no se podía cerrar
  nada hasta saber qué contenía ese secreto. **Era cierto cuando se escribió y dejó de serlo el
  11-ago**; la nota siguió en pie 17 días. Lo que hay hoy, medido en el repo:
  - `tracker-app.yml:45` y `tracker-cerebro.yml:53` **inyectan las DOS**, incluida
    `SUPABASE_SERVICE_KEY`.
  - Los scripts que esos workflows lanzan —`moloka_tracker_snapshot_nube.py` y
    `moloka_tracker_cerebro.py`— hacen
    `os.environ.get('SUPABASE_SERVICE_KEY') or os.environ['SUPABASE_KEY']`, así que el `or` cae del
    lado de la **de servicio**.
  - ⚠️ `moloka_tracker_snapshot.py` (sin `_nube`) sí usa **solo** `SUPABASE_KEY`, sin alternativa —
    pero **no lo lanza ningún workflow**: es la versión **CLI**, la que se corre a mano con
    `--fba/--keepa`, y en Actions entra solo como motor importado. No confundirla con el `_nube`,
    que es el que corre de verdad.

  🔒 **Lo que NO cambia, y es lo que hay que llevarse:** las políticas de la tabla de arriba **siguen
  ahí** — ninguna migración del repo las toca (comprobado el 28-ago). Que el trackeador ya no dependa
  de `anon` quita el motivo por el que esto estaba parado, **no cierra las políticas**.
  📌 **Y cerrarlas NO se decide aquí: está APARCADO hasta jubilar la v1**, junto con `productos` y
  `escaner_memoria`. Decisión cerrada de Fernando; este apartado la registra, no la reabre.

  ⚠️ El trackeador sigue **parado desde el 11-jul-2026** (última ejecución de los dos workflows).
  Cuando se retome, el día que se toque esto: primero se comprueba que arranca con la de servicio,
  y solo DESPUÉS se quitan las políticas de `anon`. En ese orden, nunca al revés.
  ⚠️ Y `productos` sigue con **455 filas legibles por `anon`** (§6 ya lo señalaba): mismo frente.
- 🔴 **PENDIENTE — NO EXISTE UNA LISTA FIABLE DE QUÉ MIGRACIONES SE HAN APLICADO A PRODUCCIÓN.**
  `supabase_migrations.schema_migrations` existe y tiene **37 registros, el último
  `20260806085625`** — o sea del **6-ago-2026**. Ni el contador ni el `setval` del 10-ago están
  ahí, ni nada de lo aplicado desde entonces. **Medido el 10-ago-2026.**
  Son **dos agujeros, uno encima del otro**:
  1. `aplicar-migracion.yml` aplica con **psql directo**, no por la CLI de Supabase, así que ese
     registro no se toca nunca. No es un fallo del workflow: es que nadie lo escribe.
  2. Y esa tabla vive en el esquema **`supabase_migrations`**, mientras el volcado es
     `pg_dump --schema=public`. Así que **aunque estuviera al día, el backup no la copiaría.**

  🔴 **Lo que esto significa el día del incendio:** *"restaurar y reaplicar lo posterior al
  backup"* NO se puede resolver mirando la base. Hay que reconstruirlo del historial de runs de
  GitHub o de memoria — y la memoria es justo lo que no funciona a las tres de la mañana. Es el
  mismo patrón que las tres viñetas de arriba: **el estado en un sitio que el backup no cubre.**

  🔑 **El arreglo es barato porque la pieza ya existe:** el paso 8 de `aplicar-migracion.yml` YA
  calcula el `sha256` del fichero. Basta con que escriba una fila en una tabla **de `public`** —
  fichero, sha256, entorno, quién lo despachó, cuándo, y si fue `ensayo` o `aplicar`— y el
  registro pasa a **sobrevivir al restore**. Con eso, restaurar deja de ser *"acordarse"* y pasa a
  ser *"mira qué falta desde la fecha del dump"*. Va **detrás** del PR del modelo y del
  `--no-privileges`; se anota aquí para que no dependa de que alguien lo recuerde.

---
