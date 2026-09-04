# Los informes de Amazon jamás se suman entre sí

> Movido **literalmente** desde `CLAUDE.md` al acortarlo. Ni una palabra
> cambiada, ni una regla nueva. Índice y cotejo línea a línea:
> [`docs/reglas/COTEJO.md`](COTEJO.md) · vuelta: [`CLAUDE.md`](../../CLAUDE.md)


### 1.3 Los informes de Amazon JAMÁS se suman entre sí
Cada uno responde **una** pregunta y son universos distintos:

| Informe | Es | Responde |
|---|---|---|
| **INTERNACIONAL** | El INVENTARIO por país (replica la pantalla del Seller) | ¿Cuánto tengo y dónde? |
| **INVENTARIO_FBA** | El informe de gestión de inventario FBA. Nació por **lo que viene DE CAMINO**, que es lo que nadie más contesta. Relevó a SALUD_FBA el 23-ago | ¿Cuánto hay en tránsito? |
| **PANEU_APTOS** | La dimensión Pan-EU. Es película: cambia en horas | ¿Qué me deja Amazon? |
| **LEDGER** | El EXTRACTO de UNIDADES. Libro append, no foto | ¿De dónde salió y a dónde fue? |
| **TRANSACCIONES** | El EXTRACTO de EUROS. Uno por marketplace (ES/IT/FR/DE) | ¿Cuánto he cobrado y qué me han cobrado? |
| **CUSTOM_ANALYTICS** | La DEMANDA por ASIN (visitas, sesiones, conversión). **Contador acumulado**: cada carga apila UNA LECTURA (**Película de lecturas**, §1.6) | ¿Cuánta gente lo mira? |
| **ALL_LISTINGS** | La identidad (ASIN/SKU) | ¿Qué tengo listado? |
| **KEEPA (CSV)** | Mercado, fotos, competencia | ¿Qué pasa fuera? |

⚰️ **SALUD_FBA estuvo aquí y se jubiló el 23-ago-2026** (`migraciones/2026-08-23_jubilar_salud_fba.sql`).
Amazon servía ficheros truncados; lo relevó INVENTARIO_FBA. `procesador_salud_fba.py` **ya no existe**
en el repo. ⚠️ Pero **la palabra `salud_fba` sigue viva como VISTA de compatibilidad** sobre
`inventario_fba` — lo que se jubiló es el INFORME, no el nombre: si lo ves en una consulta, no es un
fantasma. Y `salud_fba_historico` **no se borra a propósito**: es memoria congelada del 16-ago que lee
`v_nunca_enviado_fba` (por eso, cualquier cifra que salga de ahí necesita su fecha pegada, §1.4).

📌 `procesador_canal_amazon_es.py` **no está en la tabla y no es un descuido**: no lee ningún informe.
Recalcula comisión y logística desde TRANSACCIONES, ya cargado. Es derivado, no una fuente.

Si tu código suma dos de estos, está mal. Si dos discrepan, **no promedies ni lo achaques al
desfase: es un dato, y hay que explicarlo al dígito.**
