# -*- coding: utf-8 -*-
"""ESCANER 2 · LO HEREDADO DEL PROCESADOR DEL ESCAPARATE (procesador_keepa_escaparate.py), COPIADO
LITERALMENTE.

Encargo B7 (25-sep-2026). `TIPADAS`: las cabeceras del export del Visualizador, copiadas de los exports
reales; de aqui salen la del pais (`Localización`) y la de las caidas de 30 dias. Texto EXACTO del commit
2f9c06a (blob c884702162), generado por script. No se importa: escaner2_motor.columnas_keepa lo saca por nombre.
🔴 NO SE TOCA A MANO: si el procesador cambia, test_escaner2_heredado.py lo avisa y decide Fernando.
"""


# ── ORIGEN: procesador_keepa_escaparate.py, líneas 171-263 · commit 2f9c06a · blob c884702162 · md5 c7a360a4b24abc98f537fcad90554db8 ──
# ---------------------------------------------------------------------------
# Columnas TIPADAS: (encabezado EXACTO del CSV, columna Postgres, tipo).
#   tipo: 't' text · 'i' integer · 'n' numeric · 'b' boolean · 'd' date ·
#         'ts' timestamptz · 'as' text[] (split por ';') · 'ac' text[] (split por ',').
# 🔒 El encabezado se compara EXACTO (sin BOM, sin espacios sobrantes). Si uno
#    no aparece → Guarda 1 ABORTA. No se adivina, no se aproxima.
# ---------------------------------------------------------------------------
TIPADAS = [
    ('ASIN', 'asin', 't'),
    ('Localización', 'dominio', 't'),
    ('Códigos de producto: EAN', 'ean_keepa_crudo', 't'),      # CONTRASTE, nunca identidad
    ('Códigos de producto: UPC', 'upc_keepa', 't'),
    ('Título', 'titulo', 't'),
    ('Marca', 'marca', 't'),
    ('Fabricante', 'fabricante', 't'),
    ('Tipo', 'tipo_producto', 't'),
    ('Imagen', 'imagenes', 'as'),                              # split por ";"
    ('Recuento de imágenes', 'n_imagenes', 'i'),
    ('Tarifa FBA Pick&Pack', 'tarifa_fba', 'n'),               # EL PREMIO
    ('% de comisión de referencia', 'comision_pct', 'n'),      # quitar " %"
    ('Comisión de referencia basada en el precio actual de la Buy Box', 'comision_eur_bb', 'n'),
    ('Caja de Compra: Actual', 'bb_precio', 'n'),
    ('Caja de Compra: Vendedor Caja de Compra', 'bb_vendedor', 't'),   # + bb_seller_id aparte
    ('Caja de Compra: Es FBA', 'bb_es_fba', 'b'),
    ('Caja de Compra: Stock', 'bb_stock', 'i'),
    ('Caja de Compra: % Amazon 30 días', 'bb_pct_amazon_30d', 'n'),
    ('Caja de Compra: Disponibilidad de la Caja de Compra', 'bb_disponibilidad', 't'),
    # 🔴 LOS TRES QUE VIVÍAN SÓLO EN `crudo` Y EL ARCHIVADO TIRABA (11-ago-2026).
    #    `keepa_escaparate_hist` no guarda `crudo` —a propósito: el CSV está en Storage—,
    #    así que estos tres campos no tenían serie histórica y no podían tenerla. Cada
    #    archivado los perdía para siempre. Promovidos a columna, el archivado se los
    #    lleva solo (copia todo menos `crudo`).
    #    🔬 Hoy: 22 fichas con envío, 102 con plazo, 75 con país.
    ('Caja de Compra: Gastos de envío', 'bb_envio', 'n'),
    ('Caja de Compra: País de envío', 'bb_pais_envio', 't'),
    # ⚠️ El plazo va como TEXTO tal cual lo da Keepa ("1 dia", "13 - 24 días", "190 días"):
    #    no se parsea a número aquí. Convertir "13 - 24 días" en un entero obliga a elegir
    #    13 o 24, y esa elección es de quien lo use, no del procesador. Además hay 31
    #    fichas con plazo y sin precio que nadie ha explicado todavía.
    ('Caja de Compra: Tiempo de envío', 'bb_plazo_txt', 't'),
    ('Vendedor FBA más barato', 'fba_mas_barato', 't'),
    ('Vendedor FBM más barato', 'fbm_mas_barato', 't'),
    # 🔴 EL PRECIO CONTRA EL QUE SE COMPETE DE VERDAD: el más barato de las ofertas NUEVAS,
    #    lo mande Amazon o lo mande el vendedor desde su casa. `p3_fba_precio` (debajo) es
    #    solo el más barato DE LOS FBA, y hay fichas con 22 ofertas FBM y ninguna FBA donde
    #    esa columna viene vacía habiendo precio de mercado.
    #    🔬 `B01MYNI1W6` el 19-ago-2026: it 21,92 € y de 18,65 € en «Nuevo: Actual», con
    #       `p3_fba_precio` vacío en los dos. Ganan precio 123 casillas de la foto.
    # ⚠️ SIN el envío dentro: el CSV solo trae gastos de envío para la Caja de Compra
    #    (`bb_envio`). No existe variante de «Nuevo: Actual» con el envío — medido sobre las
    #    claves del `crudo` real, no supuesto.
    ('Nuevo: Actual', 'nuevo_precio', 'n'),
    ('Nuevo, de Vendedor Externo FBA: Actual', 'p3_fba_precio', 'n'),
    ('Nuevo, de Vendedor Externo FBA: Stock', 'p3_fba_stock', 'i'),
    ('Nuevo, de Vendedor Externo FBM: Stock', 'p3_fbm_stock', 'i'),
    ('Recuento ofertas nuevas: Actual', 'ofertas_nuevas', 'i'),
    ('Recuento ofertas nuevas FBA: Actual', 'ofertas_nuevas_fba', 'i'),
    ('Recuento ofertas nuevas FBM: Actual', 'ofertas_nuevas_fbm', 'i'),
    ('Recuento total de Ofertas', 'ofertas_total', 'i'),
    ('Umbral de precio competitivo', 'umbral_competitivo', 'n'),   # RECADO para el trackeador
    ('Amazon: Actual', 'amazon_precio', 'n'),
    ('Amazon: Disponibilidad de la oferta de Amazon', 'amazon_disponibilidad', 't'),
    ('Clasificación de Ventas: Actual', 'rank', 'i'),
    ('Clasificación de Ventas: Promedio de 30 días', 'rank_30d', 'i'),
    ('Clasificación de Ventas: Promedio de 90 días', 'rank_90d', 'i'),
    ('Clasificación de Ventas: Descensos en los últimos 30 días', 'rank_drops_30d', 'i'),
    ('Clasificación de Ventas: Descensos en los últimos 90 días', 'rank_drops_90d', 'i'),
    ('Categorías: Principal', 'categoria', 't'),
    ('Categorías: Subcategoría', 'subcategoria', 't'),
    ('Tendencias de ventas mensuales: Ventas mensuales (Último conocido)', 'monthly_sold_ultimo', 'i'),
    ('Tendencias de ventas mensuales: Fecha de ventas mensuales (Último conocido)', 'monthly_sold_ultimo_fecha', 'd'),
    ('Tendencias de ventas mensuales: Comprados el mes pasado', 'comprados_mes_pasado', 'i'),
    ('ASIN Padre', 'asin_padre', 't'),
    ('ASIN de variación', 'asins_variacion', 'ac'),           # split por ","
    ('Recuento de variaciones', 'n_variaciones', 'i'),
    ('Atributos de variación', 'atributos_variacion', 't'),
    ('Paquete: Peso (g)', 'paq_peso_g', 'n'),
    ('Paquete: Longitud (cm)', 'paq_largo_cm', 'n'),
    ('Paquete: Anchura (cm)', 'paq_ancho_cm', 'n'),
    ('Paquete: Altura (cm)', 'paq_alto_cm', 'n'),
    ('Fecha de lanzamiento', 'fecha_lanzamiento', 'd'),       # fecha PASADA de salida
    ('Última actualización', 'keepa_actualizado', 'ts'),      # por producto, NO la foto
    ('Listado desde', 'listado_desde', 'd'),
    ('Opiniones: Valoraciones', 'rating', 'n'),
    ('Opiniones: Cantidad de valoraciones', 'n_valoraciones', 'i'),
    ('Frecuencia comprados juntos', 'comprados_juntos', 't'),
    ('URL: Slug de URL', 'slug_amazon', 't'),
    ('Descripción & Características: Característica 1', 'bullet_1', 't'),
    ('Descripción & Características: Característica 2', 'bullet_2', 't'),
    ('Descripción & Características: Característica 3', 'bullet_3', 't'),
    ('Descripción & Características: Característica 4', 'bullet_4', 't'),
    ('Descripción & Características: Característica 5', 'bullet_5', 't'),
]
