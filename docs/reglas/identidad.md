# Identidad: el resto de la regla

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)
> Después del movimiento se han editado partes con fecha; lo fechado manda sobre el texto movido.


## 1. LAS REGLAS QUE NO SE REINTERPRETAN

- **`moloka_ean_norm()` ya existe en producción** (esquema `public`, `IMMUTABLE`, sin
  `SECURITY DEFINER`): úsala, no la reescribas.
  **REGLA para lo que se construya: va a los DOS lados de todo cruce por EAN.** Hoy la usan varios cruces
  (vistas de la base, escáner y Trackeador desde el 7-oct-2026); el que se construya la lleva igual.
