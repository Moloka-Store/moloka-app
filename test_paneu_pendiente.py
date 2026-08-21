# -*- coding: utf-8 -*-
"""MESA DE PRUEBAS · «pendiente de evaluar» contra «fichero corrupto».

Qué prueba y qué NO:
  · SÍ: que una fila con los DIEZ países en blanco se SALTA (y se marca), y que una con
        entre uno y nueve sigue ABORTANDO. Las dos direcciones, que es lo que hace que la
        distinción signifique algo.
  · SÍ: que la Guarda 8 (la aritmética de filas) sigue cuadrando con las pendientes fuera.
  · NO: la carga real. Eso sale de correr el procesador contra el fichero de verdad en
        Actions. Aquí sólo se ejercitan las guardas.

🔴 EL CASO QUE LE DA NOMBRE: `B0CQDG7Y94`, el Llavero Pocket POP Deadpool & Wolverine, de
   la factura de OcioStock 26-17346-S1 que entró el 19-ago-2026. El informe del 20-ago pasó
   de 384 a 400 filas —esas 16 son esa caja— y la fila venía con 4 de 30 celdas rellenas.
   La carga entera abortó por ella y dejó `paneu_aptos` cinco días sin actualizar.

🔬 Y NO ES UN CASO AISLADO NI UNA RAREZA: medido sobre los ONCE ficheros del buzón
   (16-jul → 20-ago), diez traen todas las celdas legibles y el único con problema es éste.
   Cero casos de celdas sueltas ilegibles en trece meses — o sea que el caso que la Guarda 5
   estaba cazando aquí no era corrupción: era mercancía nueva, que entra todas las semanas.
"""
import os, sys

RUTA = os.environ.get('PROC') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'procesador_paneu_aptos.py')
sys.path.insert(0, os.path.dirname(RUTA))
import procesador_paneu_aptos as P

PAISES = list(P.MAPA_PAIS.keys())
COLS_SKU = ['MerchantSKU', 'ASIN', 'FnSKU', 'Title', 'Estado de PanEU', 'Registrarse',
            'Enrollment Date', 'Fecha en que caduca PanEU', 'Última actividad el',
            'Comentarios del producto']


def fichero(filas_paises, skus=None):
    """Arma un TSV con la cabecera real del informe. `filas_paises` es una lista: por cada
    fila, un dict país → celda literal."""
    cab = COLS_SKU[:]
    for pais, (col_estado, col_benef) in P.MAPA_PAIS.items():
        cab += [col_estado, col_benef]
    lineas = ['\t'.join(cab)]
    for i, celdas in enumerate(filas_paises):
        sku = (skus[i] if skus else f'SKU-{i}')
        fila = [sku, f'ASIN{i}', f'X0{i}', f'Producto {i}', 'Válido', 'Y', '', '', '', '']
        for pais in PAISES:
            fila += [celdas.get(pais, '€ 19,99'), 'Y']
        lineas.append('\t'.join(fila))
    return '\n'.join(lineas) + '\n'


fallos = 0


def eq(nombre, got, exp):
    global fallos
    ok = got == exp
    if not ok:
        fallos += 1
    print(('OK  ' if ok else 'XX  ') + nombre + ('' if ok else '  got=%r exp=%r' % (got, exp)))


def analizar_ok(nombre, texto):
    """Parsea esperando que NO aborte. 🔒 Existe para que una regresión salga como un XX
    CON NOMBRE en vez de matar el script con un traceback: un test que muere a la primera
    deja sin correr todo lo que viene detrás, y quien lee la salida ve una excepción en
    vez de saber QUÉ dejó de cumplirse. 🔬 Medido: al romper el descuento de la Guarda 8,
    el script moría en el bloque 1 y el fallo real (bloque 3) no llegaba a evaluarse."""
    global fallos
    try:
        return P.analizar(texto, 'test.txt', '2026-08-20')
    except P.Aborta as e:
        fallos += 1
        print(f'XX  {nombre} ABORTÓ sin deber: {e}')
        return {'aptos': [], 'ofertas': [], 'pendientes': []}


print('-- paneu: sin evaluar (0/10) contra corrupto (1..9/10) --')

# ── 1) 🔴 CERO DE DIEZ · se salta, se marca y NO aborta ─────────────────────
vacia = {p: '' for p in PAISES}
info = analizar_ok('(1) los diez en blanco',
                   fichero([{}, vacia, {}], skus=['A', 'B0CQDG7Y94', 'C']))
eq('(1) 🔴 con los diez países en blanco NO aborta', True, True)
eq('(1) las tres filas entran en aptos', len(info['aptos']), 3)
eq('(1) 🔴 … y la del medio va marcada', info['aptos'][1]['pendiente_evaluacion'], True)
eq('(1) 🔒 … y las otras dos NO',
   [info['aptos'][0]['pendiente_evaluacion'], info['aptos'][2]['pendiente_evaluacion']],
   [False, False])
# 🔴 SIN filas de oferta: no se inventa un estado que Amazon no ha dado.
eq('(1) 🔴 la pendiente no genera filas de oferta',
   len(info['ofertas']), 2 * len(PAISES))
eq('(1) 🔒 … y ninguna oferta lleva su SKU',
   any(o['seller_sku'] == 'B0CQDG7Y94' for o in info['ofertas']), False)
# 🔑 Y queda dicho POR SU NOMBRE, para el log.
eq('(1) 🔒 se recoge con su SKU para gritarlo',
   any('B0CQDG7Y94' in p for p in info['pendientes']), True)

# ── 2) 🔴 LA OTRA DIRECCIÓN · entre uno y nueve SIGUE ABORTANDO ────────────
# Es la mitad que da sentido a la distinción. Si esto pasara, habríamos cambiado una
# guarda que protege por una que perdona.
for n_vacios in (1, 5, len(PAISES) - 1):
    celdas = {p: '' for p in PAISES[:n_vacios]}
    try:
        P.analizar(fichero([celdas]), 'test.txt', '2026-08-20')
        eq(f'(2) con {n_vacios}/{len(PAISES)} vacíos tenía que abortar', 'no abortó', 'Aborta')
    except P.Aborta as e:
        eq(f'(2) 🔴 con {n_vacios}/{len(PAISES)} vacíos ABORTA', '[Guarda 5]' in str(e), True)
        # 🔑 Y el mensaje dice cuántos son, que es lo que separa los dos casos.
        eq(f'(2) 🔒 … y el mensaje dice {n_vacios} de {len(PAISES)}',
           f'{n_vacios} de {len(PAISES)}' in str(e), True)

# ── 3) 🔒 LA ARITMÉTICA DE LA GUARDA 8 SIGUE CUADRANDO ─────────────────────
# Con las pendientes descontadas. Si se hubiera relajado la guarda en vez de ajustarla,
# se habría perdido la red que caza una fila a medio escribir.
info2 = analizar_ok('(3) la aritmética de la Guarda 8',
                    fichero([vacia, vacia, {}, {}, {}]))
eq('(3) 🔒 5 filas, 2 sin evaluar', [len(info2['aptos']), len(info2['pendientes'])], [5, 2])
eq('(3) 🔒 … y las ofertas son 3 × países', len(info2['ofertas']), 3 * len(PAISES))

# ── 4) 🔒 UN FICHERO NORMAL NO CAMBIA EN NADA ──────────────────────────────
# La mitad que se olvida: que la guarda esté CALLADA cuando no toca.
info3 = analizar_ok('(4) un fichero normal', fichero([{}, {}, {}]))
eq('(4) 🔒 sin pendientes, la lista va vacía', info3['pendientes'], [])
eq('(4) 🔒 … y todas las filas dan sus diez países',
   len(info3['ofertas']), 3 * len(PAISES))
eq('(4) 🔒 … y ninguna va marcada',
   any(a['pendiente_evaluacion'] for a in info3['aptos']), False)

# ── 5) 🔒 UN BLANCO NO ES LO MISMO QUE UN TEXTO RARO ───────────────────────
# 'Material peligroso' es un motivo de bloqueo LEGÍTIMO y cuenta como legible. Si esto
# se contara como vacío, un producto bloqueado en los diez países se marcaría como «sin
# evaluar» — y son cosas opuestas: una es que Amazon no ha hablado, la otra que ha dicho
# que no. 🔬 El Kukident está bloqueado en los cuatro nuestros.
bloqueada = {p: 'Material peligroso' for p in PAISES}
info4 = analizar_ok('(5) bloqueada en los diez', fichero([bloqueada]))
eq('(5) 🔴 bloqueada en los diez NO es «sin evaluar»', info4['pendientes'], [])
eq('(5) 🔒 … y sí genera sus diez filas de oferta', len(info4['ofertas']), len(PAISES))

print('\n' + ('TODO OK' if fallos == 0 else '%d FALLOS' % fallos))
sys.exit(0 if fallos == 0 else 1)
