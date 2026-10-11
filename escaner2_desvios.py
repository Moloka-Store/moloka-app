# -*- coding: utf-8 -*-
"""ESCANER 2 · LOS DESVIOS DELIBERADOS DE LO HEREDADO DEL VIEJO (encargo D, 28-sep-2026).

Los ficheros escaner2_heredado_*.py son el texto EXACTO del viejo, generado por
scripts/generar_escaner2_heredado.py. Cuando Fernando decide que el escaner 2 haga algo DISTINTO que el
viejo dentro de una pieza heredada, el cambio NO se teclea en el heredado: se escribe AQUI, como pares
(texto del viejo, texto nuevo), y el generador los aplica al copiar. El banco (test_escaner2_heredado.py)
aplica los MISMOS pares al viejo antes de compararlo con el heredado, asi que sigue avisando de cualquier
otro cambio del viejo, y de este tambien si el texto de «antes» deja de estar (o esta dos veces).

Reglas de un desvio:
  · cada «antes» aparece UNA sola vez en el fichero del viejo, o no se aplica (ni el generador ni el banco);
  · el texto nuevo tiene las MISMAS lineas que el de antes: asi las «líneas X-Y» de cada cabecera
    `# ── ORIGEN` siguen siendo las del viejo;
  · se dice quien lo decidio y cuando, y la pieza que toca.

HOY, DOS (encargo D, decisiones de Fernando del 28-sep-2026):
  1. La hoja «Análisis» (Celda 9, `excel_del_viejo`): «si lo que manda son ventas mes (caidas de rank) pues
     deberia salir ese dato en el excel en lugar de los dos datos de rank». 'Rank actual' pasa a 'Ventas',
     con las caidas de 30 dias de ESE pais (0 es 0; sin dato, vacia), y salen 'Rank 90d', 'Vendidos/mes',
     'Nº ofertas' y 'Promo activa' (las tres ultimas iban siempre vacias en el escaner 2). Excepcion
     consciente a su «exactamente el mismo formato de excel del escaner antiguo» (25-sep), SOLO en estas
     columnas: formulas, formatos y semaforo siguen yendo por NOMBRE de columna (`L[nombre]`).
     El Excel del escaner 2 no lo lee nadie por letra (buscado en moloka-app y moloka-app-v2).
  2. El lector del CSV del Visualizador (`leer_csv_visualizador`): 'Caja de Compra: Es FBA' llega como
     «yes»/«no» (medido en los cuatro CSV de la pasada ced8f036, 28-sep-2026), y el lector solo daba FBA con
     'true/verdadero/sí/si/1': ni una fila 'BB-FBA' en los tres cruces guardados. Se anade «yes», como ya
     hace procesador_keepa_escaparate.py con el mismo export. El precio no cambia (es el de la caja en los
     dos casos): solo la etiqueta del canal.
Y UNO MAS (encargo CJ4, decision de Fernando del 11-oct-2026):
  3. La oferta de HEO (`descargar_catalogo_heo`, la descarga que usan la foto de cada hora y el barrido): el viejo
     daba «en oferta» si habia campana, `retailerProductDiscount` > 0 o el precio de hoy por debajo del base, y eso
     es el DESCUENTO DE CLIENTE (el «Precio incluye dto.» de la web de HEO), que en Funko llevan los de precio
     normal y pierden los rebajados (parte CJ3, 11-oct-2026). La oferta de verdad es el precio TACHADO:
     `strikePricePerUnit` > 0. En oferta pasa a ser eso, y la fila lleva `precio_tachado` (el importe tal cual lo da
     HEO, al centimo; vacio si no hay). Las cajas con chase que la descarga desvia llevan tambien su `precio_tachado`
     (el viejo no les calcula oferta; escaner2_motor._fila_de_chase la saca de ahi). Nada lee el descuento de
     cliente: no se guarda. El director viejo (descargar_heo.py) no cambia.
"""

# Heredado → {pieza: [(antes, despues), …]}. Los textos van con la sangria del VIEJO (en el heredado, la
# Celda 9 lleva 4 espacios mas: el generador los pone despues).
DESVIOS = {
    'escaner2_heredado_nube.py': {
        'excel_del_viejo': [
            ("COLS = ['Nombre','EAN','ASIN','Marca','PA (€)','País','Rank actual','Rank 90d','Vendidos/mes',\n"
             "        'Precio venta (€)','Canal BB','Nº ofertas','% Comisión',\n"
             "        'Com. Amazon (€)','Fee Logística (€)','Almacén (€)','Promo activa',\n",
             "COLS = ['Nombre','EAN','ASIN','Marca','PA (€)','País','Ventas',  # 🔑 DESVÍO D (Fernando, 28-sep-2026): escaner2_desvios.py\n"
             "        'Precio venta (€)','Canal BB','% Comisión',\n"
             "        'Com. Amazon (€)','Fee Logística (€)','Almacén (€)',\n"),
            ("            d['rank_act'] if d['rank_act'] and d['rank_act']>0 else None,\n"
             "            d['rank90'] if d['rank90'] and d['rank90']>0 else None,\n"
             "            d['vendidos'], d['precio'], d['canal'], d['n_of'], pct,\n",
             "            # 🔑 DESVÍO D: 'Ventas' = las caídas de 30 días de ESTE país, tal cual: 0 es 0 y sin dato, vacía.\n"
             "            d.get('caidas_30d'),\n"
             "            d['precio'], d['canal'], pct,\n"),
            ("            d['fee'], ALMACEN, None,\n",
             "            d['fee'], ALMACEN,\n"),
        ],
    },
    'escaner2_heredado_pro.py': {
        'leer_csv_visualizador': [
            ("                 es_fba=(es_fba in ('true','verdadero','sí','si','1')),\n",
             "                 es_fba=(es_fba in ('true','verdadero','sí','si','1','yes')),  # 🔑 DESVÍO D: Keepa escribe «yes»/«no»\n"),
        ],
    },
    'escaner2_heredado_descarga.py': {
        'descargar_catalogo_heo': [
            ("        # En oferta si: hay campana, o descuento>0, o el precio de hoy es menor que el base.\n"
             "        en_oferta = bool(campana) or (dto is not None and dto > 0) or \\\n"
             "                    (base is not None and precio is not None and precio < base - 0.001)\n",
             "        # 🔑 DESVÍO CJ4 (Fernando, 11-oct-2026): en oferta = HEO trae precio TACHADO (strikePricePerUnit > 0).\n"
             "        en_oferta = strike is not None and strike > 0\n"
             "        tachado = round(strike, 2) if en_oferta else None\n"),
            ("            'en_oferta':      ('SI' if en_oferta else ''),\n",
             "            'en_oferta':      ('SI' if en_oferta else ''), 'precio_tachado': tachado,  # 🔑 DESVÍO CJ4\n"),
            ('    print(f">>> En oferta (campana/descuento/precio<base): {en_of}")\n',
             '    print(f">>> En oferta (precio tachado de HEO, DESVÍO CJ4): {en_of}")\n'),
            # Las cajas con chase que la descarga desvia: HEO tambien les pone tachado (15 de 83 en la sonda del
            # 11-oct-2026), y el viejo no les calcula oferta. Llevan su `precio_tachado` (el de la caja).
            ("            discc = _amt(prc.get('discountedPricePerUnit'))\n",
             "            discc = _amt(prc.get('discountedPricePerUnit')); strikec = _amt(prc.get('strikePricePerUnit'))  # 🔑 DESVÍO CJ4\n"),
            ("                'precio_caja':  (None if precioc is None else round(precioc, 2)),\n",
             "                'precio_caja':  (None if precioc is None else round(precioc, 2)), 'precio_tachado': (round(strikec, 2) if strikec is not None and strikec > 0 else None),  # 🔑 DESVÍO CJ4\n"),
        ],
    },
}

# (1) en cifras, para quien compare la hoja «Análisis» con la del viejo (escaner2_huella_excel.sin_columnas).
ANALISIS_QUITADAS = ('Rank 90d', 'Vendidos/mes', 'Nº ofertas', 'Promo activa')
ANALISIS_RENOMBRADAS = {'Rank actual': 'Ventas'}


class DesvioRoto(ValueError):
    """Un desvio que ya no se puede aplicar: su «antes» no esta, o esta mas de una vez, o cambia las lineas."""


def pares(heredado):
    """[(pieza, antes, despues)] de un fichero heredado (vacio si no tiene desvios)."""
    return [(p, a, d) for p, lista in DESVIOS.get(heredado, {}).items() for a, d in lista]


def aplicar(texto_viejo, heredado):
    """El texto del viejo con los desvios de `heredado` aplicados. 🔴 Falla CERRADO (DesvioRoto) si un «antes»
    no aparece exactamente UNA vez o si el texto nuevo no tiene las mismas lineas."""
    for pieza, antes, despues in pares(heredado):
        n = texto_viejo.count(antes)
        if n != 1:
            raise DesvioRoto('%s · %s: el texto de antes aparece %d veces en el viejo (tiene que ser 1)'
                             % (heredado, pieza, n))
        if antes.count('\n') != despues.count('\n'):
            raise DesvioRoto('%s · %s: el desvio cambia el numero de lineas (%d → %d)'
                             % (heredado, pieza, antes.count('\n'), despues.count('\n')))
        texto_viejo = texto_viejo.replace(antes, despues)
    return texto_viejo


def piezas_desviadas(heredado):
    """Las piezas de `heredado` que llevan desvio, sin repetir y en su orden."""
    return list(dict.fromkeys(p for p, _a, _d in pares(heredado)))
