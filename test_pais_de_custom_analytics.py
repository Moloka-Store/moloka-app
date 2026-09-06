# -*- coding: utf-8 -*-
"""MESA DE PRUEBAS del PAÍS en el procesador de Custom Analytics.
Alemania ENTRA en el selector (6-sep-2026) y NO compite en el cruce de cuotas.

Qué prueba y qué NO:
  · SÍ: que un fichero declarado DE ENTRA sin que la guarda 6.6 lo rechace ni le
        recalcule el país, y que el motivo sale escrito («sin cuota de referencia»).
  · SÍ: que eso NO es un agujero — un fichero declarado DE que en realidad cuadra con
        ES sigue ABORTANDO. Es la mitad que se olvida al «saltar» una guarda.
  · SÍ: que ES/IT/FR se comportan EXACTAMENTE igual que antes (la otra mitad que se
        olvida), y que DE no puede colarse como candidato y ganarle a nadie.
  · SÍ: que el etiquetado del inventario dice «no identificable» en vez de bautizar el
        fichero alemán con el país menos malo — que era lo que hacía hasta hoy.
  · SÍ: que las DOS listas están, y que el `.yml` ofrece los mismos países que el
        procesador ACEPTA. Sin ese cotejo, añadir DE en un sitio y no en el otro da un
        422 en la cara de quien pulse el botón, y ningún test se pondría rojo.
  · NO: las cifras reales de Alemania. Ésas salen de correr el procesador contra el
        fichero de verdad en Actions (el ensayo). Aquí los datos son sintéticos y están
        elegidos para hacer saltar cada rama a propósito (§3 de CLAUDE.md).

🔬 DE DÓNDE SALE LA REGLA, medido en producción el 6-sep-2026 (transacciones_movimientos,
   tipo_norm='pedido', 8-ene→5-sep, cruzado por el puente SKU→ASIN):
       ES 15.783 uds / 344 ASIN  ·  IT 869 / 117  ·  FR 669 / 94  ·  DE 170 / 53
   Y con el export real de amazon.de (`metric-data (12).xlsx`, 198 ASIN, 107 uds pedidas):
       error de cuota  ES=100,0%  ·  IT=100,0%  ·  FR=100,0%   → no es ninguno de ellos.
   Con la lectura española del mismo día declarada DE: ES=2,3% → tiene que abortar.
"""
import io, os, re, sys
from datetime import date, datetime, timezone

RUTA = os.environ.get('PROC') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'procesador_custom_analytics.py')
YML = os.path.join(os.path.dirname(os.path.abspath(RUTA)),
                   '.github', 'workflows', 'procesar-custom-analytics.yml')

os.environ.setdefault('PAIS', 'ES')
sys.path.insert(0, os.path.dirname(RUTA))
import procesador_custom_analytics as P

FALLOS = []


def ok(nombre, cond, detalle=''):
    print(('  OK   ' if cond else '  FALLA') + '  ' + nombre
          + (('  ·  ' + detalle) if detalle else ''))
    if not cond:
        FALLOS.append(nombre)


# ---------------------------------------------------------------------------
# El mundo de mentira. `sku == asin` para que el puente sea la identidad y lo que se
# ejercite sea la ARITMÉTICA DE CUOTAS, no el puente (que tiene su propio banco).
# Cada país tiene 12 ASIN propios con el MISMO peso, así que su cuota es 1/12 cada uno:
# un fichero que traiga los 12 de un país da error 0 contra él y 100% contra los demás.
# Las unidades imitan las proporciones reales: España mucho, Alemania una miseria.
# ---------------------------------------------------------------------------
PESOS = {'ES': 100, 'IT': 50, 'FR': 40, 'DE': 5}
ASINS = {p: ['%s%02d' % (p, i) for i in range(1, 13)] for p in PESOS}
FMIN, FMAX = date(2026, 1, 8), date(2026, 9, 5)
LEIDO = datetime(2026, 9, 6, 7, 27, 27, tzinfo=timezone.utc)


class CurFalso:
    """Contesta a las consultas que hace este trozo del procesador, por su texto."""

    def __init__(self):
        self.ultima = ''
        self.una = None
        self.muchas = []

    def execute(self, sql, args=None):
        self.ultima = ' '.join(sql.split())
        if 'FROM productos' in self.ultima:
            self.muchas = [(a, a) for p in ASINS for a in ASINS[p]]
        elif 'FROM listings_amazon' in self.ultima:
            self.muchas = []
        elif 'min(fecha)' in self.ultima:
            self.una = (FMIN, FMAX)      # mismo tramo para el global y para cada país
        elif 'FROM transacciones_movimientos' in self.ultima:
            self.muchas = [(p, a, PESOS[p]) for p in ASINS for a in ASINS[p]]
        else:
            raise AssertionError('consulta no prevista en el banco: ' + self.ultima)

    def fetchall(self):
        return self.muchas

    def fetchone(self):
        return self.una


def fichero_de(pais):
    """Un .xlsx de mentira: una unidad pedida en cada uno de los 12 ASIN de ese país."""
    return dict((a, 1) for a in ASINS[pais])


# -- 1) Las DOS listas existen y dicen cosas distintas ----------------------
print('\n1) Las dos listas')
ok('DE se ACEPTA en el selector', 'DE' in P.PAISES_VALIDOS, str(P.PAISES_VALIDOS))
ok('DE NO hace de patrón de cuota', 'DE' not in P.PAISES_CON_CUOTA, str(P.PAISES_CON_CUOTA))
ok('los tres de siempre siguen siendo patrón',
   tuple(P.PAISES_CON_CUOTA) == ('ES', 'IT', 'FR'))
ok('todo país con cuota es un país válido',
   all(p in P.PAISES_VALIDOS for p in P.PAISES_CON_CUOTA))

# -- 2) El .yml ofrece lo mismo que el procesador acepta -------------------
#    🔴 Éste es el test del 422: si alguien añade un país aquí y no allí (o al revés),
#       el disparo de la pantalla se rechaza entero y el fallo aparece lejos del cambio.
print('\n2) El .yml y el procesador ofrecen los mismos países')
txt_yml = io.open(YML, encoding='utf-8').read()
tras_pais = txt_yml.split('      pais:')[1]
m = re.search(r'^\s*options:\s*\[([^\]]*)\]\s*$', tras_pais, re.M)
paises_yml = tuple(x.strip() for x in m.group(1).split(',')) if m else ()
ok('el choice `pais` del .yml = PAISES_VALIDOS',
   paises_yml == tuple(P.PAISES_VALIDOS), 'yml=%s' % (paises_yml,))

# -- 3) Un fichero ALEMÁN declarado DE: entra, y se dice por qué no se confirma --
print('\n3) Fichero alemán declarado DE')
ver, det = P.guarda_pais(CurFalso(), 'DE', LEIDO, fichero_de('DE'))
ok('no aborta y SALTA la comprobación', ver == 'salta', ver)
ok('dice literalmente que no hay cuota de referencia',
   'sin cuota de referencia' in det)
ok('deja claro que el país elegido se RESPETA', 'RESPETA' in det)
ok('cuenta la referencia que sí hay (para el día que crezca)',
   'uds pedidas' in det and 'ASIN' in det, det[:120])

# -- 4) ...y NO es un agujero: un fichero ESPAÑOL declarado DE aborta -------
print('\n4) Fichero español declarado DE (el selector puesto mal)')
try:
    P.guarda_pais(CurFalso(), 'DE', LEIDO, fichero_de('ES'))
    ok('aborta', False, 'NO abortó: entraría un fichero de ES como si fuera de DE')
except P.Aborta as e:
    ok('aborta', True)
    ok('nombra al país verdadero en el mensaje', 'ES' in str(e))

# -- 5) Los de siempre, exactamente igual que antes ------------------------
print('\n5) ES/IT/FR sin cambios')
for p in ('ES', 'IT', 'FR'):
    ver, det = P.guarda_pais(CurFalso(), p, LEIDO, fichero_de(p))
    ok('%s con su propio fichero -> ok' % p, ver == 'ok', ver)
try:
    P.guarda_pais(CurFalso(), 'ES', LEIDO, fichero_de('IT'))
    ok('ES declarado sobre un fichero de IT aborta', False, 'NO abortó')
except P.Aborta:
    ok('ES declarado sobre un fichero de IT aborta', True)

# -- 6) DE no puede ganarle a nadie: ni siquiera es candidato --------------
print('\n6) DE no compite')
errores, tabla, trans = P._errores_de_cuota(CurFalso(), FMIN, FMAX, fichero_de('DE'))
ok('los candidatos son sólo los que tienen patrón',
   sorted(errores) == sorted(P.PAISES_CON_CUOTA), str(sorted(errores)))
ok('DE no aparece en la tabla que se imprime', 'DE=' not in tabla, tabla)
ok('pero sus unidades sí se pueden contar (van en `trans`)',
   int(sum(trans['DE'].values())) == 12 * PESOS['DE'])

# -- 7) El inventario ya no bautiza al fichero alemán ----------------------
print('\n7) Etiquetado del inventario')
etiqueta, tabla = P.etiquetar_pais(CurFalso(), LEIDO, fichero_de('DE'))
ok('un fichero que no es de ninguno de los tres NO se etiqueta',
   etiqueta is None, str(etiqueta))
ok('y se dice por qué', 'ninguno baja' in tabla, tabla)
for p in ('ES', 'IT', 'FR'):
    etiqueta, _ = P.etiquetar_pais(CurFalso(), LEIDO, fichero_de(p))
    ok('%s se sigue etiquetando bien' % p, etiqueta == p, str(etiqueta))

# -- 8) La rama nueva es LOAD-BEARING --------------------------------------
#    Si alguien mete DE en PAISES_CON_CUOTA «para simplificar», el fichero alemán deja de
#    entrar por la puerta nueva y vuelve a competir con una referencia que es ruido. Aquí
#    se ancla que el camino es OTRO, no que el resultado cambie: con datos de juguete DE
#    ganaría, pero con la referencia REAL (170 uds contra 15.783) ganar o perder es una
#    lotería, y perder significa abortar una carga correcta.
print('\n8) Sin la rama nueva, el fichero alemán no pasa por ella')
CON_CUOTA = P.PAISES_CON_CUOTA
try:
    P.PAISES_CON_CUOTA = ('ES', 'IT', 'FR', 'DE')   # el «atajo» que hay que evitar
    ver, det = P.guarda_pais(CurFalso(), 'DE', LEIDO, fichero_de('DE'))
    ok('con DE como candidato ya no se salta la comprobación',
       'sin cuota de referencia' not in det, ver)
finally:
    P.PAISES_CON_CUOTA = CON_CUOTA

print('\n' + '=' * 70)
if FALLOS:
    print('FALLAN %d: %s' % (len(FALLOS), ', '.join(FALLOS)))
    sys.exit(1)
print('Todo verde.')
