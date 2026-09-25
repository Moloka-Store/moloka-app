# -*- coding: utf-8 -*-
"""ESCANER 2 · LO HEREDADO DEL DIRECTOR DE HEO (director_heo_prep.py), COPIADO LITERALMENTE.

Encargo B7 (25-sep-2026). El filtro del modo «marcas»: las marcas de la regla y `_quiere`, texto
EXACTO del commit 2f9c06a (blob 6a65a16912), generado por script. No se importa: escaner2_motor.py lo saca por
nombre con la regla (`regla`) en su espacio de nombres, como antes hacia con el director.
🔴 NO SE TOCA A MANO: si el director cambia, test_escaner2_heredado.py lo avisa y decide Fernando.
"""


# ── ORIGEN: director_heo_prep.py, líneas 38-38 · commit 2f9c06a · blob 6a65a16912 · md5 88821ec959c756f88f2e33504436d5e3 ──
marcas = regla.get('marcas') or ['Funko']


# ── ORIGEN: director_heo_prep.py, líneas 39-39 · commit 2f9c06a · blob 6a65a16912 · md5 19d7f6bb128f412024a7a229fe728a43 ──
quiere_ofertas = any(str(m).strip().upper() == 'OFERTAS' for m in marcas)


# ── ORIGEN: director_heo_prep.py, líneas 40-40 · commit 2f9c06a · blob 6a65a16912 · md5 5db300c3e11fcfab3fb389ef2761cbfe ──
marcas_reales = [str(m).strip() for m in marcas if str(m).strip().upper() != 'OFERTAS']


# ── ORIGEN: director_heo_prep.py, líneas 41-41 · commit 2f9c06a · blob 6a65a16912 · md5 d66f125750c7feb6cc7c6e1a528dd249 ──
rank_max = regla.get('rank_maximo', 30000)


# ── ORIGEN: director_heo_prep.py, líneas 84-93 · commit 2f9c06a · blob 6a65a16912 · md5 b87cc44d4807dc6546512dfe71d02b38 ──
# 3) Pre-filtrar: servible + (marca en la lista  O  oferta si se pidio)
def _quiere(f):
    if f.get('estado') != 'disponible':
        return False
    m = (f.get('marca') or '').lower()
    if any(mr.lower() in m for mr in marcas_reales):
        return True
    if quiere_ofertas and f.get('en_oferta') == 'SI':
        return True
    return False
