# -*- coding: utf-8 -*-
"""MESA DE PRUEBAS de la guarda 6.14 — NO es el procesador, y no prueba sus cifras.

Qué prueba y qué NO:
  · SÍ: que las SIETE ramas del bloque se ejecutan sin reventar y dicen lo que dicen.
        Ejecuta el TEXTO REAL del bloque, extraído del .py por anclas — no una copia
        retecleada, que es la trampa clásica de este tipo de banco.
  · NO: los números. Esos salen de correr el procesador contra los ficheros REALES en
        Actions. Datos sintéticos no prueban nada (§3 de CLAUDE.md); aquí solo se hace
        saltar cada guarda a propósito.
"""
import io, os, sys, textwrap
from datetime import datetime, timezone, timedelta

RUTA = os.environ.get('PROC') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'procesador_custom_analytics.py')

os.environ.setdefault('PAIS', 'ES')
sys.path.insert(0, os.path.dirname(RUTA))
import procesador_custom_analytics as P

texto = io.open(RUTA, encoding='utf-8').read().split('\n')
ini = [i for i, l in enumerate(texto) if l.startswith('    # --- Guarda 6.14: EL CONTADOR')][0]
fin = [i for i, l in enumerate(texto) if l.startswith('    # --- Carga PELÍCULA: DELETE')][0]
BLOQUE = textwrap.dedent('\n'.join(texto[ini:fin]))
CODIGO = compile(BLOQUE, '<guarda_6.14>', 'exec')
print(f"Bloque extraído del fichero real: líneas {ini+1}..{fin}  "
      f"({BLOQUE.count(chr(10))} líneas)\n")

COLS = P.COLS_ACUMULADAS
AHORA = datetime(2026, 8, 7, 18, 3, 29, 812000, tzinfo=timezone.utc)


class CurFalso:
    def __init__(self, filas): self.filas = filas
    def execute(self, *a, **k): pass
    def fetchall(self): return self.filas
    def close(self): pass


class ConFalso:
    def rollback(self): pass
    def close(self): pass


def fila(asin, base, factor=1.0, cambios=None):
    r = {'asin': asin}
    for j, c in enumerate(COLS):
        v = (base + j * 7) * factor
        r[c] = int(round(v)) if c in P.COLS_ENTERAS else round(v, 2)
    for c, v in (cambios or {}).items():
        r[c] = v
    return r


def corre(nombre, datos, previo_filas, ref_cual, forzar=False, leido=AHORA):
    P.FORZAR = forzar
    ns = dict(P.__dict__)
    ns.update({'datos': datos, 'ref_cual': ref_cual, 'leido_at': leido,
               'PAIS': 'ES', 'fichero': 'FICHERO_DE_PRUEBA.xlsx',
               'cur': CurFalso(previo_filas), 'con': ConFalso()})
    print("=" * 78)
    print(f"ESCENARIO: {nombre}")
    print("=" * 78)
    try:
        exec(CODIGO, ns)
        print("\n>>> RESULTADO: SIGUE (la carga entraría)\n")
        return 'CARGA'
    except SystemExit as e:
        print(f"\n>>> RESULTADO: ABORTA (exit {e.code})\n")
        return 'ABORTA'


def previo_de(datos_previos):
    return [tuple([r['asin']] + [r[c] for c in COLS]) for r in datos_previos]


res = {}

# A · CARGA LIMPIA: 321 ASIN, todo sube. Esperado: CARGA con ✅ y 0 bajadas.
ant = [fila(f"A{i:08d}", 100 + i) for i in range(321)]
nue = [fila(f"A{i:08d}", 100 + i, factor=1.10) for i in range(321)]
res['A limpia'] = corre("A · CARGA LIMPIA (321 ASIN, 0 bajadas)",
                        nue, previo_de(ant), AHORA - timedelta(days=8))

# B · PUNTUAL: 112 ASIN, una cancelación en uno (9→8 uds, 188,14→168,15 €).
ant = [fila(f"B{i:08d}", 100 + i) for i in range(112)]
ant[7]['unidades_pedidas'], ant[7]['facturacion_pedida_eur'] = 9, 188.14
nue = [fila(f"B{i:08d}", 100 + i, factor=1.10) for i in range(112)]
nue[7]['unidades_pedidas'], nue[7]['facturacion_pedida_eur'] = 8, 168.15
res['B puntual'] = corre("B · RETROCESO PUNTUAL (2 bajadas sobre 1.008 = 0,2%)",
                         nue, previo_de(ant), AHORA - timedelta(days=8))

# C · GLOBAL: 246 ASIN, 1.583 celdas abajo de 2.214, 9/9 totales abajo, 2 negativos.
ant = [fila(f"C{i:08d}", 1000 + i) for i in range(246)]
nue = [fila(f"C{i:08d}", 1000 + i) for i in range(246)]
n = 0
for i in range(246):
    for j, c in enumerate(COLS):
        if (i * 9 + j) % 2214 < 1583:
            nue[i][c] = int(ant[i][c] * 0.01) if c in P.COLS_ENTERAS else round(ant[i][c] * 0.01, 2)
            n += 1
nue[3]['facturacion_pedida_eur'] = -12.90
nue[9]['facturacion_pedida_eur'] = -22.99
print(f"[mesa] escenario C construido con {n} celdas a la baja de {246*9}\n")
res['C global'] = corre("C · RETROCESO GLOBAL (el DISCONTINUO: negativos + 71,5% + 9/9)",
                        nue, previo_de(ant), AHORA - timedelta(days=8))

# D · ZONA GRIS por antigüedad: todo sube, pero la referencia es de hace 98 días.
ant = [fila(f"D{i:08d}", 100 + i) for i in range(321)]
nue = [fila(f"D{i:08d}", 100 + i, factor=1.30) for i in range(321)]
res['D gris'] = corre("D · ZONA GRIS por referencia vieja (98 días > 31), sin forzar",
                      nue, previo_de(ant), AHORA - timedelta(days=98))

# E · La misma D, con forzar = si. Esperado: CARGA gritando que entró forzada.
res['E gris forzada'] = corre("E · ZONA GRIS FORZADA (misma D con forzar = si)",
                              nue, previo_de(ant), AHORA - timedelta(days=98), forzar=True)

# F · ZONA GRIS por pocos comunes: 12 ASIN comunes de 321 (3,7%).
ant = [fila(f"F{i:08d}", 100 + i) for i in range(321)]
nue = [fila(f"F{i:08d}", 100 + i, factor=1.10) for i in range(12)]
res['F gris pocos'] = corre("F · ZONA GRIS por pocos ASIN comunes (12 < 20 y 3,7% < 30%)",
                            nue, previo_de(ant), AHORA - timedelta(days=8))

# G · Sin referencia (primera lectura del país) y con un negativo: criterio 1 solo.
nue = [fila(f"G{i:08d}", 100 + i) for i in range(50)]
nue[4]['reembolsado_eur'] = -3.50
res['G primera+neg'] = corre("G · PRIMERA LECTURA con un negativo (criterio 1 sin referencia)",
                             nue, [], None)

# H · Calderilla: única alarma el criterio 3, con 1 → 0 unidades.
ant = [fila(f"H{i:08d}", 100 + i) for i in range(112)]
ant[5]['unidades_pedidas'] = 1
nue = [fila(f"H{i:08d}", 100 + i, factor=1.10) for i in range(112)]
nue[5]['unidades_pedidas'] = 0
res['H calderilla'] = corre("H · CRITERIO 3 sobre calderilla (1 → 0 unidades)",
                            nue, previo_de(ant), AHORA - timedelta(days=8))

print("=" * 78)
print("RESUMEN (esperado → obtenido)")
print("=" * 78)
esperado = {'A limpia': 'CARGA', 'B puntual': 'CARGA', 'C global': 'ABORTA',
            'D gris': 'ABORTA', 'E gris forzada': 'CARGA', 'F gris pocos': 'ABORTA',
            'G primera+neg': 'ABORTA', 'H calderilla': 'ABORTA'}
mal = 0
for k, v in res.items():
    ok = 'OK ' if esperado[k] == v else 'MAL'
    mal += (ok == 'MAL')
    print(f"  {ok}  {k:<16} esperado {esperado[k]:<7} obtenido {v}")
print(("\nTODAS LAS RAMAS COMO SE ESPERABA" if not mal else f"\n{mal} RAMA(S) MAL"))
sys.exit(1 if mal else 0)
