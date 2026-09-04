# Demostrar que un cambio no cambia nada: las siete huellas

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)

- 🔴 **"Es idéntico en efecto" es una hipótesis. Para demostrar que un cambio en la CAÑERÍA no
  cambia nada: DOS RECORRIDOS COMPLETOS Y LAS MISMAS HUELLAS.** Estrenado el 9-ago-2026 con el
  `search_path` explícito de `aplicar-migracion.yml`. El método:
  1. `restaurar-staging.yml` → `ensayo` → `aplicar`, con la versión **vieja**, y tomar las huellas
     md5 del estado resultante.
  2. El mismo recorrido entero con la versión **nueva**.
  3. Comparar. Si salen idénticas, el cambio es inerte **medido sobre el resultado**, no
     argumentado — y entonces sí se puede llevar a la base de Elena.

  **Las siete huellas**, que juntas describen la forma de la base: columnas+tipos · definición de
  los índices · restricciones · firma de las funciones · políticas con su `qual` · SQL de las
  vistas · ACL. *Staging no tiene los mismos nombres que producción: tiene la misma FORMA.*
  🔒 **La huella se calcula desde UN solo sitio** (`sql/huella_acl.sql` para los ACL). Dos códigos
  que hoy coinciden es una coincidencia, no una garantía: el día que alguien retoque uno, la
  comparación empieza a mentir sin que nadie lo note. Es el hermano del `LC_ALL=C`.
  ⚠️ Y sirve para lo contrario también: si las huellas que **deben** cambiar cambian y las que
  **no** deben, no, eso demuestra que la migración hace lo que dice **y nada más**.


---
