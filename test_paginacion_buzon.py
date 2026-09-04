# -*- coding: utf-8 -*-
# Prueba EJECUTABLE de que `listar_buzon` PAGINA hasta agotar la carpeta (foto_comun).
# Compilar no es ejecutar: aquí se corre la función de verdad contra un doble de Storage
# que se comporta como storage3 2.31.0.   python test_paginacion_buzon.py
#
# 🔴 EL DOBLE ES FIEL AL SDK A PROPÓSITO, y eso es lo que hace que este test PUEDA
#    PONERSE ROJO. storage3 mezcla las opciones que le pasas con su DEFAULT_SEARCH_OPTIONS
#    = {'limit': 100, 'offset': 0, 'sortBy': {'column': 'name', 'order': 'asc'}} (medido
#    el 4-sep-2026 sobre la 2.31.0 instalada). El doble hace LO MISMO: si `listar_buzon`
#    volviera a llamar a `.list(carpeta)` a secas, el doble devolvería 100 de los 101 y el
#    primer assert se pondría rojo solo. Sin esa fidelidad, el test comprobaría el doble.
#
# 🔴 Y SE ANCLA EN LO QUE SE MUEVE: no en "¿ha llamado a .list?" (llamaba antes y llama
#    ahora, saldría verde igual), sino en el OFFSET de la segunda llamada — que antes no
#    existía — y en el objeto de la COLA, que es exactamente el que el corte se llevaba.
import time

import foto_comun as fc

fallos = 0


def chk(nombre, ok):
    global fallos
    print(('OK  ' if ok else 'XX  ') + nombre)
    if not ok:
        fallos += 1


# storage3 2.31.0, `storage3._sync.file_api.DEFAULT_SEARCH_OPTIONS`.
DEFECTOS_SDK = {'limit': 100, 'offset': 0, 'sortBy': {'column': 'name', 'order': 'asc'}}


def objetos_keepa(n):
    """n objetos con la forma REAL del buzón: el nombre lleva la fecha dentro, así que
    ordenar por nombre asc es ordenar por fecha asc — y la cola es lo MÁS RECIENTE."""
    salida = []
    for i in range(n):
        # 3 dígitos para que el orden lexicográfico coincida con el numérico.
        nombre = f"KeepaExport-2026-{i + 1:03d}-VisualizadorDeProductos.csv"
        salida.append({'name': nombre, 'id': f"id-{i}", 'updated_at': f"2026-01-{i + 1:03d}",
                       'metadata': {'size': 100 + i}})
    return salida


class Balde:
    """El `.from_(bucket)` del SDK: pagina como Supabase y APUNTA cada llamada."""

    def __init__(self, objetos, fallos_por_offset=None, ignora_offset=False):
        self.objetos = objetos
        self.llamadas = []                                      # {'path','limit','offset','sortBy'}
        self.fallos_por_offset = dict(fallos_por_offset or {})  # offset -> excepción pendiente
        self.ignora_offset = ignora_offset                      # servidor roto: misma página siempre
        self.ultimo_bucket = None

    def list(self, path=None, options=None):
        o = {**DEFECTOS_SDK, **(options or {})}
        # 🔴 Se apuntan las opciones CRUDAS, no las efectivas. Sobre las efectivas, "¿pidió
        #    limit=100 y sortBy name asc?" NO PUEDE FALLAR: si `listar_buzon` no las pasara,
        #    el merge con DEFECTOS_SDK las pondría igual y el assert saldría verde midiendo
        #    el default del SDK en vez del código. Lo que se mueve es lo que se pasa.
        self.llamadas.append({'path': path, 'crudas': dict(options or {}),
                              'limit': o['limit'], 'offset': o['offset'], 'sortBy': o['sortBy']})
        pendiente = self.fallos_por_offset.pop(o['offset'], None)
        if pendiente is not None:
            raise pendiente
        col = (o['sortBy'] or {}).get('column', 'name')
        orden = (o['sortBy'] or {}).get('order', 'asc')
        ordenados = sorted(self.objetos, key=lambda e: e.get(col) or '', reverse=(orden == 'desc'))
        ini = 0 if self.ignora_offset else o['offset']
        return ordenados[ini:ini + o['limit']]


class Sb:
    """El cliente: `sb.storage.from_(bucket)` y nada más, que es lo único que se usa."""

    def __init__(self, balde):
        self.storage = self
        self._balde = balde

    def from_(self, bucket):
        self._balde.ultimo_bucket = bucket
        return self._balde


class ErrHTTP(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


# ---------------------------------------------------------------------------
# 0) El doble es fiel: sin opciones corta en 100 y NO lo dice. Si esto falla, el resto
#    del fichero no prueba nada — sería un doble amable, no un Storage.
# ---------------------------------------------------------------------------
b0 = Balde(objetos_keepa(101))
chk('el doble imita al SDK: .list(carpeta) sin opciones devuelve 100 de 101',
    len(b0.list('keepa_escaparate')) == 100)


# ---------------------------------------------------------------------------
# 1) EL CASO DEL ENCARGO: 101 objetos -> los 101, y la COLA dentro.
# ---------------------------------------------------------------------------
todos = objetos_keepa(101)
ultimo_por_nombre = max(o['name'] for o in todos)
b1 = Balde(todos)
r1 = fc.listar_buzon(Sb(b1), 'informes', 'keepa_escaparate')

chk('101 objetos en el buzón -> listar_buzon devuelve 101', len(r1) == 101)
chk('  · el ÚLTIMO por nombre (el más reciente) está dentro',
    ultimo_por_nombre in [o['name'] for o in r1])
chk('  · están los 101 nombres y ninguno repetido',
    sorted(o['name'] for o in r1) == sorted(o['name'] for o in todos)
    and len({o['name'] for o in r1}) == 101)
chk('  · hicieron falta 2 páginas', len(b1.llamadas) == 2)
chk('  · la 2ª llamada va con offset 100 (lo que ANTES no existía)',
    [ll['offset'] for ll in b1.llamadas] == [0, 100])
chk('  · las dos PASAN limit=100 explícito (no se lo dejan al default del SDK)',
    [ll['crudas'].get('limit') for ll in b1.llamadas] == [100, 100])
chk('  · las dos PASAN sortBy name asc explícito',
    all(ll['crudas'].get('sortBy') == {'column': 'name', 'order': 'asc'} for ll in b1.llamadas))
chk('  · las dos PASAN offset explícito', [ll['crudas'].get('offset') for ll in b1.llamadas] == [0, 100])
chk('  · la carpeta se pasa tal cual en las dos',
    [ll['path'] for ll in b1.llamadas] == ['keepa_escaparate', 'keepa_escaparate'])
chk('  · el bucket es el que se pidió', b1.ultimo_bucket == 'informes')
chk('  · devuelve los dicts del SDK TAL CUAL (el mismo objeto, no una copia)',
    any(o is todos[0] for o in r1))


# ---------------------------------------------------------------------------
# 2) MISMO RETORNO QUE ANTES: no filtra nada, ni el placeholder de carpeta vacía.
# ---------------------------------------------------------------------------
con_placeholder = objetos_keepa(3) + [{'name': '.emptyFolderPlaceholder', 'id': None}]
r2 = fc.listar_buzon(Sb(Balde(con_placeholder)), 'informes', 'keepa_escaparate')
chk('no filtra: el .emptyFolderPlaceholder sigue saliendo (mismo retorno que antes)',
    len(r2) == 4 and '.emptyFolderPlaceholder' in [o['name'] for o in r2])


# ---------------------------------------------------------------------------
# 3) LOS BORDES. 100 y 200 clavados son los que se comería un `<= PAGINA` mal puesto.
# ---------------------------------------------------------------------------
for n, paginas in ((99, 1), (100, 2), (101, 2), (200, 3), (201, 3)):
    b = Balde(objetos_keepa(n))
    r = fc.listar_buzon(Sb(b), 'informes', 'c')
    chk(f'{n} objetos -> devuelve {n} en {paginas} página(s)',
        len(r) == n and len(b.llamadas) == paginas)

b_vacia = Balde([])
chk('carpeta vacía -> [] con una sola llamada',
    fc.listar_buzon(Sb(b_vacia), 'informes', 'c') == [] and len(b_vacia.llamadas) == 1)


# ---------------------------------------------------------------------------
# 4) EL REINTENTO SIGUE PUESTO, Y ES POR PÁGINA. Un corte de red en la 2ª página se
#    reintenta con SU offset: con captura tardía habría releído la 0 y duplicado 100.
# ---------------------------------------------------------------------------
dormir = time.sleep
time.sleep = lambda _s: None          # el reintento espera 1s de verdad; aquí no hace falta
try:
    b4 = Balde(objetos_keepa(101),
               fallos_por_offset={100: ConnectionResetError('[Errno 104] Connection reset by peer')})
    r4 = fc.listar_buzon(Sb(b4), 'informes', 'keepa_escaparate')
finally:
    time.sleep = dormir

chk('corte de red en la 2ª página -> se reintenta y devuelve los 101', len(r4) == 101)
chk('  · sin duplicados (el reintento repite SU offset, no el 0)',
    len({o['name'] for o in r4}) == 101)
chk('  · el reintento fue de la página 100, no de la 0',
    [ll['offset'] for ll in b4.llamadas] == [0, 100, 100])


# ---------------------------------------------------------------------------
# 5) UN 404 A MEDIA PAGINACIÓN ABORTA: no devuelve la lista a medias.
# ---------------------------------------------------------------------------
b5 = Balde(objetos_keepa(101),
           fallos_por_offset={100: ErrHTTP('404: Object not found', status=404)})
try:
    fc.listar_buzon(Sb(b5), 'informes', 'keepa_escaparate')
    chk('404 en la 2ª página -> aborta (no devuelve 100 callando)', False)
except fc.Aborta as e:
    chk('404 en la 2ª página -> aborta (no devuelve 100 callando)', True)
    chk('  · dice que NO es transitorio', 'NO es transitorio' in str(e))


# ---------------------------------------------------------------------------
# 6) EL TECHO: si Storage dejara de honrar `offset`, ABORTA — ni cuelga el runner ni
#    devuelve una lista corta sin decirlo.
# ---------------------------------------------------------------------------
techo = fc._MAX_PAGINAS_BUZON
fc._MAX_PAGINAS_BUZON = 3
try:
    b6 = Balde(objetos_keepa(500), ignora_offset=True)
    try:
        fc.listar_buzon(Sb(b6), 'informes', 'c')
        chk('offset ignorado -> aborta en vez de dar vueltas para siempre', False)
    except fc.Aborta as e:
        chk('offset ignorado -> aborta en vez de dar vueltas para siempre', True)
        chk('  · paró en el techo de páginas', len(b6.llamadas) == 3)
        chk('  · dice que no devuelve la lista a medias', 'a medias' in str(e))
finally:
    fc._MAX_PAGINAS_BUZON = techo

chk('el techo real sigue en 500 para el resto del proceso', fc._MAX_PAGINAS_BUZON == 500)


print()
print('✅ TODO OK' if fallos == 0 else f'❌ {fallos} FALLOS')
raise SystemExit(1 if fallos else 0)
