# Dónde está el proyecto ahora

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)


## 6. DÓNDE ESTÁ EL PROYECTO AHORA

La v2 ("el bicho") se construye con **patrón estrangulador**: nace al lado de la v1, sobre la misma
Supabase, y Elena se muda pestaña a pestaña. **Los datos no se mudan: se curan.** Una BD nueva serían
dos verdades y un descuadre garantizado.

**Fase 0 (la capa de datos) va PRIMERO** y está a medias. ⚠️ Aquí ponía que *«de la app v2 en sí
(repo, pantallas, Auth) no hay nada todavía»*: eso era cierto al arrancar el proyecto y **hoy no lo
es**. La app existe en el repo `moloka-app-v2`, se despliega en Vercel, tiene Auth por
`@supabase/ssr`, y su Inventario está en marcha — hasta el punto de que un workflow lo comprueba cada
mañana laborable «antes de que entre Elena». Lo que sigue siendo verdad es el orden: la capa de datos
va primero.
