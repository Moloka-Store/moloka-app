# -*- coding: utf-8 -*-
# Prueba EJECUTABLE de la verificación de la subida del Excel (encargo AH, 2-oct-2026).
#   python test_verificar_subida.py
#
# El caso: el 30-sep-2026 12:04 UTC el escáner viejo subió el Excel de TCG, el log dijo
# «verificado: False» y la fila id=1688 de escaner_resultados quedó con `fichero` NULL. La
# verificación listaba `resultados/` entero con `.list(carpeta)` a secas, y storage3 2.31.0
# devuelve por defecto las 100 primeras entradas por nombre: TCG va el último del alfabeto.
#
# 🔴 EL DOBLE ES FIEL AL SDK Y AL SERVIDOR, y por eso el test PUEDE ponerse rojo:
#    · mezcla las opciones con DEFAULT_SEARCH_OPTIONS (limit 100, offset 0, name asc), como
#      `storage3._sync.file_api.list` en la 2.31.0;
#    · `search` filtra como storage.search en producción (leído el 2-oct-2026):
#      `name ILIKE carpeta/ || search || '%'` — prefijo, sin mayúsculas, y `_` es COMODÍN.
#    Si la verificación volviera a `.list(CARPETA_RESULTADOS)` a secas, el doble devolvería
#    las 100 primeras y el caso del encargo saldría rojo solo.
# 🔴 Y SE EJECUTA EL CÓDIGO DE VERDAD: el bloque de subida de cada script se saca con `ast`
#    de moloka_escaner_nube.py y moloka_escaner_pro_nube.py y se ejecuta contra el doble. No
#    se comprueba que «esté escrito fichero_en_storage»: se comprueba qué `subido_ok` sale.
import ast
import os
import re
import tempfile
import textwrap

import verificar_subida as vs

fallos = 0


def chk(nombre, ok):
    global fallos
    print(('OK  ' if ok else 'XX  ') + nombre)
    if not ok:
        fallos += 1


# storage3 2.31.0, `storage3.constants.DEFAULT_SEARCH_OPTIONS`.
DEFECTOS_SDK = {'limit': 100, 'offset': 0, 'sortBy': {'column': 'name', 'order': 'asc'}}

OBJETIVO = 'Escaneo_TCG_Funko_20260930_1204.xlsx'


def _ilike_prefijo(patron):
    """`ILIKE patron || '%'` de Postgres como regex: % = cualquier cosa, _ = un carácter."""
    trozos = []
    for c in patron:
        trozos.append('.*' if c == '%' else '.' if c == '_' else re.escape(c))
    return re.compile(''.join(trozos), re.IGNORECASE | re.DOTALL)


class Balde:
    """El `.from_(bucket)` del SDK. Guarda rutas completas ('resultados/x.xlsx') y lista
    como el servidor: un nivel, filtrado por prefijo+search, ordenado y cortado."""

    def __init__(self, rutas, ocultar_en=(), fallar_en=()):
        self.rutas = set(rutas)
        self.llamadas = []                 # opciones CRUDAS de cada .list
        self.ocultar_en = set(ocultar_en)  # nº de llamada (1, 2…) en que el objetivo no se ve
        self.fallar_en = set(fallar_en)    # nº de llamada en que el .list lanza
        self.subidas = []

    def upload(self, ruta, contenido, opciones=None):
        self.subidas.append(ruta)
        self.rutas.add(ruta)
        return {'Key': ruta}

    def list(self, path=None, options=None):
        self.llamadas.append(dict(options or {}))
        n = len(self.llamadas)
        if n in self.fallar_en:
            raise RuntimeError('StorageApiError 500 (doble)')
        o = {**DEFECTOS_SDK, **(options or {})}
        carpeta = (path or '').rstrip('/') + '/'
        patron = _ilike_prefijo(carpeta + o.get('search', ''))
        nombres = sorted(r[len(carpeta):] for r in self.rutas
                         if r.startswith(carpeta) and '/' not in r[len(carpeta):] and patron.match(r))
        if n in self.ocultar_en:
            nombres = [x for x in nombres if x != OBJETIVO]
        nombres = sorted(nombres, key=lambda x: x, reverse=(o['sortBy'].get('order') == 'desc'))
        return [{'name': x, 'id': f'id-{x}'} for x in nombres[o['offset']:o['offset'] + o['limit']]]


class Sb:
    def __init__(self, balde):
        self.storage = self
        self._balde = balde

    def from_(self, bucket):
        self.bucket = bucket
        return self._balde


def resultados_reales(n_delante, n_detras=3):
    """`resultados/` con nombres de la forma real: los de DBLINE/OCIOSTOCK/PRO/MIS_COMPRAS
    y los TCG de días anteriores van DELANTE del objetivo; los TCG posteriores, detrás."""
    delante = []
    prefijos = ['Escaneo_DBLINE_Funko', 'Escaneo_MIS_COMPRAS_TODAS', 'Escaneo_OCIOSTOCK_Seleccion',
                'Escaneo_PRO_OSMA_Funko', 'Escaneo_TCG_Funko']
    i = 0
    while len(delante) < n_delante:
        p = prefijos[i % len(prefijos)]
        delante.append(f'resultados/{p}_202607{(i // 50) + 10:02d}_{i % 50:04d}.xlsx')
        i += 1
    detras = [f'resultados/Escaneo_TCG_Funko_2026100{k + 1}_1002.xlsx' for k in range(n_detras)]
    return delante + detras


def vieja(sb, bucket, carpeta, nombre):
    """La verificación de ANTES, copiada literal de moloka_escaner_nube.py (main 18fa3b6, l.2359)."""
    _res = sb.storage.from_(bucket).list(carpeta) or []
    return any(o.get('name') == nombre for o in _res)


class Reloj:
    def __init__(self):
        self.esperas = []

    def __call__(self, s):
        self.esperas.append(s)


def silencio(*a, **k):
    pass


# ---------------------------------------------------------------------------
# 0) El doble es fiel: sin opciones corta en 100, y el objetivo (TCG, al final del
#    alfabeto) queda FUERA. Si esto no se cumple, el resto no prueba nada.
# ---------------------------------------------------------------------------
b0 = Balde(resultados_reales(150) + ['resultados/' + OBJETIVO])
l0 = b0.list('resultados')
chk('doble fiel: .list(carpeta) a secas devuelve 100 de 154', len(l0) == 100)
chk('  · y el Excel de TCG no está entre esos 100', OBJETIVO not in [o['name'] for o in l0])
chk('doble fiel: search es prefijo ILIKE (mayúsculas da igual)',
    [o['name'] for o in b0.list('resultados', {'search': OBJETIVO.upper()})] == [OBJETIVO])

# ---------------------------------------------------------------------------
# 1) EL CASO DEL ENCARGO: 150 por delante. La vieja dice False, la nueva True.
# ---------------------------------------------------------------------------
b1 = Balde(resultados_reales(150) + ['resultados/' + OBJETIVO])
chk('150 por delante: la verificación VIEJA da False (el falso «no» del 30-sep)',
    vieja(Sb(b1), 'informes', 'resultados', OBJETIVO) is False)
b1 = Balde(resultados_reales(150) + ['resultados/' + OBJETIVO])
r1 = Reloj()
chk('150 por delante: la verificación NUEVA da True',
    vs.fichero_en_storage(Sb(b1), 'informes', 'resultados', OBJETIVO, dormir=r1, imprimir=silencio) is True)
chk('  · a la primera: una sola llamada y ninguna espera', len(b1.llamadas) == 1 and r1.esperas == [])
chk('  · pasa search = el nombre EXACTO (lo que antes no existía)',
    b1.llamadas[0].get('search') == OBJETIVO)

# ---------------------------------------------------------------------------
# 2) Callada cuando no toca: con pocos ficheros las dos dicen True.
# ---------------------------------------------------------------------------
b2 = Balde(resultados_reales(10) + ['resultados/' + OBJETIVO])
chk('10 por delante: la vieja da True', vieja(Sb(b2), 'informes', 'resultados', OBJETIVO) is True)
chk('10 por delante: la nueva da True',
    vs.fichero_en_storage(Sb(b2), 'informes', 'resultados', OBJETIVO, dormir=Reloj(), imprimir=silencio))

# ---------------------------------------------------------------------------
# 3) Si de verdad NO está: False, tras mirar DOS veces con UNA espera de 1-2 s.
# ---------------------------------------------------------------------------
b3 = Balde(resultados_reales(150))
r3 = Reloj()
chk('no subido: da False',
    vs.fichero_en_storage(Sb(b3), 'informes', 'resultados', OBJETIVO, dormir=r3, imprimir=silencio) is False)
chk('  · miró 2 veces y esperó 1 vez', len(b3.llamadas) == 2 and len(r3.esperas) == 1)
chk('  · la espera está entre 1 y 2 s', len(r3.esperas) == 1 and 1 <= r3.esperas[0] <= 2)

# ---------------------------------------------------------------------------
# 4) El reintento: no se ve a la primera, sí a la segunda -> True.
# ---------------------------------------------------------------------------
b4 = Balde(resultados_reales(5) + ['resultados/' + OBJETIVO], ocultar_en={1})
r4 = Reloj()
chk('no se ve a la primera y sí a la segunda: True',
    vs.fichero_en_storage(Sb(b4), 'informes', 'resultados', OBJETIVO, dormir=r4, imprimir=silencio) is True)
chk('  · tras una espera', len(r4.esperas) == 1 and len(b4.llamadas) == 2)

# ---------------------------------------------------------------------------
# 5) La mirada que FALLA no es un «no está» a la primera, y nunca sale como excepción.
# ---------------------------------------------------------------------------
b5 = Balde(['resultados/' + OBJETIVO], fallar_en={1})
chk('el .list lanza a la primera y responde a la segunda: True',
    vs.fichero_en_storage(Sb(b5), 'informes', 'resultados', OBJETIVO, dormir=Reloj(), imprimir=silencio) is True)
b5b = Balde(['resultados/' + OBJETIVO], fallar_en={1, 2})
try:
    r5b = vs.fichero_en_storage(Sb(b5b), 'informes', 'resultados', OBJETIVO, dormir=Reloj(), imprimir=silencio)
    chk('el .list lanza las dos veces: False, sin excepción', r5b is False)
except Exception as ex:
    chk(f'el .list lanza las dos veces: False, sin excepción (lanzó {ex!r})', False)

# ---------------------------------------------------------------------------
# 6) Igualdad EXACTA: `_` es comodín en ILIKE; un vecino que «empieza igual» no vale.
# ---------------------------------------------------------------------------
vecino = OBJETIVO.replace('Escaneo_TCG', 'Escaneo-TCG')
b6 = Balde(['resultados/' + vecino, 'resultados/' + OBJETIVO + '.bak'])
chk('el doble devuelve los vecinos al buscar (el comodín muerde)',
    len(b6.list('resultados', {'search': OBJETIVO})) == 2)
b6.llamadas.clear()
chk('solo vecinos (otro carácter en el «_», y un .bak): False',
    vs.fichero_en_storage(Sb(b6), 'informes', 'resultados', OBJETIVO, dormir=Reloj(), imprimir=silencio) is False)


# ---------------------------------------------------------------------------
# 7) EL CÓDIGO DE VERDAD de los dos escáneres, ejecutado contra el doble.
# ---------------------------------------------------------------------------
AQUI = os.path.dirname(os.path.abspath(__file__))


def fuente(fichero):
    with open(os.path.join(AQUI, fichero), encoding='utf-8') as f:
        return f.read()


def segmento(src, nodo):
    """El texto del nodo, con su sangría quitada para poder ejecutarlo suelto."""
    return textwrap.dedent(' ' * nodo.col_offset + ast.get_source_segment(src, nodo))


def asigna_subido_ok(nodo):
    return any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'subido_ok'
                                                 for t in n.targets)
               and isinstance(n.value, ast.Call) for n in ast.walk(nodo))


def importa_la_funcion(arbol):
    return any(isinstance(n, ast.ImportFrom) and n.module == 'verificar_subida'
               and any(a.name == 'fichero_en_storage' for a in n.names) for n in arbol.body)


def ejecutar_bloque(codigo, extra, balde):
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as t:
        t.write(b'PK excel de prueba')
    ns = {'sb': Sb(balde), 'BUCKET': 'informes', 'CARPETA_RESULTADOS': 'resultados',
          'subido_ok': False, 'print': silencio,
          'fichero_en_storage': lambda *a, **k: vs.fichero_en_storage(*a, dormir=Reloj(), imprimir=silencio, **k)}
    ns.update(extra(t.name))
    try:
        exec(compile(codigo, '<bloque>', 'exec'), ns)
    finally:
        os.unlink(t.name)
    return ns


# 7a) El viejo: el `if not _sin_excel:` de nivel de módulo que sube y verifica.
src_v = fuente('moloka_escaner_nube.py')
arbol_v = ast.parse(src_v)
bloques_v = [n for n in arbol_v.body if isinstance(n, ast.If) and asigna_subido_ok(n)]
chk('viejo: hay UN bloque de módulo que asigna subido_ok', len(bloques_v) == 1)
chk('viejo: importa fichero_en_storage de verificar_subida', importa_la_funcion(arbol_v))
if len(bloques_v) == 1:
    bv = Balde(resultados_reales(150))
    ns = ejecutar_bloque(segmento(src_v, bloques_v[0]),
                         lambda tmp: {'_sin_excel': False, 'ARCHIVO_SALIDA': tmp, 'nombre_xlsx': OBJETIVO,
                                      'ruta_storage': 'resultados/' + OBJETIVO}, bv)
    chk('viejo, 150 por delante: el bloque REAL sube y deja subido_ok True',
        bv.subidas == ['resultados/' + OBJETIVO] and ns['subido_ok'] is True)
    bv2 = Balde(resultados_reales(150))
    bv2.upload = lambda ruta, contenido, opciones=None: {'Key': ruta}   # dice OK y no deja nada
    ns2 = ejecutar_bloque(segmento(src_v, bloques_v[0]),
                          lambda tmp: {'_sin_excel': False, 'ARCHIVO_SALIDA': tmp, 'nombre_xlsx': OBJETIVO,
                                       'ruta_storage': 'resultados/' + OBJETIVO}, bv2)
    chk('viejo: si el fichero NO llegó, el bloque REAL deja subido_ok False', ns2['subido_ok'] is False)

# 7b) El Pro: el `try` de main() que sube y verifica.
src_p = fuente('moloka_escaner_pro_nube.py')
arbol_p = ast.parse(src_p)
main_p = [n for n in arbol_p.body if isinstance(n, ast.FunctionDef) and n.name == 'main']
bloques_p = [n for n in ast.walk(main_p[0]) if isinstance(n, ast.Try) and asigna_subido_ok(n)] if main_p else []
chk('pro: hay UN try en main() que asigna subido_ok', len(bloques_p) == 1)
chk('pro: importa fichero_en_storage de verificar_subida', importa_la_funcion(arbol_p))
if len(bloques_p) == 1:
    nombre_pro = 'Escaneo_PRO_TCG_Funko_20260930_1204.xlsx'
    bp = Balde(resultados_reales(150) + [f'resultados/Escaneo_TCG_Funko_202609{d:02d}_1204.xlsx'
                                         for d in range(1, 30)])
    ns = ejecutar_bloque(segmento(src_p, bloques_p[0]),
                         lambda tmp: {'out': tmp, 'nombre': nombre_pro,
                                      'ruta_storage': 'resultados/' + nombre_pro}, bp)
    chk('pro, 179 en la carpeta y el suyo fuera de los 100 primeros: subido_ok True',
        nombre_pro not in [o['name'] for o in Balde(bp.rutas).list('resultados')]
        and ns['subido_ok'] is True)

# 7c) Ningún sitio de los dos escáneres vuelve a verificar listando resultados/ a secas.
for fichero, arbol in (('moloka_escaner_nube.py', arbol_v), ('moloka_escaner_pro_nube.py', arbol_p)):
    a_secas = [n.lineno for n in ast.walk(arbol) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute) and n.func.attr == 'list'
               and len(n.args) == 1 and not n.keywords
               and isinstance(n.args[0], ast.Name) and n.args[0].id == 'CARPETA_RESULTADOS']
    chk(f'{fichero}: ningún .list(CARPETA_RESULTADOS) a secas (líneas: {a_secas})', a_secas == [])

print()
print('TODO OK' if not fallos else f'{fallos} FALLO(S)')
raise SystemExit(1 if fallos else 0)
