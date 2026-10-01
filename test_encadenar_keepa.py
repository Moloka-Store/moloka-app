# -*- coding: utf-8 -*-
"""El encadenado de Keepa (encargo del 01-oct-2026): la decision y los saltos del procesador.

🔴 QUE COMPRUEBA, EJECUTANDO las funciones de verdad (no copias):
   1. El titulo de la corrida: el `run-name:` del YAML y `titulo_corrida()` dicen lo MISMO.
      Es la memoria del encadenado; si se desalinean, cuenta cero intentos y no para nunca.
   2. El workflow, POR ESTRUCTURA (pyyaml): el job `encadenar` va tras `procesar`, solo en
      `aplicar`, con exito o fallo (no cancelado), `continue-on-error`, `actions: write` SOLO
      en el, y el resultado de la carga le llega por `needs.procesar.result`.
   3. La decision con los DATOS REALES del 01-oct-2026 (buzon, cargas y corridas medidos en
      produccion ese dia): con la pagina cerrada tras la carga de las 10:39, lanza DE/IT (los
      dos que se quedaron sin cargar) en serie, el mas antiguo primero, y despues para.
   4. Cuatro ficheros soltados y la pagina cerrada tras el primero → los cuatro, en serie.
   5. Un fichero que falla siempre → se intenta DOS veces y el resto sigue; sin bucle.
   6. Un fichero que el procesador SALTA en verde (no deja filas) no se relanza.
   7. Con otra corrida en marcha no se lanza nada (no pisa la fila pendiente de GitHub).
   8. El caso real del 27-sep: el mismo nombre resubido es OTRO fichero.
   9. Los saltos del procesador (`ya_cargado`, `superado_por`) con horas reales.

🔒 Lo que NO ve: el disparo real a GitHub ni la lectura de la base. Eso lo comprueba Fernando
   con la carga de una manana, delante (el encargo prohibe disparar cargas reales para probar).
"""
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

import yaml

import encadenar_keepa_escaparate as enc
import procesador_keepa_escaparate as proc

RAIZ = os.path.dirname(os.path.abspath(__file__))
fallos = []


def eq(nombre, got, exp):
    ok = got == exp
    if not ok:
        fallos.append(nombre)
    print('%s  %s%s' % ('OK' if ok else 'XX', nombre, '' if ok else '   got=%r exp=%r' % (got, exp)))


def t(iso):
    return datetime.fromisoformat(iso)


V = 'KeepaExport-%s-VisualizadorDeProductos%s.csv'

# ── 1 · el titulo ────────────────────────────────────────────────────────────────────────
with open(os.path.join(RAIZ, '.github', 'workflows', 'procesar-keepa-escaparate.yml'),
          encoding='utf-8') as fh:
    wf = yaml.safe_load(fh)
m = re.fullmatch(r"Keepa · \$\{\{ inputs\.modo \}\} · \$\{\{ inputs\.fichero \|\| '([^']+)' \}\}",
                 wf.get('run-name', ''))
eq('(1) run-name tiene la forma «Keepa · <modo> · <fichero>»', bool(m), True)
eq('(1) y el hueco sin fichero dice lo mismo que titulo_corrida()',
   m.group(1) if m else None, enc.SIN_FICHERO)
eq('(1) titulo_corrida, con fichero', enc.titulo_corrida(V % ('2026-10-01', ' (3)')),
   'Keepa · aplicar · KeepaExport-2026-10-01-VisualizadorDeProductos (3).csv')
eq('(1) titulo_corrida, sin fichero', enc.titulo_corrida(''), 'Keepa · aplicar · (el más reciente)')

# ── 2 · el workflow, por estructura ──────────────────────────────────────────────────────
# pyyaml lee la clave `on` como True (el «problema de Noruega»): se busca por las dos.
entradas = (wf.get('on') or wf.get(True))['workflow_dispatch']['inputs']
eq('(2) input encadenado: booleano, false por defecto',
   (entradas['encadenado']['type'], entradas['encadenado']['default']), ('boolean', False))
jp, je = wf['jobs']['procesar'], wf['jobs'].get('encadenar', {})
paso = next((p for p in jp['steps'] if p.get('name') == 'Ejecutar procesador'), {})
eq('(2) el procesador recibe ENCADENADO del input',
   re.sub(r'\s', '', paso.get('env', {}).get('ENCADENADO', '')), '${{inputs.encadenado}}')
eq('(2) encadenar va DESPUES de procesar', je.get('needs'), 'procesar')
cond = re.sub(r'\s', '', je.get('if', ''))
eq('(2) corre siempre que la carga acabe (always)', 'always()' in cond, True)
eq('(2) solo en aplicar', "inputs.modo=='aplicar'" in cond, True)
eq('(2) con exito o con fallo, y nada mas (no si se cancela)',
   sorted(re.findall(r"needs\.procesar\.result=='(\w+)'", cond)), ['failure', 'success'])
eq('(2) un fallo del encadenado no pone la carga en rojo', je.get('continue-on-error'), True)
eq('(2) permisos del encadenado: lanzar corridas y leer el repo, nada mas',
   je.get('permissions'), {'actions': 'write', 'contents': 'read'})
eq('(2) la carga NO recibe esos permisos (ni en su job ni para todo el workflow)',
   (jp.get('permissions'), wf.get('permissions')), (None, None))
pe = next((p for p in je.get('steps', []) if 'encadenar_keepa_escaparate.py' in (p.get('run') or '')), {})
env = {k: re.sub(r'\s', '', v) for k, v in (pe.get('env') or {}).items()}
eq('(2) el resultado de la carga llega por needs.procesar.result',
   env.get('PROPIO_RESULTADO'), '${{needs.procesar.result}}')
eq('(2) y su fichero, por el input', env.get('PROPIO_FICHERO'), '${{inputs.fichero}}')
eq('(2) el token es el del propio run (sin llave nueva)', env.get('GH_TOKEN'), '${{github.token}}')
eq('(2) la base, con la MISMA cadena que la carga', env.get('DB_URL'),
   re.sub(r'\s', '', paso.get('env', {}).get('DB_URL', '')))

# ── El mundo de mentira para simular corridas (3-7) ──────────────────────────────────────
TODOS = {d: date(2026, 9, 30) for d in enc.DOMINIOS}


class Mundo:
    """Buzon + base + GitHub. `correr(f)` = una corrida de `f` que acaba con `resultado`;
    tras ella corre el encadenado, como en el workflow, y devuelve lo que lanzaria."""

    def __init__(self, objetos, cargas, corridas, ahora, fotos=None, falla=()):
        self.objetos, self.cargas, self.corridas = objetos, dict(cargas), list(corridas)
        self.ahora, self.fotos, self.falla = ahora, dict(fotos or TODOS), set(falla)
        self.n, self.lanzados, self.cargados = 0, [], []

    def correr(self, fichero, salta=False):
        self.n += 1
        self.ahora += timedelta(minutes=1)
        rid = 'r%d' % self.n
        creada = self.ahora
        if fichero in self.falla:
            resultado = 'failure'
        else:
            resultado = 'success'
            if not salta:
                self.cargas[fichero] = self.ahora + timedelta(seconds=20)
                self.cargados.append(fichero)
        self.ahora += timedelta(minutes=1)
        # Mientras corre el encadenado, la corrida propia sigue «in_progress» en GitHub.
        vista = self.corridas + [{'id': rid, 'status': 'in_progress', 'conclusion': None,
                                  'display_title': enc.titulo_corrida(fichero),
                                  'created_at': creada.isoformat()}]
        d = enc.decidir(self.objetos, self.cargas, vista,
                        {'run_id': rid, 'fichero': fichero, 'resultado': resultado},
                        self.ahora, self.fotos)
        self.corridas.append({'id': rid, 'status': 'completed', 'conclusion': resultado,
                              'display_title': enc.titulo_corrida(fichero),
                              'created_at': creada.isoformat()})
        return d

    def cadena(self, primero, tope=30):
        """La pagina lanza `primero` y se CIERRA: a partir de ahi solo encadena el servidor."""
        sig = primero
        while sig and self.n < tope:
            self.lanzados.append(sig)
            sig = self.correr(sig)['siguiente']
        return self.lanzados


# ── 3 · los DATOS REALES del 01-oct-2026 ─────────────────────────────────────────────────
#    Buzon (storage.objects.updated_at), cargas (max procesado_at en viva ∪ historico) y
#    corridas (#227-#237 de GitHub) medidos en produccion el 01-oct-2026 a mediodia.
REAL = [
    (V % ('2026-09-29', ''), '2026-09-29T14:11:17.402457+00:00', '2026-09-29T05:53:21.361192+00:00'),
    (V % ('2026-09-29', ' (2)'), '2026-09-29T14:11:17.466591+00:00', '2026-09-29T05:55:29.611431+00:00'),
    (V % ('2026-09-29', ' (3)'), '2026-09-29T14:11:17.501431+00:00', '2026-09-29T05:54:25.915013+00:00'),
    (V % ('2026-09-29', ' (1)'), '2026-09-29T14:11:17.502151+00:00', '2026-09-29T05:52:06.538667+00:00'),
    (V % ('2026-09-30', ' (2)'), '2026-09-30T06:20:13.905778+00:00', '2026-09-30T06:20:34.884829+00:00'),
    (V % ('2026-09-30', ' (1)'), '2026-09-30T06:20:14.103673+00:00', '2026-09-30T06:21:34.660581+00:00'),
    (V % ('2026-09-30', ''), '2026-09-30T06:20:14.149661+00:00', '2026-09-30T06:22:33.337421+00:00'),
    (V % ('2026-09-30', ' (3)'), '2026-09-30T06:20:14.269383+00:00', '2026-09-30T06:23:58.491464+00:00'),
    (V % ('2026-10-01', ''), '2026-10-01T07:16:08.456607+00:00', '2026-10-01T07:16:30.720081+00:00'),
    (V % ('2026-10-01', ' (2)'), '2026-10-01T07:17:22.555793+00:00', '2026-10-01T07:17:45.632402+00:00'),
    (V % ('2026-10-01', ' (3)'), '2026-10-01T07:17:22.571854+00:00', None),
    (V % ('2026-10-01', ' (1)'), '2026-10-01T07:17:22.637997+00:00', None),
    (V % ('2026-10-01', ' (4)'), '2026-10-01T10:38:47.946138+00:00', '2026-10-01T10:39:10.260856+00:00'),
]
OBJ_REAL = [{'name': n, 'updated_at': s} for n, s, _ in REAL] + [
    # Lo que tambien hay en el buzon y no es candidato: un .csv.gz comprimido y uno de 26-sep.
    {'name': V % ('2026-09-20', '') + '.gz', 'updated_at': '2026-09-20T06:00:00+00:00'},
    {'name': V % ('2026-09-26', ''), 'updated_at': '2026-09-26T05:53:48.767062+00:00'},
]
CARGAS_REAL = {n: c for n, _, c in REAL}
# Las corridas de antes del cambio llevan el titulo generico: no cuentan como de ningun fichero.
CORRIDAS_REAL = [{'id': str(i), 'status': 'completed', 'conclusion': 'success',
                  'display_title': 'Moloka - Procesar KEEPA_ESCAPARATE', 'created_at': c}
                 for i, c in [(227, '2026-09-29T14:11:20Z'), (231, '2026-09-30T06:20:16Z'),
                              (235, '2026-10-01T07:16:10Z'), (236, '2026-10-01T07:17:24Z')]]
FOTOS_REAL = {'it': date(2026, 9, 30), 'de': date(2026, 9, 30),
              'fr': date(2026, 10, 1), 'es': date(2026, 10, 1)}
# La corrida #237 (ES (4), 10:38:49) es la «propia»: la que acaba y encadena.
d = enc.decidir(OBJ_REAL, CARGAS_REAL,
                CORRIDAS_REAL + [{'id': '237', 'status': 'in_progress', 'conclusion': None,
                                  'display_title': enc.titulo_corrida(V % ('2026-10-01', ' (4)')),
                                  'created_at': '2026-10-01T10:38:49Z'}],
                {'run_id': '237', 'fichero': V % ('2026-10-01', ' (4)'), 'resultado': 'success'},
                t('2026-10-01T10:40:00+00:00'), FOTOS_REAL)
estados = {n: e for n, _, e in d['filas']}
eq('(3) real 01-oct: lanza el (3) — el mas antiguo de los dos sin cargar', d['siguiente'],
   V % ('2026-10-01', ' (3)'))
eq('(3) los dos sin cargar salen como pendientes',
   sorted(n for n, e in estados.items() if e.startswith('pendiente')),
   sorted([V % ('2026-10-01', ' (1)'), V % ('2026-10-01', ' (3)')]))
eq('(3) los del 29-sep (resubidos, sin rastro en las tablas) NO: mas viejos que los cuatro paises',
   {estados[V % ('2026-09-29', s)] for s in ('', ' (1)', ' (2)', ' (3)')},
   {'más viejo que la foto viva de los cuatro países'})
eq('(3) los del 30-sep y los cargados de hoy: cargados',
   all(estados[V % (f, s)].startswith('cargado') for f, s in
       [('2026-09-30', ''), ('2026-09-30', ' (1)'), ('2026-09-30', ' (2)'), ('2026-09-30', ' (3)'),
        ('2026-10-01', ''), ('2026-10-01', ' (2)'), ('2026-10-01', ' (4)')]), True)
eq('(3) fuera de la ventana (26-sep) y el .csv.gz ni se miran',
   (V % ('2026-09-26', '') in estados, V % ('2026-09-20', '') + '.gz' in estados), (False, False))
mundo = Mundo(OBJ_REAL, CARGAS_REAL, CORRIDAS_REAL, t('2026-10-01T10:40:00+00:00'), FOTOS_REAL)
eq('(3) real 01-oct: en serie (3) → (1), y para',
   mundo.cadena(V % ('2026-10-01', ' (3)')), [V % ('2026-10-01', ' (3)'), V % ('2026-10-01', ' (1)')])

# ── 4 · cuatro soltados, la pagina se cierra tras el primero ─────────────────────────────
CUATRO = [{'name': V % ('2026-10-02', s), 'updated_at': '2026-10-02T07:17:22.%06d+00:00' % (i * 1000)}
          for i, s in enumerate(['', ' (1)', ' (2)', ' (3)'])]
mundo = Mundo(CUATRO, {}, [], t('2026-10-02T07:17:30+00:00'))
eq('(4) los cuatro se cargan, en serie, por orden de subida',
   mundo.cadena(CUATRO[0]['name']), [o['name'] for o in CUATRO])
eq('(4) cada uno UNA vez', mundo.cargados, [o['name'] for o in CUATRO])

# ── 5 · un fichero que falla siempre ─────────────────────────────────────────────────────
mundo = Mundo(CUATRO, {}, [], t('2026-10-02T07:17:30+00:00'), falla={CUATRO[1]['name']})
lanzados = mundo.cadena(CUATRO[0]['name'])
eq('(5) el que falla se intenta DOS veces y la fila sigue con los demas',
   lanzados, [CUATRO[0]['name'], CUATRO[1]['name'], CUATRO[1]['name'],
              CUATRO[2]['name'], CUATRO[3]['name']])
eq('(5) la cadena acaba sola (5 corridas, lejos del tope de 30)', mundo.n, 5)
ultima = mundo.correr(CUATRO[3]['name'])  # una corrida mas, a mano, por si acaso
eq('(5) y despues no lo vuelve a intentar', ultima['siguiente'], None)
eq('(5) el resumen lo dice', dict((n, e) for n, _, e in ultima['filas'])[CUATRO[1]['name']],
   'falló 2 veces: no se reintenta solo')
# El primero falla en la PAGINA (intento 1): el encadenado lo reintenta UNA vez (intento 2).
mundo = Mundo(CUATRO[:1], {}, [], t('2026-10-02T07:17:30+00:00'), falla={CUATRO[0]['name']})
eq('(5) fallo en la pagina → un solo reintento del servidor',
   mundo.cadena(CUATRO[0]['name']), [CUATRO[0]['name'], CUATRO[0]['name']])

# ── 6 · un salto en verde no se relanza ──────────────────────────────────────────────────
mundo = Mundo(CUATRO[:1], {}, [], t('2026-10-02T07:17:30+00:00'))
eq('(6) el procesador lo salta (verde, sin filas) → el encadenado no lo vuelve a lanzar',
   mundo.correr(CUATRO[0]['name'], salta=True)['siguiente'], None)

# ── 7 · otra corrida en marcha ───────────────────────────────────────────────────────────
otra = [{'id': 'x', 'status': 'pending', 'conclusion': None, 'display_title': 'Keepa · aplicar · y',
         'created_at': '2026-10-02T07:18:00+00:00'}]
d = enc.decidir(CUATRO, {}, otra, {'run_id': 'r', 'fichero': CUATRO[0]['name'], 'resultado': 'failure'},
                t('2026-10-02T07:20:00+00:00'), TODOS)
eq('(7) con otra corrida en marcha no lanza (la cola de GitHub cancelaria la pendiente)',
   (d['siguiente'], d['motivo'].startswith('hay otra corrida en marcha')), (None, True))

# ── 8 · el 27-sep: mismo nombre, otro fichero ────────────────────────────────────────────
#    `(1)` se cargo como FR a las 08:35:52 y se resubio a las 15:55:46 (fue IT).
N = V % ('2026-09-27', ' (1)')
obj = [{'name': N, 'updated_at': '2026-09-27T15:55:46.496422+00:00'}]
titulada = [{'id': 'a', 'status': 'completed', 'conclusion': 'success', 'display_title': enc.titulo_corrida(N),
             'created_at': '2026-09-27T08:35:29Z'}]
d = enc.decidir(obj, {N: '2026-09-27T08:35:52.916717+00:00'}, titulada,
                {'run_id': 'z', 'fichero': '', 'resultado': 'success'}, t('2026-09-27T15:56:00+00:00'),
                {k: date(2026, 9, 26) for k in enc.DOMINIOS})
eq('(8) 27-sep: la carga y la corrida de la version de las 08:35 NO cuentan para la de las 15:55',
   d['siguiente'], N)
eq('(8) procesador: ya_cargado con la carga de FR (08:35) → no',
   proc.ya_cargado('2026-09-27T15:55:46.496422+00:00', t('2026-09-27T08:35:52.916717+00:00')), False)
eq('(8) procesador: ya_cargado con la de IT (15:56:07) → si',
   proc.ya_cargado('2026-09-27T15:55:46.496422+00:00', t('2026-09-27T15:56:07.993782+00:00')), True)
eq('(8) sin hora de subida no se afirma nada', proc.ya_cargado(None, t('2026-09-27T15:56:07+00:00')), False)

# ── 9 · superado_por, con el ES de hoy ───────────────────────────────────────────────────
#    ES subido 07:16:08 y cargado; ES (4) subido 10:38:47 y cargado 10:39:10: la viva es (4).
viva_es = {'fichero': V % ('2026-10-01', ' (4)'), 'fecha_foto': date(2026, 10, 1),
           'procesado_at': t('2026-10-01T10:39:10.260856+00:00'),
           'subido': '2026-10-01T10:38:47.946138+00:00'}
eq('(9) el ES de las 07:16 con el (4) ya cargado → superado (pondria la vieja encima)',
   bool(proc.superado_por(V % ('2026-10-01', ''), date(2026, 10, 1), '2026-10-01T07:16:08.456607+00:00',
                          viva_es, False)), True)
eq('(9) el propio (4) no se supera a si mismo',
   proc.superado_por(viva_es['fichero'], date(2026, 10, 1), viva_es['subido'], viva_es, False), None)
eq('(9) uno del mismo dia subido DESPUES que la viva → se carga',
   proc.superado_por(V % ('2026-10-01', ' (5)'), date(2026, 10, 1), '2026-10-01T12:00:00+00:00',
                     viva_es, False), None)
eq('(9) la viva se resubio y aun no se ha cargado (subida > carga) → no se fia: se carga',
   proc.superado_por(V % ('2026-10-01', ''), date(2026, 10, 1), '2026-10-01T07:16:08+00:00',
                     dict(viva_es, subido='2026-10-01T11:00:00+00:00'), False), None)
eq('(9) un dia anterior, a mano → None (lo para la Guarda 11 en rojo, como siempre)',
   proc.superado_por(V % ('2026-09-30', ''), date(2026, 9, 30), '2026-10-01T11:00:00+00:00',
                     viva_es, False), None)
eq('(9) un dia anterior, ENCADENADO → se salta en verde',
   bool(proc.superado_por(V % ('2026-09-30', ''), date(2026, 9, 30), '2026-10-01T11:00:00+00:00',
                          viva_es, True)), True)
eq('(9) pais sin foto viva → se carga', proc.superado_por('x', date(2026, 10, 1), None, None, True), None)

print('')
if fallos:
    print('%d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('TODO OK · encadenado de Keepa')
