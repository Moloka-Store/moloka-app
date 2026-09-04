# Los tres cajones: todo menos la tabla

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)

> 🔑 **La TABLA de los tres cajones no vive aquí: vive en el**
> **[`CLAUDE.md`](../../CLAUDE.md) corto**, que es donde tiene que verse
> siempre. Aquí queda todo lo demás de §1.6.

### 1.6 Los TRES CAJONES: cada tabla se escribe de UNA manera
Antes de escribir en una tabla, mira **en qué cajón está**. El cajón decide qué pasa con lo que ya
había, y los cajones no se mezclan:


⚠️ **`custom analytics` estaba en la fila FOTO y ahí no va.** Cambió de cajón el **10-ago-2026**, y
lo dice su propio procesador en la cabecera (*«EL CAJÓN: PELÍCULA DE LECTURAS»*): cada carga **apila
una lectura** del contador, no sustituye la anterior. El cuadro se quedó con el cajón de antes.
⚰️ Y `salud_fba` sale de la fila FOTO porque su informe se jubiló el 23-ago (§1.3); lo relevó
`inventario_fba`, que sí es Foto.

- Una **FOTO** contesta *"¿cómo está esto AHORA?"*. Una fila que sobrevive a su fichero es un
  fantasma que descuadra el cruce. La memoria histórica **no vive aquí**: vive en la Película.
- Una **PELÍCULA** es un libro de asientos: append, jamás update destructivo. Borrar una línea del
  ledger es falsificar el extracto.
- Un **MAESTRO** es la identidad. Un producto que deja de venderse no se borra: se **marca**
  (`activo=false`). Borrarlo deja huérfanos los movimientos que lo citan.

🔴 **El error caro es tratar un cajón como si fuera otro.** Un upsert-sin-DELETE convierte una Foto
en un collage de dos días (fue el caso real de salud_fba, §2); un DELETE en una Película destruye
el histórico y no hay de dónde recuperarlo.

---
