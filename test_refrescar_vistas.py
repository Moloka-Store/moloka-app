# -*- coding: utf-8 -*-
"""El gancho del refresco de copias, visto ROJO y visto CALLADO.

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

    # 🔴 SABE ABORTAR LA TRANSACCION, y eso es lo que lo hace un doble y no un decorado.
    #    En Postgres, un error dentro de una transaccion la ABORTA ENTERA: todo lo que
    #    venga detras revienta con `InFailedSqlTransaction` hasta que alguien haga commit
    #    o rollback. Sin esto, la mesa daba VERDE con el commit-por-copia quitado --el
    #    fallo de una copia se llevaria por delante a las demas y al Trackeador, y aqui
    #    no se veria--. Cazado el 25-ago rompiendolo a mano.
    def __init__(self, existe=True, dueno='postgres', quien='postgres',
                 refresco_revienta=None, trackeador='1234 filas en 7.4 s',
                 trackeador_revienta=None):
        self.abortada = False
        self.existe = existe
        self.dueno = dueno
        self.quien = quien
        self.refresco_revienta = refresco_revienta
        self.trackeador = trackeador
        self.trackeador_revienta = trackeador_revienta
        self.ejecutadas = []
        self._ultimo = None

    def execute(self, sql, args=None):
        if self.abortada:
            raise psycopg2.errors.InFailedSqlTransaction(
                'current transaction is aborted, commands ignored until end of '
                'transaction block')
        self.ejecutadas.append(sql)
        s = sql.lower()
        if 'current_user' in s:
            self._ultimo = (self.quien,)
        elif 'to_regclass' in s:
            self._ultimo = ('algo' if self.existe else None,)
        elif 'pg_get_userbyid' in s:
            self._ultimo = (self.dueno,)
        elif 'fn_trackeador_refrescar' in s:
            if self.trackeador_revienta is not None:
                self.abortada = True
                raise self.trackeador_revienta
            self._ultimo = (self.trackeador,)
        elif 'refresh materialized view' in s:
            if self.refresco_revienta is not None:
                self.abortada = True
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
    """🔴 Sabe de `transaction_status`, de `commit()`, de `rollback()`, y de que NADIE
    debe tocar `autocommit`.

    ⚠️ Ese ultimo detalle es un assert disfrazado de doble, y esta anclado sobre lo
       que NO debe pasar --que es la unica mitad que se mueve--: hasta el 25-ago-2026
       esta funcion ponia la conexion en autocommit, y de ahi salio un rojo en
       produccion (`set_session cannot be used inside a transaction`). Ahora no hace
       falta, asi que el doble REVIENTA si alguien vuelve a asignarlo. Un test que
       solo comprobara "sigue valiendo False" saldria verde con la asignacion puesta
       y deshecha en el `finally`."""

    def __init__(self, cur, estado=psycopg2.extensions.TRANSACTION_STATUS_IDLE):
        self._cur = cur
        self._autocommit = False
        self._estado = estado
        self.rollbacks = 0
        self.commits = 0

    @property
    def info(self):
        return InfoFalsa(self._estado)

    @property
    def autocommit(self):
        return self._autocommit

    @autocommit.setter
    def autocommit(self, valor):
        raise AssertionError(
            'refrescar_vistas NO debe tocar el autocommit de la conexion: '
            'esa era la causa del rojo del 25-ago y ya no hace falta')

    def commit(self):
        self.commits += 1
        self._estado = psycopg2.extensions.TRANSACTION_STATUS_IDLE
        self._cur.abortada = False

    def rollback(self):
        self.rollbacks += 1
        self._estado = psycopg2.extensions.TRANSACTION_STATUS_IDLE
        self._cur.abortada = False

    def cursor(self):
        return self._cur


def corre(cur, fuente='ledger', con=None):
    """Devuelve (resultado, lineas escritas, conexion)."""
    con = con if con is not None else ConexionFalsa(cur)
    lineas = []
    r = refrescar_vistas(con, fuente, escribir=lambda t: lineas.append(str(t)))
    return r, '\n'.join(lineas), con


def refrescos(cur):
    return [e for e in cur.ejecutadas if 'refresh materialized view' in e.lower()]


def pos_trackeador(cur):
    for i, e in enumerate(cur.ejecutadas):
        if 'fn_trackeador_refrescar' in e.lower():
            return i
    return -1


print('== 1) EL CAMINO BUENO ==')
c = CursorFalso()
r, txt, con = corre(c)
eq('(1) devuelve True', r, True)
eq('(1) ha refrescado de verdad', len(refrescos(c)), 2)   # ledger: ventanas + presencia
# 🔒 Sin el indice unico esto bloquearia a quien este leyendo la pantalla.
eq('(1) … sin bloquear a los lectores',
   all('concurrently' in e.lower() for e in refrescos(c)), True)
# 🔴 Anclado en el ROTULO de esa linea, no en el valor: `postgres` sale TAMBIEN en la
#    linea del dueno, asi que buscarlo daba verde con la linea borrada. Cazado
#    rompiendolo. Es el patron de siempre: un assert que busca algo que aparece en dos
#    sitios no distingue cual de los dos falta.
eq('(1) 🔴 registra current_user SIEMPRE, no solo al fallar', 'conectado como' in txt, True)
eq('(1) … y dice cuanto tardo', 'ms' in txt, True)
eq('(1) 🔒 avisa a la app', '/api/cache/invalidar' in txt, True)
# 🔴 CADA COPIA EN SU PROPIA TRANSACCION: sin commit por copia, un REFRESH fallido
#    abortaria la transaccion entera y todo lo de detras reventaria con "current
#    transaction is aborted". Anclado sobre el RECUENTO, no sobre "hubo algun commit".
# Uno por el sondeo inicial, uno por cada copia, y uno del trackeador. EXACTO, no
# ">=": con un solo commit al final el ">=" salia verde igual (medido rompiendolo).
eq('(1) 🔴 confirma cada copia por separado', con.commits, len(refrescos(c)) + 2)
eq('(1) 🔒 y no deshace nada', con.rollbacks, 0)

print('\n== 2) LA MV NO EXISTE TODAVIA (la migracion no se ha aplicado) ==')
c = CursorFalso(existe=False)
r, txt, _ = corre(c)
eq('(2) 🔴 devuelve False', r, False)
eq('(2) 🔴 … y NO intenta refrescar', len(refrescos(c)), 0)
eq('(2) … diciendo que la migracion falta', 'no se ha aplicado' in txt.lower(), True)
# 🔴 Y lo que NO tiene que decir: que la carga haya fallado. El informe ya esta escrito.
eq('(2) 🔒 … y aclarando que la carga SI esta hecha',
   'el informe ya esta escrito' in txt.lower(), True)
eq('(2) 🔴 NO avisa a la app', '/api/cache/invalidar' in txt, False)
# 🔴 UNA COPIA QUE FALTA NO PUEDE LLEVARSE POR DELANTE AL TRACKEADOR. Es la razon de
#    ser del commit por copia: si compartieran transaccion, este caso la dejaria
#    abortada y el trackeador ni se intentaria.
eq('(2) 🔴 … pero el trackeador SI se refresca igual', pos_trackeador(c) >= 0, True)

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
# 🔴 El REFRESH fallido se DESHACE, para no dejar la transaccion abortada detras.
eq('(3) 🔴 deshace la suya y sigue', con.rollbacks >= 1, True)
eq('(3) 🔴 … y el trackeador se refresca igual', pos_trackeador(c) >= 0, True)

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

print('\n== 3c) LLAMADO CON UNA TRANSACCION ABIERTA ==')
# 🔴 EL MOTIVO CAMBIO EL 25-ago-2026 Y ES MAS FUERTE QUE EL DE ANTES. Antes se decia
#    "refrescar exige salir de la transaccion", y era FALSO: `REFRESH ... CONCURRENTLY`
#    corre dentro de un BEGIN sin problema (lo que se vio entonces fue una queja de
#    psycopg2 al cambiar el modo de la sesion, no de Postgres al refrescar).
#    El motivo bueno es que aqui dentro hay `commit()`, y una transaccion abierta
#    significa que quien llamo tenia trabajo SIN CONFIRMAR: ese commit se lo
#    confirmaria por la espalda. Peor todavia que el rollback que ya se descarto.
# 🔑 La conservadora es la misma: gritar, devolver False y no tocar NADA.
c = CursorFalso()
con_sucia = ConexionFalsa(c, estado=psycopg2.extensions.TRANSACTION_STATUS_INTRANS)
r, txt, con_sucia = corre(c, con=con_sucia)
eq('(3c) 🔴 con transaccion abierta NO revienta', r is not None, True)
eq('(3c) 🔴 … y RENUNCIA (devuelve False)', r, False)
eq('(3c) 🔴 … SIN confirmar trabajo ajeno', con_sucia.commits, 0)
eq('(3c) 🔴 … y SIN deshacerlo tampoco', con_sucia.rollbacks, 0)
eq('(3c) … diciendo por que', 'TRANSACCION ABIERTA' in txt, True)
eq('(3c) … y que la copia se queda vieja', 'centinela' in txt, True)
eq('(3c) 🔴 NO avisa a la app', '/api/cache/invalidar' in txt, False)
eq('(3c) 🔒 … y no ha tocado la base', c.ejecutadas, [])

print('\n== 4) UNA FUENTE QUE NO TIENE MATERIALIZADAS ==')
# 🔴 ESTE CASO CAMBIO DE SIGNO EL 25-ago-2026, Y ES LO QUE HACE QUE EL TRACKEADOR VEA
#    EL KEEPA DE LA MANANA. Antes se salia CALLADO por la puerta de atras. Pero
#    `v_trackeador_pantalla` bebe de nueve tablas --entre ellas keepa_escaparate--, o
#    sea de informes que NO tienen materializada propia. Si el gancho se saltase esas
#    fuentes, su pestana seguiria ensenando la foto de ayer.
c = CursorFalso()
r, txt, con = corre(c, fuente='keepa')
eq('(4) 🔴 el trackeador se refresca IGUAL', pos_trackeador(c) >= 0, True)
eq('(4) 🔒 … pero no refresca ninguna materializada nuestra', len(refrescos(c)), 0)
eq('(4) devuelve True', r, True)
# 🔒 Y no avisa de NADA a la app: esta fuente no tiene etiquetas porque no tiene copias.
eq('(4) 🔒 avisa sin etiquetas nuestras',
   'inventario' in txt or 'ventas' in txt or 'rentabilidad' in txt, False)

print('\n== 5) EL MAPA FUENTE -> MATERIALIZADAS ==')
# 🔴 Anclado sobre lo que tiene que estar: las tres fuentes de v_ventas_ventanas.
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

# 🔴 LA TERCERA COPIA. `mv_presencia_pais` agrega SOLO `ledger_movimientos`: ni un
#    join, ni una funcion, ni CURRENT_DATE. Una sola fuente y una sola ancla.
eq('(5) 🔴 el ledger refresca TAMBIEN la presencia por pais',
   'mv_presencia_pais' in REFRESCOS_POR_FUENTE.get('ledger', ()), True)
# 🔒 Anclado sobre lo que NO debe aparecer: colgarla de transacciones o de listings
#    seria refrescar por un evento que no la toca, y el dato saldria bien igual --
#    o sea que nadie lo notaria.
eq('(5) 🔒 … y NADIE MAS la refresca',
   sorted(f for f, vs in REFRESCOS_POR_FUENTE.items() if 'mv_presencia_pais' in vs),
   ['ledger'])

# 🔴 LA CUARTA COPIA, Y ES LA UNICA QUE NO ES UNA VISTA ENTERA: `mv_asin_con_pedido`
#    guarda SOLO la rama cara de v_nunca_enviado_fba (el 97% del coste). Bebe de DOS
#    fuentes, y `listings` no es adorno: es el mapa SKU->ASIN. Sin refrescarla al
#    entrar un informe de listings, un SKU que cambia de ASIN deja de contar como
#    "tuvo pedido" y su ficha aparece como NUNCA ENVIADA.
eq('(5) 🔴 las transacciones refrescan la lista de ASIN con pedido',
   'mv_asin_con_pedido' in REFRESCOS_POR_FUENTE.get('transacciones', ()), True)
eq('(5) 🔴 … y listings TAMBIEN (es el mapa SKU->ASIN)',
   'mv_asin_con_pedido' in REFRESCOS_POR_FUENTE.get('listings', ()), True)
# 🔒 Anclado sobre lo que NO debe aparecer: el ledger no la toca.
eq('(5) 🔒 … y el ledger NO la refresca',
   sorted(f for f, vs in REFRESCOS_POR_FUENTE.items() if 'mv_asin_con_pedido' in vs),
   ['listings', 'transacciones'])

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

print('\n== 5c) EL TRACKEADOR: AL FINAL, Y SU FALLO NO ES MUDO ==')
c = CursorFalso()
_, txt, _ = corre(c, fuente='transacciones')
# 🔴 DESPUES de las nuestras, no antes: su vista lee las mismas tablas, asi que
#    ponerla primero la dejaria mirando la foto anterior. Aqui el ORDEN es lo que se
#    esta probando, asi que compararlo por posicion es lo correcto.
eq('(5c) 🔴 va DESPUES de todas las nuestras',
   pos_trackeador(c) > max(c.ejecutadas.index(e) for e in refrescos(c)), True)
eq('(5c) 🔒 … y en modo "no relances" (false)',
   'false' in c.ejecutadas[pos_trackeador(c)].lower(), True)
eq('(5c) dice cuanto tardo y que devolvio', 'trackeador refrescado en' in txt, True)

# 🔴 LA MITAD QUE SE OLVIDA: con `false`, la funcion SE TRAGA su excepcion y devuelve
#    'ERROR: ...' COMO VALOR NORMAL. Mirar solo "no ha lanzado" daria verde sobre un
#    refresco fallido -- una comprobacion que no puede fallar.
c = CursorFalso(trackeador='ERROR: refresco sospechoso: solo 3 filas')
r, txt, _ = corre(c, fuente='transacciones')
eq('(5c) 🔴 un ERROR devuelto como TEXTO cuenta como fallo', r, False)
eq('(5c) … y se ve el motivo', 'solo 3 filas' in txt, True)
eq('(5c) 🔴 … y NO avisa a la app', '/api/cache/invalidar' in txt, False)

# 🔒 Y si revienta de verdad, tampoco tumba la corrida ni se lleva a las nuestras.
c = CursorFalso(trackeador_revienta=psycopg2.errors.InsufficientPrivilege(
    'permission denied for function fn_trackeador_refrescar'))
r, txt, con = corre(c, fuente='transacciones')
eq('(5c) 🔒 si revienta, devuelve False sin tumbar nada', r, False)
eq('(5c) 🔒 … diciendo el error', 'permission denied' in txt, True)
eq('(5c) 🔒 … y las nuestras SI se habian refrescado', len(refrescos(c)), 3)   # transacciones: ventanas + rentabilidad + asin_con_pedido

print('\n== 6) LOS PROCESADORES LO LLAMAN DE VERDAD ==')
# 🔴 Un CI verde no prueba que una feature este viva. `refrescar_vistas` puede estar
#    perfecta y no ejecutarse nunca.
# ⚠️ Sobre el codigo SIN comentarios: la cabecera del gancho NOMBRA la funcion, asi
#    que un grep sobre el fichero crudo daria verde con la llamada borrada.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))


def sin_almohadillas(texto):
    return '\n'.join(l for l in texto.split('\n') if not l.lstrip().startswith('#'))


for fichero, fuente in (('procesador_ledger.py', 'ledger'),
                        ('procesador_transacciones.py', 'transacciones'),
                        ('procesador_all_listings.py', 'listings'),
                        ('procesador_keepa_escaparate.py', 'keepa')):
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
       codigo.count('refrescar_vistas('), 1)

print('')
if fallos:
    print('%d FALLOS: %s' % (len(fallos), ', '.join(fallos)))
    sys.exit(1)
print('TODO OK · gancho del refresco de copias')
