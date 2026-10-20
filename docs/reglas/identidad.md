# Identidad: el resto de la regla

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)
> Después del movimiento se han editado partes con fecha; lo fechado manda sobre el texto movido.


## 1. LAS REGLAS QUE NO SE REINTERPRETAN

- 🟢 **Desde el 19-oct-2026 (v2 #755, v1 #376)** el escaneo de facturas escribe el ASIN de la ficha SOLO cuando Keepa devuelve un único candidato para el código de barras (sin chase ni SKU); con varios o ninguno, lo deja en blanco y lo decide una persona. La regla «más de un candidato → nunca ganador automático» sigue en pie. Pendiente de encargo (frente 140 del cerebro): emparejar también por el código de barras de NUESTROS propios anuncios cuando casa con un único ASIN nuestro; con varios, a mano.
- **`moloka_ean_norm()` ya existe en producción** (esquema `public`, `IMMUTABLE`, sin
  `SECURITY DEFINER`): úsala, no la reescribas.
  **REGLA para lo que se construya: va a los DOS lados de todo cruce por EAN.** Hoy la usan varios cruces
  (vistas de la base, escáner y Trackeador desde el 7-oct-2026); el que se construya la lleva igual.
