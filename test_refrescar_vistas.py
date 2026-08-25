# -*- coding: utf-8 -*-
"""El gancho del refresco de materializadas, visto ROJO y visto CALLADO.

🔴 POR QUE ESTE FICHERO EXISTE. `refrescar_vistas()` corre DESPUES del commit y no
   aborta nunca: si falla, la carga del informe ya esta escrita y lo unico que
   queda es el grito. O sea que un fallo suyo NO tumba el workflow -- se veria
   dias despues, cuando alguien mirase la pantalla y encontrase ventas viejas.
   Por eso lo que hay que probar aqui no es que funcione: es QUE GRITE, y que
   grite lo que hace falta para arreglarlo.

🔒 LAS DOS DIRECCIONES (§3 de CLAUDE.md): que hable cuando toca y que este callado
   cuando no. Un `return False` incondicional pasaria la mitad de arriba.

⚠️ Y la mitad mas facil de olvidar: **que NO avise a la app cuando el refresco
   fue mal**. Avisar entonces es peor que no avisar -- la app tira su cache,
   relee la copia VIEJA y la vuelve a cachear con sello nuevo: dato caducado
   disfrazado de fresco.
"""
import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from foto_comun import refrescar_vistas, REFRESCOS_POR_FUENTE  # noqa: E402

fallos = []


def eq(nombre, obtenido, esperado):
    ok = obtenido == esperado
    if not ok:
        fallos.append(nombre)
    print(('OK  ' if ok else 'XX  ') + nombre
          + ('' if ok else '   got=%r exp=%r' % (obtenido, esperado)))


class CursorFalso:
    """Se comporta como el cursor de psycopg2 en lo que esta funcion usa, y deja
    APUNTADO todo lo que se le pidio ejecutar."""

    def __init__(self, existe=True, dueno='postgres', quien='postgres', refresco_revienta=None):
        self.existe = existe
        self.dueno = dueno
        self.quien = quien
        self.refresco_revienta = refresco_revienta
        self.ejecutadas = []
        self._ultimo = None

    def execute(self, sql, args=None):
        self.ejecutadas.append(sql)
        s = sql.lower()
        if 'current_user' in s:
            self._ultimo = (self.quien,)
        elif 'to_regclass' in s:
            self._ultimo = ('algo' if self.existe else None,)
        elif 'pg_get_userbyid' in s:
            self._ultimo = (self.dueno,)
        elif 'refresh materialized view' in s:
            if self.refresco_revienta is not None:
                raise self.refresco_revienta
            self._ultimo = None
        else:
            self._ultimo = None

    def fetchone(self):
        return self._ultimo

    def close(self):
        pass


class InfoFalsa:
    def __init__(self, estado):
        self.transaction_status = estado


class ConexionFalsa:
    """🔴 Sabe de `transaction_status`, de `rollback()` y de que asignar `autocommit`
    PUEDE FALLAR -- las tres cosas que la version anterior NO sabia, y por eso no cazo
    el bug del 25-ago: `con.autocommit = True` estaba fuera del try y con una
    transaccion abierta psycopg2 lanza `set_session cannot be used inside a
    transaction`. En un procesador real eso habria tumbado la carga del informe.
    Una conexion de mentira que solo sabe el camino feliz no prueba el infeliz."""

    def __init__(self, cur, estado=psycopg2.extensions.TRANSACTION_STATUS_IDLE,
                 autocommit_revienta=False):
        self._cur = cur
        self._autocommit = False
        self._estado = estado
        self.autocommit_revienta = autocommit_revienta
        self.rollbacks = 0

    @property
    def info(self):
        return InfoFalsa(self._estado)

    @property
    def autocommit(self):
        return self._autocommit

    @autocommit.setter
    def autocommit(self, valor):
        # psycopg2 lanza ProgrammingError si hay una transaccion abierta.
        if self.autocommit_revienta and valor:
            raise psycopg2.ProgrammingError(
                'set_session cannot be used inside a transaction')
        self._autocommit = valor

    def rollback(self):
        self.rollbacks += 1
        self._estado = psycopg2.extensions.TRANSACTION_STATUS_IDLE

    def cursor(self):
        return self._cur


def corre(cur, fuente='ledger', con=None):
    """Devuelve (resultado, lineas escritas, conexion)."""
    con = con if con is not None else ConexionFalsa(cur)
    salida = []
    r = refrescar_vistas(con, fuente, escribir=salida.append)
    return r, '\n'.join(salida), con


print('== 1) EL CAMINO BUENO ==')
c = CursorFalso()
r, txt, con = corre(c)
eq('(1) devuelve True', r, True)
eq('(1) ha refrescado de verdad',
   any('refresh materialized view' in e.lower() for e in c.ejecutadas), True)
# 🔒 Sin el indice unico esto bloquearia a quien este leyendo la pantalla.
eq('(1) … sin bloquear a los lectores',
   any('concurrently' in e.lower() for e in c.ejecutadas), True)
# 🔴 Anclado en el ROTULO de esa linea, no en el valor: `postgres` sale TAMBIEN en la
#    linea del dueno, asi que buscarlo daba verde con la linea borrada. Cazado
#    rompiendolo. Es el patron de siempre: un assert que busca algo que aparece en dos
#    sitios no distingue cual de los dos falta.
eq('(1) 🔴 registra current_user SIEMPRE, no solo al fallar', 'conectado como' in txt, True)
eq('(1) … y dice cuanto tardo', 'ms' in txt, True)
eq('(1) 🔒 avisa a la app', '/api/cache/invalidar' in txt, True)
eq('(1) 🔒 y deja el autocommit como estaba', con.autocommit, False)

print('\n== 2) LA MV NO EXISTE TODAVIA (la migracion no se ha aplicado) ==')
c = CursorFalso(existe=False)
r, txt, _ = corre(c)
eq('(2) 🔴 devuelve False', r, False)
eq('(2) 🔴 … y NO intenta refrescar',
   any('refresh materialized view' in e.lower() for e in c.ejecutadas), False)
eq('(2) … diciendo que la migracion falta', 'no se ha aplicado' in txt.lower(), True)
# 🔴 Y lo que NO tiene que decir: que la carga haya fallado. El informe ya esta escrito.
eq('(2) 🔒 … y aclarando que la carga SI esta hecha',
   'el informe ya esta escrito' in txt.lower(), True)
eq('(2) 🔴 NO avisa a la app', '/api/cache/invalidar' in txt, False)

print('\n== 3) NO ES DUENO: REFRESH exige propiedad, no permisos ==')
c = CursorFalso(quien='otro_usuario', dueno='postgres',
                refresco_revienta=psycopg2.errors.InsufficientPrivilege(
                    'must be owner of materialized view mv_ventas_ventanas'))
r, txt, con = corre(c)
eq('(3) 🔴 devuelve False', r, False)
eq('(3) 🔴 dice QUIEN es', 'otro_usuario' in txt, True)
eq('(3) 🔴 … y QUIEN es el dueno', 'postgres' in txt, True)
eq('(3) … y el error exacto', 'must be owner' in txt, True)
eq('(3) 🔒 … y como se arregla', 'SECURITY' in txt, True)
eq('(3) 🔴 NO avisa a la app', '/api/cache/invalidar' in txt, False)
eq('(3) 🔒 y deja el autocommit como estaba', con.autocommit, False)

print('\n== 3b) UN FALLO INESPERADO NO PUEDE TUMBAR LA CORRIDA ==')
# 🔴 EL DANO DE VERDAD NO ES QUE FALLE EL REFRESCO: es que el workflow salga ROJO.
#    El commit ya paso, asi que el informe esta escrito y a salvo. Si esto tumbara la
#    corrida, quien la mirase pensaria que la carga fallo y VOLVERIA A SUBIR EL
#    INFORME. Por eso `refrescar_vistas` no deja subir NINGUNA excepcion.
# 🔒 Y es seguro tragarselo aqui SOLO porque el centinela de la pantalla ya esta
#    desplegado: si el refresco se cae callado, la pantalla lo dice.
# ⚠️ Este caso NO lo cubria ningun test hasta el 25-ago-2026: la conexion de mentira
#    solo sabia reventar en el REFRESH, que lo caza el manejador de DENTRO. El de
#    FUERA --el que da esta garantia-- no se ejecutaba nunca. Cazado rompiendolo.


class CursorQueRevientaRaro(CursorFalso):
    """Revienta con algo que NO es un error de psycopg2, y en un sitio que el
    manejador de dentro no cubre: al preguntar si la mv existe."""

    def execute(self, sql, args=None):
        if 'to_regclass' in sql.lower():
            raise RuntimeError('la conexion se ha caido en mitad del refresco')
        return super().execute(sql, args)


c = CursorQueRevientaRaro()
tumbo = False
try:
    r, txt, con = corre(c)
except Exception:
    tumbo = True
    r, txt, con = None, '', None
eq('(3b) 🔴 NO deja subir la excepcion', tumbo, False)
eq('(3b) 🔴 … y devuelve False', r, False)
eq('(3b) … diciendo que ha reventado', 'REVENTADO' in txt, True)
eq('(3b) 🔴 … y que la CARGA no se ve afectada', 'NO se ve afectada' in txt, True)
eq('(3b) 🔒 … y que NO se vuelva a subir el informe', 'NO vuelvas a subir' in txt, True)
eq('(3b) 🔴 NO avisa a la app', '/api/cache/invalidar' in txt, False)
eq('(3b) 🔒 y deja el autocommit como estaba', con.autocommit, False)

print('\n== 3c) LLAMADO CON UNA TRANSACCION ABIERTA ==')
# 🔴 EL BUG DEL 25-ago, y el sexto assert del dia que debia ser rojo y salio verde.
#    `con.autocommit = True` estaba FUERA del try. psycopg2 lanza `set_session cannot
#    be used inside a transaction` si hay una transaccion abierta, asi que la garantia
#    de "se traga cualquier excepcion y no tumba la carga" era FALSA en la propia linea
#    que la daba. Lo encontro un rojo del workflow de diagnostico, no esta mesa: la
#    conexion de mentira llegaba SIEMPRE a esa linea en estado limpio.
# 🔒 Y no se da por hecho que el caller llame justo despues del commit: es verdad en el
#    camino que se escribio y falso en cualquier otro (basta un SELECT despues).
c = CursorFalso()
con_sucia = ConexionFalsa(c, estado=psycopg2.extensions.TRANSACTION_STATUS_INTRANS)
r, txt, con_sucia = corre(c, con=con_sucia)
eq('(3c) 🔴 con transaccion abierta NO revienta', r is not None, True)
eq('(3c) 🔴 … y RENUNCIA al refresco (devuelve False)', r, False)
# 🔴 EL ASSERT QUE MAS IMPORTA DE ESTE BLOQUE, y viene de una correccion de Fernando:
#    aqui hubo un `con.rollback()` "para dejar la conexion limpia". Era un error. Una
#    transaccion abierta significa que quien llamo tenia trabajo SIN CONFIRMAR, y
#    hacerle rollback SE LO DESTRUYE. La justificacion --"si solo se leyo, no deshace
#    nada"-- daba por hecho justo lo que no se puede saber en ese punto.
#    Lo que se pierde renunciando es que la copia se quede vieja, y ESO LO CAZA EL
#    CENTINELA. Lo que perderia un rollback no lo caza nadie.
eq('(3c) 🔴 … SIN tocar la transaccion de quien llamo', con_sucia.rollbacks, 0)
eq('(3c) … diciendo por que', 'TRANSACCION ABIERTA' in txt, True)
eq('(3c) … y que la copia se queda vieja', 'centinela' in txt, True)
eq('(3c) 🔴 NO avisa a la app', '/api/cache/invalidar' in txt, False)
eq('(3c) 🔒 y deja el autocommit como estaba', con_sucia.autocommit, False)
eq('(3c) 🔒 … y ni siquiera intento refrescar',
   any('refresh materialized view' in e.lower() for e in c.ejecutadas), False)

print('\n== 3d) SI ASIGNAR autocommit REVIENTA, TAMPOCO TUMBA LA CARGA ==')
# 🔴 La misma excepcion exacta, pero por un camino que el rollback no arregla. La
#    garantia tiene que aguantar igual: devolver False, no propagar, y NO avisar.
c = CursorFalso()
con_mala = ConexionFalsa(c, autocommit_revienta=True)
tumbo = False
try:
    r, txt, con_mala = corre(c, con=con_mala)
except Exception:
    tumbo = True
    r, txt = None, ''
eq('(3d) 🔴 NO deja subir la excepcion', tumbo, False)
eq('(3d) 🔴 … y devuelve False', r, False)
eq('(3d) … nombrando el error de psycopg2', 'set_session' in txt, True)
eq('(3d) 🔴 … y que la CARGA no se ve afectada', 'NO se ve afectada' in txt, True)
eq('(3d) 🔴 NO avisa a la app', '/api/cache/invalidar' in txt, False)

print('\n== 4) UNA FUENTE QUE NO TIENE MATERIALIZADAS ==')
c = CursorFalso()
r, txt, _ = corre(c, fuente='keepa')
eq('(4) devuelve True (no hay nada que hacer)', r, True)
eq('(4) 🔒 y esta CALLADO: ni una linea', txt, '')
eq('(4) 🔒 … y no ha tocado la base', c.ejecutadas, [])

print('\n== 5) EL MAPA FUENTE -> MATERIALIZADAS ==')
# 🔴 Anclado sobre lo que tiene que estar: las dos fuentes de v_ventas_ventanas.
#    Si alguien anade una mv y olvida su fuente, el refresco no corre y no chilla
#    nadie -- este assert es el unico sitio donde eso se ve.
eq('(5) el ledger refresca las ventanas',
   'mv_ventas_ventanas' in REFRESCOS_POR_FUENTE.get('ledger', ()), True)
eq('(5) las transacciones tambien',
   'mv_ventas_ventanas' in REFRESCOS_POR_FUENTE.get('transacciones', ()), True)
# 🔴 LA TERCERA, que es la que se me olvido en la primera version de este mapa.
#    listings_amazon es el MAPA SKU -> ASIN de esa vista: si cambia y no se refresca,
#    las ventas de un SKU nuevo dejan de sumarse a su ASIN y el numero sale BAJO.
eq('(5) 🔴 y listings TAMBIEN las refresca (es el mapa SKU->ASIN)',
   'mv_ventas_ventanas' in REFRESCOS_POR_FUENTE.get('listings', ()), True)
# 🔒 Anclado sobre el RECUENTO: si manana alguien anade una fuente a la vista y se
#    olvida del gancho, esto no lo caza -- pero si caza que alguien QUITE una.
eq('(5) 🔒 v_ventas_ventanas se refresca desde sus TRES fuentes',
   sorted(f for f, vs in REFRESCOS_POR_FUENTE.items() if 'mv_ventas_ventanas' in vs),
   ['ledger', 'listings', 'transacciones'])

# 🔴 LA SEGUNDA MATERIALIZADA, Y SU FUENTE ES **UNA SOLA**. `mv_rentabilidad_sku`
#    agrega `transacciones_movimientos` y nada mas: `productos` --el pvd, el
#    producto_id, el con_ficha-- se cruza EN VIVO en las vistas de encima, asi que
#    cambiar una ficha NO necesita refresco. Ese es justamente el motivo del reparto.
eq('(5) 🔴 las transacciones refrescan TAMBIEN la rentabilidad',
   'mv_rentabilidad_sku' in REFRESCOS_POR_FUENTE.get('transacciones', ()), True)
# 🔒 Anclado sobre lo que NO debe aparecer, que es la mitad que se mueve: si alguien
#    la colgara de ledger o de listings estaria refrescando de mas por un evento que
#    no la toca, y nadie lo notaria porque el dato saldria bien igual.
eq('(5) 🔒 … y NADIE MAS la refresca',
   sorted(f for f, vs in REFRESCOS_POR_FUENTE.items() if 'mv_rentabilidad_sku' in vs),
   ['transacciones'])

print('\n== 5b) LAS ETIQUETAS DEL AVISO SALEN DE LO QUE SE REFRESCO ==')
# 🔴 LAS DOS DIRECCIONES, y la segunda es la que importa: que la etiqueta APAREZCA
#    cuando toca y que NO aparezca cuando no toca. Una lista fija de etiquetas pasaria
#    la primera mitad SIEMPRE, mida lo que mida.
#    Un informe de ledger no toca la rentabilidad: mandar su etiqueta seria tirar una
#    cache que estaba bien. No da un dato falso, pero es trabajo que nadie pidio.
c = CursorFalso()
_, txt_tx, _ = corre(c, fuente='transacciones')
c = CursorFalso()
_, txt_led, _ = corre(c, fuente='ledger')
eq('(5b) transacciones avisa de la RENTABILIDAD', 'rentabilidad' in txt_tx, True)
eq('(5b) … y tambien del inventario', 'inventario' in txt_tx, True)
eq('(5b) 🔴 el ledger NO avisa de la rentabilidad', 'rentabilidad' in txt_led, False)
eq('(5b) 🔒 … pero si avisa de lo suyo', 'inventario' in txt_led, True)

print('\n== 6) LOS DOS PROCESADORES LO LLAMAN DE VERDAD ==')
# 🔴 Un CI verde no prueba que una feature este viva. `refrescar_vistas` puede estar
#    perfecta y no ejecutarse nunca.
# ⚠️ Sobre el codigo SIN comentarios: la cabecera del gancho NOMBRA la funcion, asi
#    que un grep sobre el fichero crudo daria verde con la llamada borrada.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))
from censo_migraciones import sin_comentarios  # noqa: E402


def sin_almohadillas(texto):
    return '\n'.join(l for l in texto.split('\n') if not l.lstrip().startswith('#'))


for fichero, fuente in (('procesador_ledger.py', 'ledger'),
                        ('procesador_transacciones.py', 'transacciones'),
                        ('procesador_all_listings.py', 'listings')):
    with open(fichero, encoding='utf-8') as fh:
        codigo = sin_almohadillas(fh.read())
    eq('(6) %s llama al refresco con su fuente' % fichero,
       "refrescar_vistas(con, '%s')" % fuente in codigo, True)
    # 🔴 Y DENTRO DE LA RAMA DE `aplicar`, NO SOLO "DESPUES DEL COMMIT".
    #    Aqui hubo un assert mio que comparaba POSICIONES (`pos_refresco > pos_commit`)
    #    y habria pasado igual con el gancho puesto tras el `con.rollback()` de la rama
    #    de ENSAYO -- que es exactamente el error contra el que se escribio. Un ensayo
    #    con efectos secundarios deja de ser un ensayo: refrescaria y avisaria a la app
    #    por una corrida que no aplico nada.
    #    Se recorta la rama de `aplicar` y se mira DENTRO.
    ini = codigo.find("if MODO == 'aplicar':")
    fin = codigo.find('con.rollback()', ini)
    rama_aplicar = codigo[ini:fin] if ini != -1 and fin != -1 else ''
    eq('(6) el recorte de la rama aplicar trae codigo', len(rama_aplicar) > 0, True)
    eq('(6) 🔴 … y el refresco esta DENTRO de esa rama',
       'refrescar_vistas(' in rama_aplicar, True)
    # 🔒 Anclado sobre lo que NO debe haber: ni una llamada fuera de esa rama.
    eq('(6) 🔒 … y NO hay ninguna otra llamada suelta',
       codigo.count('refrescar_vistas(') , 1)

print('')
if fallos:
    print('%d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('TODO OK · gancho del refresco de materializadas')
