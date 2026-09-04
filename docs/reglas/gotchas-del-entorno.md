# Gotchas del entorno

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)

### Gotchas del entorno
- **La máquina de Fernando es Windows y su terminal es PowerShell**, pero las herramientas ejecutan
  **Bash**. `&&` no funciona en su terminal; las here-strings de PowerShell (`@'...'@`) corrompen
  los mensajes de commit si las usas en Bash. Comandos de una línea, sintaxis Bash.
- **`workflow_dispatch` exige que el `.yml` esté en la rama por defecto.** Orden forzoso:
  fichero → merge → ensayo.
- 🔴 **EL ID DE UN RUN SE TOMA DE LA URL QUE IMPRIME EL DISPATCH, JAMÁS DE
  `gh run list --limit 1`.** El run recién creado tarda unos segundos en registrarse, así que
  "el último de la lista" puede ser **el ANTERIOR** — y como ése suele estar en `success`,
  `gh run watch` vuelve al instante y da por bueno un trabajo que **todavía no ha empezado**.
  Es un verde prestado, hermano de los dos de §3.
  *Medido el 11-ago-2026: di por aplicado un andamio de staging leyendo el run de 25 minutos
  antes. Se cazó porque la comprobación por SQL no cuadraba con lo que decía el log.*
  `gh workflow run` (v2.96.0, la de esta máquina) **sí imprime la URL del run creado**, y de
  ahí sale el id:
  ```bash
  URL=$(gh workflow run X.yml -f entorno=staging 2>&1 | head -1); ID=${URL##*/}
  ```
  Si algún día no la imprimiera, la salida es acotar por `--branch` o `--created`, **nunca**
  "el último". Y la regla de fondo es la de siempre: la verificación es SQL contra la base, no
  el log — y menos aún el log de otro run.
- **En un `.yml`, un `no` suelto es el BOOLEANO `false`, no la cadena "no"** (el "problema de
  Noruega": `NO` = Norway). *Medido el 11-ago-2026 sobre
  `procesar-custom-analytics.yml`: `options: [no, si]` de un input se lee `[False, 'si']`.*
  Las opciones y los defaults de texto van **entrecomillados**. Vale para `on`, `off`, `yes`,
  `y`, `n` y las variantes en mayúsculas.
- **Los commits de este repo se firman con la dirección noreply de GitHub.** El repo es PÚBLICO:
  no publiques correos reales en la historia. La identidad está en `git config --local`, nunca
  `--global`.
- `raw.githubusercontent.com` tiene retraso de caché tras un commit. Para leer el repo desde fuera:
  **tarball por `codeload.github.com`**. La API de GitHub sin token da 60 peticiones/hora por IP.

---
