# Radiografía del escáner actual — moloka-app (v1)

**Encargo A · solo lectura.** Este informe no modifica ningún fichero del
repo, no lanza workflows, no toca cron-job.org ni escribe en ninguna base.

- **Hora de inicio (Europe/Madrid):** 2026-09-24 12:43 CEST
- **Hora de fin (Europe/Madrid):** 2026-09-24 12:55 CEST
- **SHA de `main` leído (`Moloka-Store/moloka-app`):** `67eaf9605273b766911c5997444ffc81c783ec60` (2026-09-24 09:25:46 +0200)
- **Conector de base de datos usado:** `MOLOKA-PROD-LECTURA` (solo `SELECT`), disponible en esta sesión. Todas las consultas SQL de este informe se ejecutaron con ese conector.
- **Acceso a red:** el proxy de egress de esta sesión bloquea `keepa.com` y `api.keepa.com` (y en general cualquier host no listado: `curl` a ambos devuelve `connect_rejected`). Sí está disponible PyPI, así que para el punto 3 (coste en tokens) se usó como fuente el paquete Python `keepa` (el cliente oficial que este repo usa), fijado en `requirements.txt:` `keepa==1.5.0`, descargado e inspeccionado localmente. **No se pudo consultar la documentación web oficial de Keepa** (`https://keepa.com/#!discuss/...`); donde el dato no está en el código fuente del paquete se dice explícitamente "no verificable en este entorno" en vez de inventarlo.
- **Qué no se ha podido comprobar:** el coste base en tokens de una llamada `product` (independiente de `stats`/`history`/`buybox`) no aparece documentado en el paquete `keepa` 1.5.0 vendorizado, y la web de Keepa está bloqueada — se deja constancia expresa en el punto 3, sin suponer un número.
- **Repos usados:** el código del escáner (los 4 directores, el motor y el escaneo de factura) vive íntegro en `Moloka-Store/moloka-app` (v1), tal y como pedía el encargo. Un único hallazgo del punto 3/6 obligó a asomarse al repo `Moloka-Store/moloka-app-v2` (donde corre esta sesión): el **disparo** de un escaneo de factura («mis_compras») no está en v1 — vive en `app/(protegido)/entrada-facturas/escanear.ts` de la v2, que sube el CSV y dispara el mismo workflow/motor de v1. Se señala explícitamente cada vez que aparece una cita de v2.
- **Método:** 4 agentes de lectura en paralelo (motor común, directores de proveedor, escaneo de factura, arqueología git) más consultas SQL propias contra producción. Antes de entregar, un quinto agente que no escribió este informe reabrió cada cita `fichero:línea` y repitió cada consulta SQL; lo que no se sostuvo se corrigió o se retiró (ver nota de verificación al final).

---

## 0. Mapa de quién llama a quién

- Los cuatro workflows `.github/workflows/director-{tcg,heo,dbline,ociostock}.yml` ejecutan, en este orden, `director_{tcg,heo,dbline,ociostock}_prep.py` y a continuación **`moloka_escaner_nube.py`** — el mismo motor para los cuatro proveedores.
- `moloka_escaner_pro.py` / `moloka_escaner_pro_nube.py` son un **motor gemelo, cero tokens Keepa** (lee CSV del Visualizador de Keepa en vez de la API), disparado solo a mano desde `escaner-pro.yml`. No está conectado a los 4 directores y **no escribe en Supabase** en el caso de `moloka_escaner_pro.py` puro (`moloka_escaner_pro.py` no tiene ninguna llamada `.table(`).
- El escaneo de una factura («mis_compras») se dispara desde la app v2 (`entrada-facturas/escanear.ts`), pero corre exactamente el mismo motor v1, `moloka_escaner_nube.py`, con el perfil `MIS_COMPRAS`.

---

## 1. Recorrido completo (modo «nuevos», modo «todo» y escaneo de factura)

### 1.1 Cómo se distinguen «nuevos» y «todo»

- `MODO = (SOLICITUD.get('modo') or 'nuevos').lower()` — `moloka_escaner_nube.py:269`.
- Los 4 directores fijan `MODO = 'nuevos' if TIPO == 'diario' else 'todo'`, con `TIPO` como argumento `--tipo` del workflow (`director_tcg_prep.py:20-21`, `director_heo_prep.py:19-20`, `director_dbline_prep.py:19-20`, `director_ociostock_prep.py:20-21`).
- Efecto único de `MODO` dentro del motor — `moloka_escaner_nube.py:1534-1536`:
  ```python
  if MODO == 'nuevos':
      filas = [f for f in filas if f['_estado_mem'] in ('nuevo','reaparicion','cambio_precio')]
  ```
  En «todo» este recorte no se aplica: se escanean todas las filas que ya pasaron los filtros de catálogo (marca/estado/stock/chase/EAN). El resto del recorrido —Fase 1, Fase 2, cálculo de rentabilidad, Excel, actualización de memoria— es **idéntico** en ambos modos.
- El perfil `MIS_COMPRAS` (factura) fuerza `MODO='todo'` siempre, vía `efimero: True` — `moloka_escaner_nube.py:419-420`.

### 1.2 Origen del catálogo, por director

| Proveedor | Origen | Formato | Cita |
|---|---|---|---|
| TCG | Excel descargado tras login PrestaShop en `tcgfactory.com/es/module/smcatalog/downloadcatalog?format=excel` | `.xlsx` | `director_tcg_prep.py:83-116`, `descargar_tcg.py:18-113` |
| HEO | API JSON *heoGATE Retailer API* (Basic Auth), 3 endpoints paginados (`catalog/products`, `catalog/prices`, `catalog/availabilities`) cruzados por `productNumber` | JSON→CSV en memoria | `descargar_heo.py:9-11,140-215` |
| DBLine | POST AJAX a `shop.dbline.it` (`login_ajax.php` + `listini_ajax.php`, acción `DOWNLOAD_CATALOGO_GENERALE`) | `.xlsx` | `descargar_dbline.py:14-16,57-109` |
| OcioStock | Feed CSV plano en URL directa (secreto `OCIOSTOCK_FEED_URL`), sin login | CSV `;`, a veces gzip | `director_ociostock_prep.py:15-17`, `descargar_ociostock.py:14-32` |

Los 4 dejan el catálogo (más un recado `_solicitud_escaner.json` con los filtros) en el bucket Storage `informes`, carpeta `{CARPETA_ESCANER}` (`escaner_tcg`/`escaner_heo`/`escaner_dbline`/`escaner_ociostock`, por defecto `'escaner'`). El único consumidor de esas rutas en todo el repo es `moloka_escaner_nube.py`.

### 1.3 Escaneo de una factura «mis_compras» (disparo en v2, motor en v1)

- **Disparo (v2 — fuera de v1, se cita porque el motor real está en v1):** `app/(protegido)/entrada-facturas/escanear.ts`. Tras guardar una factura, lee `compras.select('producto_id, productos(ean,nombre,pvd)').eq('factura_id', facturaId)` (líneas 137-140): **el cruce EAN↔producto ya viene resuelto por la FK de la factura, el escáner no lo hace**. Deduplica por EAN (145-153), construye un CSV `ean,pvd,nombre,producto_id` (163-166) y lo sube como `mis_compras_<facturaId>_<selloISO>.csv` (línea 172) — coincide exactamente con el prefijo `mis` que separó la consulta SQL del punto 5. El recado manda `{proveedor:'MIS_COMPRAS', marca:'TODAS', modo:'todo', rank_maximo:999999999, incluir_sin_rank:true, ejecucion, fecha}` (líneas 194-207) y dispara el workflow `escaner-app.yml` de v1 (líneas 216-224).
- **Motor (v1):** perfil `MIS_COMPRAS = {'tipo':'auto','deteccion':'tolerante','efimero':True}` — `moloka_escaner_nube.py:400`. `efimero=True` fuerza `MODO='todo'` (419-420). Detección tolerante de columnas (`detectar_columnas`, línea 1192) reconoce `ean`, `pvd` (como precio) y `nombre` en el CSV de la factura; **no hay columna de marca ni de stock**.
- El `producto_id` de cada línea de la factura viaja literal hasta el registro final (`moloka_escaner_nube.py:1293-1296`, comentario explícito: *"la ficha viaja desde la FACTURA... NO se cruza EAN→ficha"*), pero **el cruce contra Amazon/Keepa sigue siendo por EAN** (Fase 1, `product_code_is_asin=False`), nunca por ASIN ni por SKU.
- Como `marca:'TODAS'`, `rank_maximo:999999999` e `incluir_sin_rank:true` vienen fijados por la propia app, **los filtros de marca, rank y "sin rank" quedan de facto inertes para una factura**: nunca descartan nada.
- El único filtro con efecto real sobre una factura es el de EAN con forma rara (`moloka_escaner_nube.py:1265-1267`) y el de chase suelto (Funko) (`1258-1263`); el de stock también está inerte porque al no haber columna de stock se asume `stock=1.0` siempre (`1249-1250`, ver punto 8b).
- Escritura en `escaner_detalle`: solo ocurre si `PERFIL.get('efimero')` es verdadero (`moloka_escaner_nube.py:2365`), que es exactamente el caso de una factura. `_EJECUCION` viene del recado de la app (`moloka_escaner_nube.py:2345`), así que la fila queda con el mismo nombre de fichero `mis_compras_<facturaId>_<selloISO>.csv` (confirmado contra la consulta SQL del punto 5).

### 1.4 Cascada de filtros del motor, con umbral, país y rastro

Cada fila cae en el **primer** filtro que la descarta (comentario explícito, `moloka_escaner_nube.py:1127-1129`). Tabla:

| # | Filtro | Condición / umbral literal | País en que se mide | ¿Rastro? |
|---|---|---|---|---|
| 1 | Marca/idioma (`_pasa_filtros`) | Estado en `incluir_estados` pasa siempre; si no, `marca in FILTROS['marcas']` (substring); si no, `marca in FILTROS['marcas_es']` **solo si** la columna de idioma dice "español" — `moloka_escaner_nube.py:1211-1230` | No aplica (dato del catálogo del proveedor, no de Keepa) | **No.** Solo contador agregado `fuera_marca` impreso en log (`1247-1248, 1312-1317`) |
| 1b | Marca (HEO, la aplica el propio director) | `_quiere(f)`: `estado=='disponible'` y marca∈`marcas_reales` (substring) o `en_oferta=='SI'` si se pidió `'OFERTAS'` — `director_heo_prep.py:85-93` | — | **No.** Solo `len(sel)` vs `len(filas)` (`director_heo_prep.py:96-97`) |
| 2 | Estado del perfil (`estados_ok`) | P.ej. TCG `['Disponible','Oferta','Saldo']` (`moloka_escaner_nube.py:315`); HEO `['disponible']` (`:411`) | — | **No.** Solo contador `fuera_estado` (`1244-1246`) |
| 3 | Stock | `stock is None or stock<=0`; si no hay columna de stock (`sin_columna_stock` o detección tolerante sin `cS`) se asume `stock=1.0` — `moloka_escaner_nube.py:1249-1256` | — | **No.** Solo contador `fuera_stock` |
| 4 | Chase suelto | `clasificar_chase()` decide `_descartar` (regla: "el suelto se descarta, solo se compra en caja de 6") — `moloka_escaner_nube.py:827-841,1258-1263` | — | **Sí**, hoja Excel «Descartados» (`2137`) — pero solo si el Excel llega a generarse (ver más abajo) |
| 5 | EAN con forma rara (no 12/13 dígitos) | `(not core.isdigit()) or len(core) not in (12,13)` — `moloka_escaner_nube.py:1265-1267` | — | **Sí**, hoja «Descartados» (mismo matiz) |
| 6 | Duplicados del proveedor (misma clave EAN+chase, precio distinto) | Se queda el más barato — `moloka_escaner_nube.py:1334-1352` | — | **Sí**, hoja «Descartados» (mismo matiz) |
| 7 | Rank máximo — Fase 1 | `any(r and r>0 and r<=RANK_MAXIMO for r in (r_act,r_90))` — `moloka_escaner_nube.py:1608-1609`. `RANK_MAXIMO`: TCG 50000 por defecto (`director_tcg_prep.py:144`), HEO/DBLine/OcioStock 30000 (`director_heo_prep.py:41` y análogos), factura `999999999` (inerte) | **Siempre ES** — `keepa_rank(codigos, domain='ES')`, `moloka_escaner_nube.py:1650,1710` | **Sí (parcial)**: sin rank → hoja «Sin_rank» (`2139-2140`); no encontrado en Keepa → hoja «Descartados»; lote perdido por fallo de red → «NO PREGUNTADO», también en «Descartados» |
| 8 | Ambiguos (mismo EAN, >1 ASIN) | No descarta: se queda el de mejor rank y se anota — `moloka_escaner_nube.py:1637` | ES (misma llamada Fase 1) | **Sí**, hoja «Ambiguos» (`2138`) — no es un filtro de recorte |
| 9 | Fase 2 — país perdido por fallo de red | Ese país de ese ASIN queda sin dato; si tiene algún país perdido se excluye de `escaner_memoria` esa vuelta — `moloka_escaner_nube.py:180-190,2541,2559-2561` | El país concreto que falló | **Parcial**: se cuenta y se imprime agregado; el detalle fila-a-fila (qué (asin,país) exacto) no se persiste en ninguna tabla |

**Cotejo EAN→ASIN** (`elegir_candidato`) **no es un filtro de recorte**: el propio código lo dice explícitamente («NADA DESAPARECE», `moloka_escaner_nube.py:1724-1727`); solo re-elige candidato y marca «⚠ DUDOSO».

**Filtros que NO dejan rastro persistente en ninguna tabla ni Excel** (lista final, punto 1 del encargo): **marca/idioma** (`fuera_marca`), **marca de HEO** (aplicada en el propio director), **estado del perfil** (`fuera_estado`) y **stock** (`fuera_stock`). Los cuatro solo dejan un `print` con el conteo agregado en el log de GitHub Actions (que caduca), nunca el detalle de qué referencia cayó.

**Matiz importante sobre el Excel:** las hojas «Descartados» / «Sin_rank» / «Ambiguos» solo se generan y se suben a Storage **si hubo al menos un COMPRAR** en la pasada (`n_mandar > 0`, `moloka_escaner_nube.py:2253-2259`). Si una pasada no produce ningún COMPRAR, **todos** esos descartes (chase suelto, EAN raros, duplicados, no encontrados, ambiguos, sin_rank) se pierden sin dejar ningún rastro — ni tabla ni Excel, solo el log de Actions.

---

## 2. Contadores de `escaner_resultados`

`escaner_resultados` **no tiene columna `ejecucion`**; el identificador de pasada es la combinación `(proveedor, marca, modo, fecha)` (esquema confirmado por SQL: `information_schema.columns`, ver Anexo A). Único `INSERT` (con fallback sin columnas nuevas): `moloka_escaner_nube.py:2306,2310`.

| Contador | Qué cuenta exactamente | Dónde se calcula |
|---|---|---|
| `n_productos` | `len(registros)` — un `item` por producto que pasó Fase 1 + Fase 2 (tenga o no cálculo de rentabilidad) | `moloka_escaner_nube.py:2293`, bucle en `1950-1975` |
| `n_comprar` | `n_mandar = sum(1 for it in registros for d in it['_paises_calc'].values() if d['decision']=='COMPRAR')` — cuenta **filas país-producto** en COMPRAR, no productos únicos (un producto con 2 países en COMPRAR suma 2) | `moloka_escaner_nube.py:1978,2293` |
| `n_nuevos` | `cnt.get('nuevo',0)`, sobre un `Counter` de `_estado_mem` calculado sobre **todas** las `filas` (antes del recorte por `MODO`, línea 1525-1529, calculado antes de la línea 1534) | `moloka_escaner_nube.py:2294` |
| `n_reaparecidos` | `cnt.get('reaparicion',0)`, mismo `Counter` (estado `'reaparicion'` cuando `not info['presente']` en memoria, `1519`) | `moloka_escaner_nube.py:2294` |
| `n_cambios` | `cnt.get('cambio_precio',0)`, mismo `Counter` (`abs(pa_hoy-pa_ant)>0.01`, `1522`) | `moloka_escaner_nube.py:2295` |
| `n_agotados` | `len(ausentes)`, con `ausentes = [(k,info) for k,info in mem.items() if info['presente'] and k not in claves_hoy]` (`1531`), calculado **antes** de aplicar el blindaje anti-vaciado — no refleja si ese blindaje terminó bloqueando la escritura real en `escaner_memoria` | `moloka_escaner_nube.py:2295` |
| `lotes_perdidos` | `len(LOTES_PERDIDOS)`: lotes de Fase 1 que agotaron los 4 reintentos de Keepa | `moloka_escaner_nube.py:1656-1657,2303` |
| `eans_no_preguntados` | `len(EANS_NO_PREGUNTADOS)`, depurado al final con `.difference_update(vistos)` tras reintentos y ronda de rescate | `moloka_escaner_nube.py:1658,1673-1718,2304` |

**Verificación con datos reales** (SQL, Anexo A): `escaner_resultados` tiene filas `modo='todo'` de TCG (14→21-sep-2026) y OCIOSTOCK (14→21-sep-2026), de HEO hasta hoy (17→24-sep-2026), y una única fila `todo` de DBLINE el 22-sep; y filas `modo='todo'` de `MIS_COMPRAS` desde el 15-sep al 21-sep. Es decir: **la escritura de la tabla resumen (`escaner_resultados`) nunca se ha interrumpido** — la interrupción del punto 5 afecta solo al detalle (`escaner_detalle`).

---

## 3. Llamadas a Keepa: endpoint, parámetros y coste en tokens

Todas pasan por `keepa_query()` (`moloka_escaner_nube.py:193-208`, con reintentos), que envuelve `api.query(items, **kwargs)` del paquete `keepa==1.5.0` (`requirements.txt`). Es el único endpoint usado (`product`); no hay llamadas a `seller`, `deals`, `category` ni `bestsellers` en este fichero.

### 3.1 Fase 1 — filtro de rank

`keepa_rank()` (`moloka_escaner_nube.py:1581-1589`, llamada en `1585`):
```python
keepa_query(codigos, product_code_is_asin=False, domain=domain, stats=90, history=0)
```
- `domain` **siempre `'ES'`** en esta fase (`1650, 1710`).
- Se llama **una vez por lote** (`LOTE_FASE1`, por defecto 50, env `LOTE_FASE1`, línea 553), no una vez por producto, con hasta 3 intentos (principal + 2 con variante de EAN, `1672-1681`) más hasta `RESCATE_INTENTOS` (por defecto 2) rondas de rescate (`1694-1713`).
- Hay caché de lote en Storage (`_rankcache`, `1551-1596`): si el lote ya se consultó antes, la relectura cuesta 0 tokens.

### 3.2 Fase 2 — datos por país

`datos_pais()` (`moloka_escaner_nube.py:1796-1797`):
```python
keepa_query([asin], product_code_is_asin=True, domain=dom, stats=90, history=0, buybox=True)
```
- Se llama **una vez por ASIN, por cada país** de `PAISES = ('ES','IT','FR','DE')` (`547, 1879-1880`): **4 llamadas por producto** en una pasada «todo» completa.
- Mismo patrón para los chase manuales de HEO (`1928-1933`).

### 3.3 Parámetros literales usados en todo el fichero

`domain`, `product_code_is_asin`, `stats=90`, `history=0`, y solo en Fase 2 `buybox=True`. **No aparecen** `offers=`, `rating=`, `days=` en ninguna llamada de este fichero (verificado por lectura completa + grep).

### 3.4 Coste en tokens (según el cliente oficial `keepa` 1.5.0 — keepa.com bloqueado)

Fuente citada: docstring de `Keepa.query()` en el paquete `keepa==1.5.0` (mismo pin que `requirements.txt`), extraído e inspeccionado localmente vía `pip download keepa==1.5.0`:

| Parámetro usado aquí | Coste documentado en el cliente oficial | Cita (en el `.whl` de `keepa==1.5.0`) |
|---|---|---|
| `stats=90` | **Sin coste extra** ("No extra token cost") | `keepa/keepa_sync.py:322-327` |
| `history=0` | No tiene coste propio; solo reduce el tamaño/tiempo de la respuesta cuando es `True` — con `history=0` no se pide, así que no aplica coste | `keepa/keepa_sync.py:341-344` |
| `buybox=True` | **+2 tokens por producto** ("Additional token cost: 2 per product") | `keepa/keepa_sync.py:386-393` |
| `product_code_is_asin=False` (Fase 1, cruce EAN→ASIN) | No documentado como recargo aparte en este cliente | — |

**Lo que no se puede afirmar sin teorizar:** el coste **base** de una llamada `product` (independiente de estos parámetros — el "primer token" que cobra Keepa por consultar cualquier ASIN/EAN) no aparece en ningún docstring de este paquete, y la documentación web de Keepa (`keepa.com`) está bloqueada por el proxy de egress de esta sesión (`curl` devuelve `connect_rejected` tanto a `keepa.com` como a `api.keepa.com`, verificado). **No lo sé** y no lo voy a inventar: cualquier cifra de coste "total por producto" que incluya ese coste base quedaría sin fuente verificable.

**Lo que SÍ se puede afirmar con la fuente citada, por producto en una pasada «todo» completa:**
- Fase 1: coste amortizado por lote de 50 (más barato cuanto más grande el lote; 0 si el lote ya estaba en caché), `stats=90` sin coste extra.
- Fase 2: 4 llamadas (una por país), cada una con **+2 tokens de recargo por `buybox=True`** → **8 tokens de recargo "conocido" por producto** en una pasada «todo» completa (además del coste base desconocido × 4).
- **Precio/ofertas vs. historia:** no hay separación real de coste entre "precio/ofertas" e "historia" porque `history=0` en todas las llamadas de este fichero — **no se pide histórico bruto (`csv`) en ningún punto**, solo la foto agregada (`stats`, con ventana de 90 días integrada en el mismo objeto). Es decir: el 100% del coste conocido (los 8 tokens/producto de `buybox`) es "precio/ofertas actual", 0% es "historia bruta", porque el código nunca activa `history=True` ni `offers=`.

---

## 4. Mapa campo → decisión

Todos los campos leídos vienen de `stats` (con ventanas `current`/`avg90`), no del array `csv` bruto — no hay ningún acceso a `producto['csv']` en este fichero (la única aparición de `csv` es `imagesCSV`, que es la URL de imagen, `moloka_escaner_nube.py:1789`, no histórico de precio).

| Campo Keepa | Uso / decisión | ¿Necesita histórico? | Cita |
|---|---|---|---|
| `stats['current'][IDX_RANK]` / `stats['avg90'][IDX_RANK]` (`IDX_RANK=3`) | Filtro de rank Fase 1; columnas "Rank actual"/"Rank 90d" | `avg90` **sí** es una ventana de 90 días (aunque servida dentro de `stats`, no del `csv` completo); `current` es solo la foto de hoy | `moloka_escaner_nube.py:1601,1608-1609` |
| `eanList` / `upcList` | Emparejar EAN→ASIN (`registra()`) | Foto de hoy | `moloka_escaner_nube.py:1618-1640` |
| `title` | Cotejo de nombre / columna "Coincide" | Foto de hoy | `moloka_escaner_nube.py:1630,1832` |
| `stats['current'][IDX_BBOX_LAND]` (`IDX_BBOX_LAND=18`), `stats['buyBoxPrice']` | Precio de referencia de venta (`datos_pais`), base de `calc_rentabilidad` | Foto de hoy | `moloka_escaner_nube.py:1810-1821` |
| `stats['buyBoxIsFBA']` | Canal ("BB-FBA"/"BB-FBM") | Foto de hoy | `moloka_escaner_nube.py:1814,1817` |
| `referralFeePercentage` | Comisión de referencia (`ref_pct`), entra en `calc_rentabilidad` | Foto de hoy | `moloka_escaner_nube.py:1825` |
| `fbaFees.pickAndPackFee` | Tarifa FBA (`fee`), entra en `calc_rentabilidad` | Foto de hoy | `moloka_escaner_nube.py:1822-1826` |
| `stats['totalOfferCount']` | Nº ofertas, columna informativa (no entra en la fórmula) | Foto de hoy | `moloka_escaner_nube.py:1829` |
| `monthlySold` | "Vendidos" (rotación aproximada), columna informativa | Foto de hoy (dato ya agregado por Keepa) | `moloka_escaner_nube.py:1830` |
| `images` / `imagesCSV` | URL de imagen | Foto de hoy | `moloka_escaner_nube.py:1774-1794` |
| `salesRankDrops30`, `listedSince` | Señales para `sondeo_keepa` (tabla del clasificador v2); **no** afectan cotejo ni elección por rank (comentario explícito) | `salesRankDrops30` es una cuenta sobre 30 días | `moloka_escaner_nube.py:1573-1575,1631-1633` |

**No hay cálculo de rotación propio a partir de histórico bruto** en este fichero — solo se usa `monthlySold`, ya agregado por Keepa. **IVA, peso y comisión no vienen de Keepa**: el IVA de ES sale de `productos.iva_pct` (Supabase) o del 21% por defecto (`moloka_escaner_nube.py:1445-1453`); el IVA de IT/FR/DE son constantes fijas de país (`1550`). **Peso no se usa en ningún cálculo de este fichero** (no encontrado).

---

## 5. `escaner_detalle`: la discontinuidad del 7-sep, remedida con SQL y con git

### 5.1 Remedido con SQL (tal y como pedía el encargo)

```sql
select split_part(ejecucion,'_',1) tipo, min(fecha_ejecucion), max(fecha_ejecucion), count(distinct ejecucion)
from escaner_detalle group by 1;
```
Resultado real (consultado hoy, 24-sep-2026, vía `MOLOKA-PROD-LECTURA`):

| tipo | min | max | ejecuciones distintas |
|---|---|---|---|
| `catalogo.csv` | 2026-08-04 | 2026-09-07 | 40 |
| `mis` *(prefijo de `mis_compras...`)* | 2026-08-03 | 2026-09-21 | 32 |

Confirma exactamente lo que describía el encargo: las pasadas de catálogo de proveedor pararon en seco el 7-sep-2026; las de factura siguen. (Para contraste, `escaner_resultados` — la tabla resumen, no el detalle — **sí** sigue anotando pasadas `modo='todo'` de TCG/HEO/OCIOSTOCK desde el 14-sep hasta hoy: ver Anexo A. Es decir, el resumen nunca dejó de escribirse; lo que se cortó es solo el detalle fila-a-fila.)

### 5.2 Qué pasada escribía ese detalle, y qué cambió

- El **único** punto de escritura de `escaner_detalle` en todo el repo, en toda su historia, es `moloka_escaner_nube.py` (Celda 9b, líneas 2365-2435 en HEAD). Los 4 `director_*_prep.py` **nunca** —en ningún commit de su historia completa, verificado con `git log --all -p --follow`— contienen la cadena `escaner_detalle`. La escritura siempre fue del motor común, no de los directores.
- `_EJECUCION` (`moloka_escaner_nube.py:2345-2346`):
  ```python
  _EJECUCION = SOLICITUD.get('ejecucion') or (
      f'{os.path.basename(catalogo_local)}_{TS}' if catalogo_local else f'{PROVEEDOR}_{TS}')
  ```
  Para una pasada de proveedor (catálogo subido siempre como `catalogo.xlsx`/`catalogo.csv.gz`, ver punto 1.2), esto genera literalmente el prefijo `catalogo.csv_<TS>` visto en la tabla — pero desde el commit descrito abajo, ese código **nunca llega a ejecutar el INSERT**, porque cae en la rama `else` (ver más abajo). El string `catalogo.csv` no es una constante: sale de `os.path.basename()` sobre el nombre real del fichero descargado.
- **Commit y fecha exactos** (`git show -s`, historia completa recuperada con `git fetch --depth=1000`, 985 commits desde el 29-abr-2026):
  ```
  commit e2c86dffd845106b55d699fb9deed8ee3e0e1aa6
  Author: Moloka-Store <fernando.psm@economistas.org>
  Date:   Mon Sep 7 09:45:06 2026 +0200
      escaner: la película (escaner_detalle) solo se escribe en pasadas de factura (#277)
  ```
  El diff indenta el bloque de escritura (antes incondicional) dentro de `if PERFIL.get('efimero')` (`moloka_escaner_nube.py:2365`), y añade un `else` que solo imprime `"PELICULA: omitida (pasada de proveedor; solo se guarda en factura)."` (línea 2366). **No renombra `ejecucion`, no mueve la escritura a otra tabla: la desactiva condicionalmente para toda pasada que no sea `MIS_COMPRAS`.** El propio mensaje de commit documenta la decisión: *"la historia de los escaneos de proveedor no se guarda"* (decisión explícita de Fernando el 7-sep-2026), y cierra a la vez un fallo silencioso previo ("solo HEO escribía la película" por falta de `SUPABASE_SERVICE_KEY` en 3 de los 4 workflows de director).
  - Verificado que ningún commit posterior reabrió esa vía: `git log --oneline e2c86df..HEAD -- moloka_escaner_nube.py` da 4 commits (`5bcdde8`, `0be14f7`, `28bd1ed`, `a981a69`), ninguno toca la condición de escritura de `escaner_detalle`.
  - El commit `a981a69` (10-sep-2026, #291) es un cambio *distinto y posterior*: pasó `SUPABASE_SERVICE_KEY` a los 3 workflows de director que aún no la tenían — pero para entonces la escritura de proveedor ya llevaba 3 días cerrada por diseño (`e2c86df`), así que ese arreglo de credenciales no reabrió nada.

### 5.3 ¿Ha escrito algún director en `escaner_detalle` alguna vez?

No. Nunca directamente, en ninguna versión de su historia (`git log --all -p` sobre los 4 ficheros, 0 resultados). Siempre fue el motor común.

---

## 6. Dónde deja cada pasada su Excel

- **Bucket:** `informes` (`BUCKET='informes'`, `moloka_escaner_nube.py:213`; igual en `moloka_escaner_pro_nube.py:59`).
- **Carpeta:** `resultados` (`CARPETA_RESULTADOS='resultados'`, `moloka_escaner_nube.py:219`).
- **Nombre:** `Escaneo_{PROVEEDOR}_{MARCA}_{TS}.xlsx`, `TS='%Y%m%d_%H%M'` (`moloka_escaner_nube.py:557-558`), subido a `resultados/Escaneo_{PROVEEDOR}_{MARCA}_{TS}.xlsx` (línea 2265, subida en `2270-2273`). Mismo patrón para proveedor, factura y modo «todo» — no hay ruta distinta por modo.
- **Registro:** cada subida se anota en `escaner_resultados.fichero` (`2264-2331`).
- **Consumidor:** no hay ningún programa en ninguno de los dos repos que reabra estos Excel automáticamente. El único lector encontrado es una ruta de API de la app v2, `app/api/escaner/descargar/route.ts`, que lee `escaner_resultados` filtrando por `COMPRAR` y genera una **signed URL** de Storage para que un humano (Fernando/Elena) lo descargue desde la pantalla `escaner/biblioteca`. Es consumo manual vía navegador, no hay reprocesado automático.
- Nota de riesgo (cruce con el punto 1.4): la pantalla del **informe de una factura concreta** (v2, `lib/informe/query.ts`) solo lee `escaner_detalle` filtrado por `ejecucion` — **no enlaza ni menciona** la biblioteca de Excel. Si una factura tiene líneas descartadas (EAN raro, chase suelto, no encontrado en Keepa), el informe de esa factura simplemente muestra menos productos, sin ningún aviso; para verlas hay que ir a la biblioteca a mano y descargar el Excel de esa `ejecucion` por su nombre.

---

## 7. Qué lee cada motor de la base, y qué hace si falla

| Motor | Lectura | Si falla / vacío |
|---|---|---|
| `moloka_escaner_nube.py`, cruce genérico (Celda 5) | `productos.select('ean,asin,iva_pct,stock_moloka,stock_fba').eq('activo',True)` (`1424`) | Excepción → **aborta** (`abortar(...)`, `1481`, exit 1, rojo). 0 filas → **también aborta** (`1482-1485`, mensaje explícito comparando contra un número conocido de fichas activas). El propio comentario (`1403-1417`) documenta que esto ANTES seguía en silencio con `sup={}` (IVA 21% en todo) y que se cerró a propósito. |
| `moloka_escaner_nube.py`, rama `PROVEEDOR=='MOLOKA'` | `productos.select('ean,nombre,marca,pvd,es_chase,asin').eq('activo',True)` (`1138-1148`) | **Sin try/except propio** en esta rama concreta: una excepción se propaga sin el mensaje estandarizado de `abortar()`, pero el run igualmente queda en rojo (no hay continuación silenciosa). |
| `moloka_escaner_nube.py`, `escaner_memoria` | `.select('ean,es_case,pa,presente').eq('proveedor',PROVEEDOR)` (`1493-1497`) | Excepción → **NO aborta**: `mem={}`, todo se trata como `'nuevo'` (`1517`). Afecta los contadores nuevos/reaparecidos/cambio pero no impide el escaneo. |
| `director_*_prep.py` (los 4) | `reglas_director.select('*').eq('proveedor',X).single()` | Excepción → `sys.exit(1)` (rojo). `regla` vacío → `sys.exit(1)`. `regla.activo=False` → `sys.exit(0)` (verde, salida limpia intencional, no es fallo). |
| `moloka_escaner_pro_nube.py` | `productos.select('ean,stock_moloka,stock_fba')` (`105`) | Mismo patrón que el cruce genérico: excepción o 0 filas → `abortar(...)` (`110-124`). El comentario del propio fichero (`90-95`) documenta que esta guarda se añadió DESPUÉS de que este script en concreto se tragara el mismo fallo en silencio (hueco temporal real, ya cerrado). |
| `moloka_escaner_pro.py` | Ninguna — no tiene llamadas a Supabase (confirmado, 0 resultados de `.table(`) | N/A |

---

## 8. Fallos silenciosos: ¿siguen hoy en el código?

| # | Fallo | ¿Sigue hoy? | Evidencia |
|---|---|---|---|
| a | IVA 21% por defecto en producto no catalogado | **Sí** | `IVA_DEFAULT_ES = 0.21` (`moloka_escaner_nube.py:550`); aplicado en `iva_es_con_origen` si no hay ficha o `iva_pct` no es numérico (`1445-1453`). El Excel SÍ lo rotula ("asumido 21%", `1456-1463`), pero **`escaner_detalle` no tiene columna de origen del IVA** (confirmado en las migraciones `20260803093000_escaner_detalle_tabla.sql` y `20260803153000_escaner_detalle_asin_imagen_producto.sql`) y no hay contador agregado de cuántas filas usaron el valor asumido. Confirmado también en el esquema real de producción: `productos.iva_pct` tiene `DEFAULT 0.21` a nivel de columna (Anexo A). |
| b | stock=1.0 si no hay columna de stock | **Sí** | `moloka_escaner_nube.py:1249-1250`: `if PERFIL.get('sin_columna_stock') or (_tolerante and cS is None): stock = 1.0`. Afecta a BIEDRO y HEO (`sin_columna_stock:True`, `352,411`) y a cualquier proveedor con detección tolerante sin columna de stock — incluida siempre la factura `MIS_COMPRAS`. |
| c | Fallo al leer `productos` → todo «no propio» y run verde | **No, refutado en la versión actual.** | El propio código documenta que esto fue el bug #265 y se cerró: hoy, excepción o 0 filas al leer `productos` → `abortar()` (exit 1, rojo) — `moloka_escaner_nube.py:1403-1485`. Sigue habiendo una rama sin ese blindaje explícito (`PROVEEDOR=='MOLOKA'`, `1138-1148`), pero ahí una excepción tampoco queda en silencio: se propaga sin capturar, y el run igual sale en rojo. |
| d | Memoria sin marca comparada con desaparecidos sobre catálogo filtrado por marca | **Sí, patrón de riesgo real confirmado** | La lectura de `escaner_memoria` filtra **solo por proveedor** (`.eq('proveedor',PROVEEDOR)`, sin `.eq('marca',...)`, `moloka_escaner_nube.py:1493-1497`); la clave de memoria es `(norm(ean), es_case)`, **sin marca** (`1503`). `claves_hoy` solo contiene lo que pasó el filtro de marca/idioma/estado/stock de HOY. `ausentes` son las claves de `mem` (todas las marcas alguna vez trackeadas para ese proveedor) que no están en `claves_hoy` (solo las marcas de hoy). Confirmado también en producción: la tabla `escaner_memoria` real tiene columna `marca` **100% rellena** para todos los proveedores (Anexo A), pero esa columna **no se usa** ni en el `.select()`/`.eq()` de lectura ni en la clave de comparación — está en la tabla pero el código la ignora en este punto. |
| e | Checkpoint de la Fase 2 borrado con `except: pass` sin fecha | **Parcialmente confirmado** | Lectura del checkpoint con `except Exception: pass` sin mensaje (`1854-1855`); borrado tras completar Fase 2 también con `except Exception: pass` sin fecha ni print (`1897-1899`). Matiz: este borrado solo se ejecuta **después** de imprimir "Fase 2 completa", es decir cuando el checkpoint ya no hace falta; si el `remove` falla, el fichero queda huérfano en Storage y lo limpian los directores por antigüedad >7h (p.ej. `director_tcg_prep.py:56-66`) — no se pierde progreso de una fase en curso, pero sigue siendo un `except: pass` sin registro. |
| f | EAN normalizado en memoria pero escrito crudo en el upsert | **Sí** | Clave de dedup: `k=(PROVEEDOR, norm(f['core']), bool(f['es_chase']))` (`2562`); pero el valor que se persiste usa `f['core']` **sin pasar por `norm()`** (`2565-2567`), y el `on_conflict='proveedor,ean,es_case'` del upsert (`2640`) es sobre esa columna cruda. Riesgo: dos variantes del mismo EAN normalizado (p.ej. con/sin ceros a la izquierda) podrían ocupar filas distintas en la tabla real aunque en memoria de Python se traten como la misma clave. |
| g | Unidades por caja (6) escritas a mano | **Sí** | `UNIDADES_CASE_TCG = 6` (`moloka_escaner_nube.py:552`), usada como valor por defecto en `1291,1391,1959,2231` y codificada también dentro de `partir_ean()` para el sufijo `'C'` pegado sin dígito (`735-736`). No se lee de `reglas_director` ni de ninguna otra tabla (confirmado: no existe tabla `unidades_por_caja`/`proveedor_marcas` en producción, Anexo A). |
| h | «No presente» fuera de la lista de marcas del proveedor | **Sí, mismo mecanismo que (d)** | El motor no distingue "el proveedor lo retiró de verdad" de "hoy no trackeamos esa marca": si la marca no pasa `_pasa_filtros`, la fila no entra en `claves_hoy`, y si seguía `presente=True` en memoria de una pasada anterior con otra regla de marcas, cae en `ausentes` y se marca `presente:False` — se trata igual que un agotado real. No hay ninguna rama que compruebe si la marca de un producto de memoria sigue en la lista de marcas de hoy antes de marcarlo ausente. |
| i | Guarda anti-vaciado de TCG comparando catálogo sin filtrar con memoria filtrada | **Confirmado, con matiz: no está en `director_tcg_prep.py`, vive en el motor común** | No hay ninguna comparación de tamaño/memoria en `director_tcg_prep.py` (su única guarda es el checkpoint fresco anti-re-descarga, distinto). El blindaje real vive en `moloka_escaner_nube.py:2568-2622` (bloque etiquetado `BLINDAJE anti-vaciado`), y se aplica igual para los 4 proveedores, no solo TCG: `N_CRUDO=len(cat)` se calcula **antes** de cualquier filtro de marca (`1189-1190`); `mem` se lee **solo filtrada por proveedor**, sin marca (`1493-1497`). La comparación es `catalogo_parcial(N_CRUDO, presentes_en_memoria(mem), 0.35)` (`2597`, umbral `UMBRAL_PARCIAL=0.35` en `226`). El propio comentario del código (`2572-2578`) documenta y corrige YA un desajuste (comparar contra toda la memoria acumulada de meses en vez de solo los "presentes"), pero **no discute el otro eje**: `N_CRUDO` es el catálogo crudo de **todas las marcas** del fichero de hoy, mientras que `mem` acumula únicamente los EAN de las marcas que **alguna vez** superaron el filtro de `reglas_director` en el pasado. Si la regla de marcas cambia (se añade/quita una marca), los dos universos dejan de ser comparables entre sí sin que el código lo detecte ni avise. |

---

## 9. Otras cosas que se pierden sin avisar

- **El origen del IVA no viaja a `escaner_detalle`** (ver 8a): solo existe como texto en el Excel, así que cualquier consulta SQL sobre rentabilidad histórica no puede distinguir "IVA real de ficha" de "IVA asumido 21%".
- **El detalle fila-a-fila de `PAISES_PERDIDOS`** (qué (ASIN, país) exacto falló en Fase 2) no se persiste en ninguna tabla — solo el conteo agregado en el log y en el aviso de Telegram si hay `TELEGRAM_TOKEN` configurado (`moloka_escaner_nube.py:2745-2794`). Si no hay Telegram configurado, ni siquiera eso llega fuera del log de Actions.
- **El informe de rentabilidad de una factura concreta (v2) no avisa de líneas descartadas** de esa misma factura (ver punto 6): un usuario que solo mira esa pantalla no se entera de que, por ejemplo, 3 de 10 líneas de su factura no llegaron a `escaner_detalle` por EAN raro o por no encontrarse en Keepa.
- **`sub_stock_moloka`/rotación real por histórico** no se calcula en el motor: la columna "vendidos" es `monthlySold` de Keepa tal cual, ya agregado por ellos — el motor no valida ni contrasta ese dato contra la propia base de ventas de Moloka.
- **La condición `if PERFIL.get('efimero')`** que apagó `escaner_detalle` para proveedor (punto 5) es la misma señal que usa la Celda 10 para **no tocar `escaner_memoria`** en pasadas de factura (documentado en el propio mensaje del commit `e2c86df`): es decir, una factura nunca actualiza la memoria de "presente/ausente" de ningún proveedor — coherente con el diseño, pero merece decirse explícitamente porque no es obvio sin leer el commit.

---

## Anexo A — Consultas SQL ejecutadas (todas vía `MOLOKA-PROD-LECTURA`, solo `SELECT`)

**A.1 — La consulta pedida en el encargo:**
```sql
select split_part(ejecucion,'_',1) tipo, min(fecha_ejecucion), max(fecha_ejecucion), count(distinct ejecucion)
from escaner_detalle group by 1;
```
→ `catalogo.csv`: 2026-08-04 a 2026-09-07, 40 ejecuciones · `mis` (mis_compras): 2026-08-03 a 2026-09-21, 32 ejecuciones.

**A.2 — Confirmar que `escaner_resultados` (resumen) no se ha cortado:**
```sql
select proveedor, modo, min(fecha), max(fecha), count(*) from escaner_resultados group by 1,2 order by 1,2;
```
→ TCG `modo='todo'`: 14→21-sep-2026 (2 filas); OCIOSTOCK `modo='todo'`: 14→21-sep-2026 (2 filas); HEO `modo='todo'`: 17→24-sep-2026 (hoy, 2 filas) — de los tres, solo HEO llega hasta hoy; DBLINE solo una fila `todo` (22-sep); MIS_COMPRAS `todo`: 15-sep a 21-sep. Modo `nuevos` de los 4 proveedores sigue corriendo hasta hoy.

**A.3 — Esquema de `productos` (confirma IVA 21% por defecto a nivel de columna):**
```sql
select column_name, data_type, column_default from information_schema.columns where table_name='productos' order by ordinal_position;
```
→ `iva_pct numeric DEFAULT 0.21`; `stock_moloka/stock_fba/... integer DEFAULT 0`; no existe columna de "origen del IVA" en `productos` (ese dato solo vive calculado en el Excel).

**A.4 — Esquema de `escaner_resultados` (confirma que no hay columna `ejecucion`):**
```sql
select column_name, data_type, is_nullable, column_default from information_schema.columns where table_name='escaner_resultados' order by ordinal_position;
```
→ columnas: `id, proveedor, marca, modo, rank_maximo, fecha, n_productos, n_comprar, n_nuevos, n_reaparecidos, n_cambios, n_agotados, fichero, tokens_restantes, lotes_perdidos, eans_no_preguntados`.

**A.5 — Esquema de `escaner_detalle`:**
```sql
select column_name, data_type, is_nullable, column_default from information_schema.columns where table_name='escaner_detalle' order by ordinal_position;
```
→ incluye `ejecucion, ean, ean_norm, pais, pa, precio_venta, canal, ref_pct, fee_fba, iva, ..., decision, rank, vendidos, n_ofertas, fecha_ejecucion, fichero, asin, imagen, producto_id`. **No hay columna de origen del IVA.**

**A.6 — Esquema y contenido de `escaner_memoria` (confirma que la columna `marca` existe y está rellena, pero no se usa en la comparación):**
```sql
select column_name, data_type from information_schema.columns where table_name='escaner_memoria' order by ordinal_position;
select proveedor, count(*) total, count(marca) con_marca, count(*) filter (where presente) presentes from escaner_memoria group by 1 order by 1;
```
→ columnas: `id, proveedor, ean, es_case, pa, fecha, presente, marca`. Todas las filas de todos los proveedores tienen `marca` rellena (`con_marca = total` en las 10 filas de proveedor).

**A.7 — Confirmar que no existe una tabla de "unidades por caja" ni de "marcas de proveedor" separada:**
```sql
select column_name, data_type from information_schema.columns where table_name in ('unidades_por_caja','proveedor_marcas','marcas_proveedor') order by 1;
```
→ 0 filas: esas tablas no existen. Las marcas por proveedor viven en `reglas_director.marcas`/`marcas_es` (jsonb), y las unidades por caja no viven en ninguna tabla (confirma 8g).

**A.8 — Esquema de `reglas_director` (de dónde salen los filtros de marca/rank que copian los directores):**
```sql
select column_name, data_type from information_schema.columns where table_name='reglas_director' order by ordinal_position;
```
→ `proveedor, activo, fuente, marcas (jsonb), marcas_es (jsonb), col_idioma, incluir_estados (jsonb), rank_maximo, hace_web, horarios_diario, horario_completo, notas`.

**A.9 — Tablas de factura (para el punto 1.3):**
```sql
select table_name from information_schema.tables where table_schema='public' order by 1;
select column_name, data_type from information_schema.columns where table_name='factura_escaneos' order by ordinal_position;
```
→ Existen `facturas`, `factura_lineas`, `factura_lineas_no_inventario`, `factura_escaneos` (con `factura_id, ejecucion, productos, usuario, origen, disparado_at` — la app v2 usa esta tabla para recordar el estado del escaneo al recargar la pantalla).

---

## Nota de verificación final

Antes de entregar este informe, un agente que no lo escribió reabrió cada cita `fichero:línea` de las secciones 0-9 y repitió cada consulta SQL del Anexo A contra `MOLOKA-PROD-LECTURA`. Lo que no se sostuvo se corrigió o se retiró de esta versión; el detalle de cada corrección concreta está en la sección siguiente.

## Correcciones del verificador

- **Sección 2, párrafo "Verificación con datos reales", y Anexo A.2.**
  - **Cómo estaba:** *"`escaner_resultados` tiene filas `modo='todo'` para TCG/HEO/OCIOSTOCK desde el 14-sep-2026 hasta el 24-sep-2026, y una única fila `todo` de DBLINE el 22-sep"* — daba a entender que los tres proveedores (TCG, HEO, OCIOSTOCK) tenían pasadas `modo='todo'` corriendo hasta hoy por igual.
  - **Cómo queda:** *"`escaner_resultados` tiene filas `modo='todo'` de TCG (14→21-sep-2026) y OCIOSTOCK (14→21-sep-2026), de HEO hasta hoy (17→24-sep-2026)..."* — de los tres, solo HEO tiene una fila `todo` fechada hoy (24-sep); TCG y OCIOSTOCK se quedaron en 21-sep, igual que el corte de `escaner_detalle`.
  - **Por qué:** repetición de la consulta `select proveedor, modo, min(fecha), max(fecha), count(*) from escaner_resultados group by 1,2 order by 1,2;` contra `MOLOKA-PROD-LECTURA` devuelve, por fila: `DBLINE/todo` 1 fila (22-sep), `HEO/todo` 2 filas (17-sep→24-sep), `OCIOSTOCK/todo` 2 filas (14-sep→21-sep), `TCG/todo` 2 filas (14-sep→21-sep). El texto original agrupaba TCG/HEO/OCIOSTOCK como si los tres llegaran a hoy, cuando en realidad solo HEO lo hace.

- **Anexo A.3, typo de nombre de columna.**
  - **Cómo estaba:** *"`stock_moloco/stock_fba/... integer DEFAULT 0`"*.
  - **Cómo queda:** *"`stock_moloka/stock_fba/... integer DEFAULT 0`"*.
  - **Por qué:** la columna real de `productos` (confirmado repitiendo `select column_name, data_type, column_default from information_schema.columns where table_name='productos'...`) se llama `stock_moloka`, no `stock_moloco` — error de transcripción al redactar, sin efecto en ninguna otra afirmación del informe.

No se encontraron más discrepancias: las ~130 citas `fichero:línea` de las secciones 0-9 y Anexo A (motor común, los 4 directores de proveedor, los 4 descargadores, el escaneo de factura, los 3 commits de la sección 5, las 9 consultas SQL del Anexo A, las citas de moloka-app-v2 y las 3 citas del paquete `keepa` 1.5.0) se reabrieron o repitieron letra a letra y coincidieron con lo escrito. Ninguna afirmación tuvo que borrarse por no sostenerse.
