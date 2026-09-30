# -*- coding: utf-8 -*-
"""«EN MI BD» CON EL STOCK DE VERDAD · la columna que dice qué tenemos ya de un producto (encargo E, 30-sep-2026).

UNA SOLA FUNCION PARA TODOS: el escaner viejo (moloka_escaner_nube.py), el Pro (moloka_escaner_pro.py, que lo
llama moloka_escaner_pro_nube.py) y el escaner 2 (escaner2_motor.py: cruce de HEO y novedades) escriben la
columna con `texto_en_mi_bd`. Hasta hoy cada uno la armaba a mano con `productos.stock_fba`.

🔴 EL FALLO QUE CIERRA. `productos.stock_fba` esta CONGELADO: solo lo escribia `moloka_actualizar_nube.py`
   (workflow actualizar-app.yml, sin reloj; su ultima corrida es del 22-jul-2026). Medido en produccion el
   30-sep-2026: de 523 fichas activas con ASIN, 314 tienen un `stock_fba` distinto del disponible de la ultima
   foto de `inventario_fba`, y 155 dicen 0 con Amazon teniendo stock (2.346 uds). Caso: Claptrap (B0DP7C737P,
   EAN 889698882774): `stock_fba` 0 desde el 16-ago, foto del 30-sep con 18 disponibles. El Excel decia
   «OK Alm:0 FBA:0», o sea «no hay nada en Amazon», y era mentira.

LAS DOS FUENTES:
  · Almacen = `productos.stock_moloka`: la MISMA que enseña la v2 en Inventario y Cockpit
    (moloka-app-v2, lib/inventory/build.ts:3109, columna pedida en lib/inventory/query.ts:77). No la
    escribe nadie a mano: la deriva el trigger `trg_sync_stock_moloka` de las baldas (`ubicaciones_cant`);
    medido el 30-sep-2026, 0 fichas descuadradas.
  · FBA = `available + fc_transfer` de la ULTIMA `fecha_foto` de `inventario_fba`, SUMADO POR ASIN (el
    criterio de la casa para el disponible; la llave de la capa Amazon es el ASIN, nunca el SKU: un ASIN
    con dos vidas de SKU suma las dos). «+N en camino» = `inbound_shipped + inbound_receiving`.

🔒 AUSENCIA DE DATO NO ES CERO:
  · ficha sin ASIN (o chase: nunca lleva ASIN) → «FBA: —»;
  · ASIN que no esta en la foto → «FBA: — (foto …)»;
  · foto que no se pudo leer → «FBA: sin foto»;
  · foto de hace mas de DIAS_FOTO_VIEJA dias → «FBA: foto vieja del DD-MM», sin cifra: un informe
    caducado no da informacion incompleta, da informacion FALSA. El log lo avisa y el run SIGUE.
  · ficha sin `stock_moloka` (la consulta no lo pidio, o es nulo) → «Alm: —».

Sin red y sin base: `leer_foto_fba` recibe el cliente de Supabase del programa que llama (con su llave) y
NUNCA LANZA; lo demas son funciones puras.
"""
from datetime import date, datetime

TABLA_FOTO = 'inventario_fba'
COLUMNAS_FOTO = 'sku,asin,available,fc_transfer,inbound_shipped,inbound_receiving,fecha_foto'
DIAS_FOTO_VIEJA = 2
RAYA = '—'


def hoy_madrid():
    """La fecha de hoy en España (los runners de Actions van en UTC)."""
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('Europe/Madrid')).date()


def _fecha(v):
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _n(v):
    return int(v) if v not in (None, '') else 0


def foto_de_filas(filas, fecha, hoy=None, error=None):
    """La foto de FBA ya sumada: {'fecha', 'edad', 'vieja', 'por_asin': {asin: {'disponible', 'en_camino'}},
    'filas', 'error'}. `filas` son las de `inventario_fba` de ESA fecha; se suman por ASIN (las filas sin ASIN
    no casan con ninguna ficha y se cuentan aparte, en 'sin_asin')."""
    fecha = _fecha(fecha)
    hoy = hoy or hoy_madrid()
    por_asin, sin_asin = {}, 0
    for f in filas or []:
        asin = (f.get('asin') or '').strip()
        if not asin:
            sin_asin += 1
            continue
        a = por_asin.setdefault(asin, {'disponible': 0, 'en_camino': 0})
        a['disponible'] += _n(f.get('available')) + _n(f.get('fc_transfer'))
        a['en_camino'] += _n(f.get('inbound_shipped')) + _n(f.get('inbound_receiving'))
    edad = (hoy - fecha).days if fecha else None
    return {'fecha': fecha, 'edad': edad, 'vieja': edad is not None and edad > DIAS_FOTO_VIEJA,
            'por_asin': por_asin, 'filas': len(filas or []), 'sin_asin': sin_asin, 'error': error}


def leer_foto_fba(sb, hoy=None, imprimir=print):
    """La ultima foto de `inventario_fba`, sumada por ASIN (`foto_de_filas`). NUNCA LANZA: si no se puede leer,
    devuelve una foto sin fecha y con el motivo en 'error', y la columna dira «sin foto». Deja en el log la linea
    FOTO_FBA (fecha, filas, ASIN, edad) y un AVISO si la foto no se pudo leer o es vieja."""
    try:
        res = sb.table(TABLA_FOTO).select('fecha_foto').order('fecha_foto', desc=True).limit(1).execute()
        fecha = _fecha((res.data or [{}])[0].get('fecha_foto'))
        filas = []
        if fecha is not None:
            desde = 0
            while True:
                pagina = (sb.table(TABLA_FOTO).select(COLUMNAS_FOTO).eq('fecha_foto', fecha.isoformat())
                          .order('sku').range(desde, desde + 999).execute().data or [])
                filas.extend(pagina)
                if len(pagina) < 1000:
                    break
                desde += 1000
        foto = foto_de_filas(filas, fecha, hoy, error=None if fecha else '%s no tiene ninguna foto' % TABLA_FOTO)
    except Exception as ex:
        foto = foto_de_filas([], None, hoy, error='%s: %s' % (type(ex).__name__, ex))
    for linea in lineas_log(foto):
        imprimir(linea)
    return foto


def lineas_log(foto):
    """Lo que el programa deja en el log sobre la foto que va a usar la columna «En mi BD»."""
    if not foto or foto.get('fecha') is None:
        motivo = (foto or {}).get('error') or 'no se leyó'
        return ['FOTO_FBA: fecha=NINGUNA | filas=0',
                'AVISO FOTO_FBA ILEGIBLE (%s): la columna «En mi BD» dirá «FBA: sin foto». El escaneo sigue.' % motivo]
    salida = ['FOTO_FBA: fecha=%s | filas=%d | asins=%d | edad=%d días'
              % (foto['fecha'].isoformat(), foto['filas'], len(foto['por_asin']), foto['edad'])]
    if foto['vieja']:
        salida.append('AVISO FOTO_FBA VIEJA: la última foto de %s es del %s (%d días, el tope es %d): la columna '
                      '«En mi BD» dirá «FBA: foto vieja del %s». El escaneo sigue.'
                      % (TABLA_FOTO, foto['fecha'].isoformat(), foto['edad'], DIAS_FOTO_VIEJA,
                         foto['fecha'].strftime('%d-%m')))
    return salida


def texto_fba(ficha, foto):
    """La mitad FBA de la columna, para UNA ficha de `productos` (lee 'asin' y, si viene, 'es_chase')."""
    asin = (ficha.get('asin') or '').strip()
    if not asin or ficha.get('es_chase'):
        return 'FBA: ' + RAYA
    if not foto or foto.get('fecha') is None:
        return 'FBA: sin foto'
    if foto['vieja']:
        return 'FBA: foto vieja del %s' % foto['fecha'].strftime('%d-%m')
    sello = '(foto %s)' % foto['fecha'].isoformat()
    a = foto['por_asin'].get(asin)
    if a is None:
        return 'FBA: %s %s' % (RAYA, sello)
    camino = ' +%d en camino' % a['en_camino'] if a['en_camino'] > 0 else ''
    return 'FBA:%d%s %s' % (a['disponible'], camino, sello)


def texto_en_mi_bd(ficha, foto):
    """«OK Alm:X FBA:Y (foto AAAA-MM-DD)» para una ficha propia (la que el escaner ha encontrado por EAN).
    Sin ficha no hay nada que decir: ''."""
    if not ficha:
        return ''
    alm = ficha.get('stock_moloka')
    alm_txt = 'Alm:%d' % int(alm) if alm not in (None, '') else 'Alm: ' + RAYA
    return 'OK %s %s' % (alm_txt, texto_fba(ficha, foto))
