# -*- coding: utf-8 -*-
"""ESCANER 2 · LO HEREDADO DEL ESCANER PRO (moloka_escaner_pro.py), COPIADO LITERALMENTE.

Encargo B7 (25-sep-2026). El lector del CSV del Visualizador de Keepa: `CSV_COLS`, `norm`, `_num_csv`
y `leer_csv_visualizador`, texto EXACTO del commit 2f9c06a (blob e60c13f819), generado por script.
SI se importa (`import escaner2_heredado_pro as pro`), como antes el Escaner Pro.

🔑 Del original solo se trae `csv` de su linea 9 (`import pandas as pd, csv`): es lo unico que usan
   estas cuatro piezas, y asi el escaner 2 no necesita pandas para leer un CSV.
🔴 NO SE TOCA A MANO: si el Pro cambia, test_escaner2_heredado.py lo avisa y decide Fernando.
"""

import csv  # ← moloka_escaner_pro.py, línea 9 (`import pandas as pd, csv`): solo `csv`


# ── ORIGEN: moloka_escaner_pro.py, líneas 64-75 · commit 2f9c06a · blob e60c13f819 · md5 dfbebdc4ae3a052e7eb4a2bd28aca6a8 ──
# ===== Columnas del CSV del Visualizador (por NOMBRE: robusto a reordenacion) =====
CSV_COLS = {
    'ean':'Códigos de producto: EAN', 'asin':'ASIN',
    'rank':'Clasificación de Ventas: Actual', 'rank90':'Clasificación de Ventas: Promedio de 90 días',
    'nuevo':'Nuevo: Actual', 'buybox':'Caja de Compra: Actual', 'es_fba':'Caja de Compra: Es FBA',
    'fba':'Tarifa FBA Pick&Pack', 'compct':'% de comisión de referencia',
    'nof':'Recuento ofertas nuevas: Actual',
    'vendidos':'Tendencias de ventas mensuales: Ventas mensuales (Último conocido)',
    'vendidos2':'Tendencias de ventas mensuales: Comprados el mes pasado',
    'nvar':'Recuento de variaciones',
    'titulo':'Título',   # la de la FICHA, no la del ASIN padre (ver el porque en leer_csv_visualizador)
}


# ── ORIGEN: moloka_escaner_pro.py, líneas 89-89 · commit 2f9c06a · blob e60c13f819 · md5 02dcdbb04a7d062e3e163f764dea1ca2 ──
def norm(code): return str(code).strip().lstrip('0')


# ── ORIGEN: moloka_escaner_pro.py, líneas 169-173 · commit 2f9c06a · blob e60c13f819 · md5 bbd4139c5a71c88dc4f438d8f92a9116 ──
def _num_csv(x):
    s=(x or '').strip().replace('%','').strip()
    if s in ('','-','—'): return None
    try: return float(s.replace(',', '.'))
    except Exception: return None


# ── ORIGEN: moloka_escaner_pro.py, líneas 312-353 · commit 2f9c06a · blob e60c13f819 · md5 d2fe5fe3aabffd884c929ccc1173cd96 ──
# ===== Lectura del CSV del Visualizador (indexado por CADA EAN; celdas multi-EAN) =====
def leer_csv_visualizador(rutas):
    # Acepta UNA ruta (str) o VARIAS (list) -> las funde en un solo diccionario.
    # Asi un catalogo grande exportado de Keepa de 5.000 en 5.000 (6-7 CSV por pais)
    # se junta en un unico dataset y sale UN solo Excel.
    if isinstance(rutas, str): rutas=[rutas]
    data={}
    for ruta in rutas:
      with open(ruta, encoding='utf-8-sig', newline='') as f:
        rr=csv.reader(f); H=next(rr); rows=list(rr)
      idx={c:i for i,c in enumerate(H)}
      # Columna del titulo de Amazon (robusto al nombre exacto del export de Keepa).
      # 🔒 EL ORDEN IMPORTA, y no es por el idioma: en el export del Visualizador las dos
      # columnas EXISTEN siempre, pero 'Titulo principal' es el titulo del ASIN PADRE y solo
      # trae dato cuando el producto tiene variaciones. Medido en el export del 6-ago-2026
      # (191 filas, dominio es): 'Titulo' relleno 191/191, 'Titulo principal' 45/191.
      # Al preferir la del padre, el cotejo se quedaba ciego en el 76% de las filas.
      # 'Titulo' es ademas la que ya usa procesador_keepa_escaparate.py sobre este mismo CSV.
      _tit=None
      for _cand in ('Título','Titulo','Title','Título principal','Titulo principal'):
        if _cand in idx: _tit=_cand; break
      if _tit is None:
        for _c in H:
          _cl=str(_c).lower()
          if 'tulo' in _cl or 'title' in _cl: _tit=_c; break
      def col(row,key):
        c=CSV_COLS.get(key); return row[idx[c]] if (c and c in idx) else ''
      for row in rows:
        es_fba=col(row,'es_fba').strip().lower()
        rec=dict(asin=(col(row,'asin').strip() or None),
                 rank=_num_csv(col(row,'rank')), rank90=_num_csv(col(row,'rank90')),
                 nuevo=_num_csv(col(row,'nuevo')), buybox=_num_csv(col(row,'buybox')),
                 es_fba=(es_fba in ('true','verdadero','sí','si','1')),
                 fba=_num_csv(col(row,'fba')), compct=_num_csv(col(row,'compct')),
                 nof=_num_csv(col(row,'nof')),
                 vendidos=(_num_csv(col(row,'vendidos')) or _num_csv(col(row,'vendidos2'))),
                 nvar=_num_csv(col(row,'nvar')),
                 titulo=((row[idx[_tit]].strip() if (_tit and idx[_tit]<len(row)) else '')))
        for e in col(row,'ean').split(','):
            e=norm(e)
            if e: data.setdefault(e,[]).append(rec)   # LISTA de candidatos (un EAN puede tener varias fichas)
    return data
