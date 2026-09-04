# Identidad: el resto de la regla

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)


## 1. LAS REGLAS QUE NO SE REINTERPRETAN

- **`moloka_ean_norm()` ya existe en producción** (esquema `public`, `IMMUTABLE`, sin
  `SECURITY DEFINER`): úsala, no la reescribas.
  **REGLA para lo que se construya: va a los DOS lados de todo cruce por EAN.** No es una
  descripción de hoy — hoy solo hay UN cruce que la usa (la vista de `procesador_keepa_escaparate.py`).
  Es la regla para el siguiente.
