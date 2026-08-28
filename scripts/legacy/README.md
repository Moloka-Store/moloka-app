# scripts/legacy — archivo muerto. Nada de aquí se ejecuta.

**Qué hacía.** `Moloka_ActualizarApp.ipynb` era el cuaderno de Colab que leía los informes del Seller desde `MyDrive/Moloka/inputs/` y **sellaba en la tabla `app_datos`** las claves `rentabilidad`, `velocidades` y `rentabilidad_miravia` (y de camino escribía el stock FBA, la tabla `devoluciones`, la Buy Box de Keepa y los canales IT/FR/Miravia en `canales_producto`).

**Qué lo sustituye.** Primero `moloka_actualizar_nube.py` + `.github/workflows/actualizar-app.yml`, que es este mismo cuaderno llevado a GitHub Actions (buzón de Storage en vez de Drive, Secrets en vez de Colab) — su cabecera lo dice: *"Generado a partir de Moloka_ActualizarApp.ipynb"*, y el cuaderno no se toca desde el 12-jun-2026, el día en que se subió esa versión. Y hoy, de verdad, lo sustituye la Fase 0: `procesador_transacciones.py` carga el extracto de euros en `transacciones_movimientos` y de ahí salen `v_velocidad_ventas` y `mv_rentabilidad_sku` — cifras vivas en tablas, no un JSON sellado.

**Por qué está parado.** Las tres claves de `app_datos` no se reescriben desde el **22-jul-2026 18:06 UTC** (medido en producción el 28-ago-2026), que es la hora en que terminó la **última** ejecución de `actualizar-app.yml` (arrancó a las 17:06 UTC). Ese workflow no tiene reloj: solo corre si alguien lo lanza, y nadie lo ha lanzado desde entonces. Se archiva aquí, y no se borra sin más, porque es el original del que se generó `moloka_actualizar_nube.py` y hasta hoy no vivía en ningún repo: estaba solo en el Drive de Fernando.

**Qué se le quitó, y por qué en DOS pasos.** El fichero de este repo no es byte a byte el del Drive: se le han hecho dos supresiones, en dos días distintos, porque respondían a dos preguntas distintas.

1. **La línea de Keepa** (28-ago-2026, al archivar). En las salidas de las celdas 17 y 24 —y solo ahí— la línea que la librería de Keepa imprime al arrancar (`INFO:keepa.keepa_sync:Using key ending in …`) traía los **seis últimos caracteres de la `KEEPA_API_KEY`**. Sustituidos por `[SUPRIMIDO AL ARCHIVAR: ver README.md]`; aquí tampoco se escriben, que sería quitarlos de un sitio para ponerlos en el de al lado. *(Decidido aparte: la `KEEPA_API_KEY` **no** se rota — seis caracteres del final no son una llave, y esa llave alimenta el escáner, que escribe en producción sin pasar por staging.)*
2. **El `executionInfo` de Colab** (28-ago-2026, ya con el cuaderno dentro). Colab guarda en `metadata.executionInfo` de **cada celda ejecutada** quién le dio al play: `displayName` y `userId` de Google, más `elapsed`, `status`, `timestamp` y `user_tz`. Eran **13 celdas** con el nombre y el identificador de una persona, y este repo es público. Se quita el objeto **entero**, no solo el `user`: lo demás tampoco aporta nada y así no hace falta un segundo viaje.

🔑 **Por qué no salió todo a la vez, que es lo que enseña este README:** el primer barrido buscaba **credenciales** —llaves, tokens, JWT— y esa pregunta se contesta mirando `source` y `outputs`. La identidad de quien ejecutaba **no vive en ninguno de los dos**: vive en la metadata de cada celda, y solo aparece si haces el censo de **todas** las claves JSON del fichero. Dos preguntas distintas, dos pasadas. Un barrido que solo mira donde ya sabes que hay cosas sale limpio siempre.

**Los tres estados, con sus md5.** Cada paso es comprobable por separado:

| Estado | Bytes | md5 |
|---|---|---|
| **original** (el del Drive, tal cual lo dejó Colab) | 169.886 | `f1da85a8abcf3f3e83bb15708cebebe4` |
| **archivado** (original − la línea de Keepa) | 169.950 | `6b659b512f6918f52f0a212bb9ad6cbd` |
| **limpio** (archivado − los 13 `executionInfo`) ← el de este repo | 167.738 | `f7b55851758aac70d5c1e0440c15efc3` |

El archivado pesa **64 bytes MÁS** que el original (32 por cada una de las dos sustituciones: el corchete es más largo que lo que tapa) y el limpio **2.212 MENOS** que el archivado. Los dos pasos son reversibles sobre el papel y así se comprobaron: **deshacer la sustitución** devuelve el md5 del original **exacto**, y **reinsertar los 13 bloques** donde estaban devuelve el md5 del archivado **exacto**. Esa ida y vuelta es la prueba de que no se cambió nada más — y el contraste celda a celda lo confirma por otra vía: **las 25 celdas de `source` idénticas**, los `outputs` idénticos salvo los dos de Keepa, y ninguna metadata distinta por algo que no sea el `executionInfo` quitado.

Un archivo editado y anotado sigue siendo un archivo; lo que no vale es editarlo en silencio.

⚠️ **Y lo que esto NO hace: no lo borra de la historia pública.** El cuaderno con los 13 `executionInfo` se fusionó a `main` en el commit `83aee98`, y ese blob sigue alcanzable en GitHub aunque aquí ya no esté; lo mismo que el commit `2a8b4d3`, huérfano desde un force-push, que seguía devolviendo 200 sin sesión. **Quitar algo hacia delante no es quitarlo.** Reescribir `main` para eso no se hace por iniciativa propia: lo decide Fernando.
