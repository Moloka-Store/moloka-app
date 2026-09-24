# -*- coding: utf-8 -*-
"""Banco de la FORMULA del escaner 2: recalcula filas REALES de `escaner_detalle` con
`calc_rentabilidad` sacada del escaner viejo (la MISMA que usa el escaner nuevo) y exige el
mismo beneficio y el mismo margen AL CENTIMO, y la MISMA decision.

🔴 LAS FILAS REALES NO VIVEN EN ESTE REPO, Y ES A PROPOSITO. Este repo es PUBLICO y
   `escaner_detalle` lleva el precio de COSTE de las compras de Moloka (por eso `anon` esta
   revocada de esa tabla). Asi que el banco tiene dos partes:
     · SIEMPRE (tambien en el CI): el cotejador se prueba contra filas FABRICADAS con la propia
       formula, y contra una fila MALA que tiene que cazar. Sin esto, un cotejador roto diria
       «todo cuadra» con las filas reales igual que con cualquier cosa.
     · CON FILAS REALES: si la variable ESCANER2_FILAS_REALES apunta a un JSON con las filas
       (sacadas con el conector de SOLO LECTURA, ver la consulta de abajo), se cotejan TODAS.
       El resultado de la corrida del 24-sep-2026 esta en el INFORME.md de la v2.

LA CONSULTA (MOLOKA-PROD-LECTURA, solo SELECT), sin nombres ni EAN, solo lo que la cuenta usa:
    select id, procesado_at, pais, pa, precio_venta, ref_pct, fee_fba, iva, almacen,
           com_digitales, beneficio, margen, decision
      from escaner_detalle where ejecucion like 'mis_compras%' order by id;

🔑 QUE CUENTA SE USO EN CADA FILA, POR FECHA Y NO PROBANDO LAS DOS. Hasta el #174 (commit
   f8ab0b7, en `main` el 28-ago-2026 a las 08:57 de Madrid) el escaner calculaba con la cuenta
   historica (`isd` omitido: el x1,03 plano); desde entonces, con `isd=ISD_PAIS[pais]`. Las dos
   solo se separan en Francia (alli el recargo cae tambien sobre la tarifa FBA). Probar las dos
   y quedarse con la que cuadre seria un banco que no puede fallar.
"""
import json
import os
import sys
from datetime import datetime, timezone

import escaner2_motor as e2

FECHA_ISD = datetime(2026, 8, 28, 6, 57, 14, tzinfo=timezone.utc)
CENTIMO = 0.005

M = e2.cargar_motor()
fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK ' if ok else 'XX ') + nombre + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


def _f(x):
    return None if x is None else float(x)


def _fecha(s):
    return datetime.fromisoformat(str(s).replace('Z', '+00:00').replace(' ', 'T'))


def cotejar(fila):
    """None si la fila cuadra; si no, el porque. Misma condicion para calcular que la Celda 8."""
    precio, pa, ref, fee = _f(fila['precio_venta']), _f(fila['pa']), _f(fila['ref_pct']), _f(fila['fee_fba'])
    if not (precio and pa and ref is not None and fee is not None):
        if fila['beneficio'] is not None or fila['decision'] != 'Sin datos':
            return 'faltan datos y la fila trae beneficio o una decision que no es Sin datos'
        return None
    extra = {'isd': M.ISD_PAIS[fila['pais']]} if _fecha(fila['procesado_at']) >= FECHA_ISD else {}
    r = M.calc_rentabilidad(precio, pa, ref, fee, _f(fila['iva']), almacen=_f(fila['almacen']),
                            com_digitales=_f(fila['com_digitales']), **extra)
    if fila['beneficio'] is None or abs(r['beneficio'] - _f(fila['beneficio'])) >= CENTIMO:
        return 'beneficio %r frente a %r' % (r['beneficio'], fila['beneficio'])
    if fila['margen'] is None or abs(r['margen'] - _f(fila['margen'])) >= CENTIMO / 100:
        return 'margen %r frente a %r' % (r['margen'], fila['margen'])
    if M.decision_de(r['margen']) != fila['decision']:
        return 'decision %s frente a %s' % (M.decision_de(r['margen']), fila['decision'])
    return None


# ── 1 · el cotejador, contra filas fabricadas (corre SIEMPRE) ───────────────────────────
def fabricada(pais, cuando, precio=24.99, pa=8.12, ref=15.0, fee=5.29, iva=0.21, isd=True):
    r = M.calc_rentabilidad(precio, pa, ref, fee, iva, almacen=M.ALMACEN, com_digitales=M.COM_DIGITALES,
                            **({'isd': M.ISD_PAIS[pais]} if isd else {}))
    return {'id': 0, 'procesado_at': cuando, 'pais': pais, 'pa': pa, 'precio_venta': precio, 'ref_pct': ref,
            'fee_fba': fee, 'iva': iva, 'almacen': M.ALMACEN, 'com_digitales': M.COM_DIGITALES,
            'beneficio': r['beneficio'], 'margen': r['margen'], 'decision': M.decision_de(r['margen'])}


print('1 · el cotejador, con filas fabricadas')
eq('1 · FR antes del #174 (cuenta historica) cuadra', cotejar(fabricada('FR', '2026-08-20T10:00:00+00:00', isd=False)), None)
eq('1 · FR despues del #174 (ISD sobre comision + FBA) cuadra', cotejar(fabricada('FR', '2026-09-08T10:00:00+00:00')), None)
eq('1 · 🔴 FR despues del #174 guardada con la cuenta VIEJA → la caza',
   cotejar(fabricada('FR', '2026-09-08T10:00:00+00:00', isd=False)) is not None, True)
_mala = fabricada('ES', '2026-09-08T10:00:00+00:00')
_mala['beneficio'] += 0.01
eq('1 · 🔴 un centimo de diferencia en el beneficio → la caza', cotejar(_mala) is not None, True)
_mala = fabricada('ES', '2026-09-08T10:00:00+00:00')
_mala['decision'] = 'VALORAR' if _mala['decision'] != 'VALORAR' else 'COMPRAR'
eq('1 · 🔴 la misma cuenta con otra decision → la caza', cotejar(_mala) is not None, True)
_sin = dict(fabricada('DE', '2026-09-08T10:00:00+00:00'), fee_fba=None, beneficio=None, margen=None, decision='Sin datos')
eq('1 · sin tarifa FBA: Sin datos y sin beneficio, cuadra', cotejar(_sin), None)

# ── 2 · las filas REALES, si se le pasan ────────────────────────────────────────────────
ruta = os.environ.get('ESCANER2_FILAS_REALES', '').strip()
print()
if not ruta:
    print('2 · FILAS REALES: no cargadas en esta corrida (el repo es publico y llevan precio de '
          'coste). Se corren con ESCANER2_FILAS_REALES=<json>; ver la cabecera de este fichero.')
else:
    with open(ruta, encoding='utf-8') as fh:
        filas = json.load(fh)
    malas = [(f['id'], m) for f in filas for m in [cotejar(f)] if m]
    calculadas = sum(1 for f in filas if f['beneficio'] is not None)
    por_pais = {}
    for f in filas:
        por_pais[f['pais']] = por_pais.get(f['pais'], 0) + 1
    print('2 · FILAS REALES: %d filas (%d con cuenta, %d «Sin datos») · por pais %s'
          % (len(filas), calculadas, len(filas) - calculadas, dict(sorted(por_pais.items()))))
    eq('2 · hay filas reales que cotejar, no cero', len(filas) > 0, True)
    for i, m in malas[:20]:
        print('   XX fila %s: %s' % (i, m))
    eq('2 · 🔴 TODAS las filas reales: mismo beneficio y margen al centimo y misma decision', len(malas), 0)

print()
if fallos:
    print('ROJO: %d comprobaciones fallan: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('VERDE: la formula que usa el escaner 2 es la del viejo y reproduce sus filas.')
