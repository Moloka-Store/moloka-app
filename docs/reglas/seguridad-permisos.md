# Permisos: «nace cerrado» no es el estado por defecto

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)

## 4. SEGURIDAD

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
- **SP-API: jamás con credenciales de Moloka SL.** Decidido y cerrado. Las cuentas de Moloka
  (Elena) y Fernando (autónomo) están separadas a nivel de credenciales.

## `SECURITY DEFINER`: con motivo y con candados (29-sep-2026)

> **Añadido, no movido.** Sustituye en `CLAUDE.md` a «**Todo lo NUEVO nace CERRADO:** RLS activo y 0
> políticas. Vistas `security_invoker`. Funciones `IMMUTABLE`, sin `SECURITY DEFINER`.» Es la
> «Opción 1 — v1» del parte `2026-09-29-1844-auditoria-definer-y-staging.md` §C, aprobada por
> Fernando el 29-sep-2026. Texto literal (el «Detalle» de la v2 vive hoy en
> `docs/reglas/permisos-nace-cerrado.md` de `moloka-app-v2`):

- **Todo lo NUEVO nace CERRADO:** RLS activo y 0 políticas. Vistas `security_invoker`. Funciones
  `SECURITY INVOKER`; `SECURITY DEFINER` solo como puerta de escritura, lectura estrecha de una tabla
  cerrada o función de una política, con `search_path = ''`, EXECUTE solo a quien la llama, nunca a
  `anon`, y —si escribe— excluyendo al warmer y fallando cerrado. Detalle: `CLAUDE.md` de `moloka-app-v2`.
