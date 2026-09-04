# Cómo se trabaja aquí: worktrees e hipótesis

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)

## 5. CÓMO SE TRABAJA AQUÍ

- 🔴 **AL FUSIONAR UN PR, QUIEN CREÓ EL WORKTREE LO RETIRA CON `git worktree remove`.**
  Un worktree que sobrevive a su PR es un clon fantasma más donde alguien leerá el código
  equivocado. Nunca se borra la carpeta a mano —eso deja el registro de `git worktree list`
  mintiendo—: `git worktree remove <ruta>` y, al terminar la tanda, `git worktree prune`.
- **Distingue "podría" de "está documentado".** Una hipótesis bien redactada no es un hecho.
  Si no lo has verificado ahora mismo, dilo.
- **Antes de decir "no se puede":** eso es una hipótesis. Agota la búsqueda (documentación oficial,
  la propia herramienta, la web). *"No conozco una manera"* ≠ *"no existe una manera"*.
