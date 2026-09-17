# -*- coding: utf-8 -*-
# ============================================================================
# LA PODA DE s3://moloka-backups/bd/ — LOS VOLCADOS DE LA v1, SIN RETENCION
# ----------------------------------------------------------------------------
# QUE HACE
#   `backup-bd.yml` llevaba desde el 14-jul-2026 subiendo un volcado por noche
#   a `bd/` sin que nada los recortara nunca (71 volcados medidos el
#   17-sep-2026, ~27 MB cada uno y subiendo). Al apagar su `schedule` (mismo
#   PR) esa acumulacion se para, pero lo que ya hay sigue ahi. Este script
#   decide QUE se conserva y QUE se borra; el workflow (`podar-copia-bd.yml`)
#   es quien de verdad toca R2.
#
# LA REGLA, LITERAL (Fernando, 17-sep-2026): conservar TRES copias — la mas
# cercana a hace 7 dias, a hace 15 y a hace 21, contados desde el dia en que
# se ejecuta — y borrar TODAS las demas de `bd/`.
#
# 🔒 SOLO DECIDE. No lee R2 ni lo toca: recibe por stdin lo que el workflow ya
#    listo (`nombre\tbytes`, uno por linea, de `aws s3 ls s3://.../bd/`), y dice
#    que conservar y que borrar. El propio `aws s3 rm` lo dispara el workflow,
#    igual que separa `carear_r2.py` de la subida en la v2 (`copia-r2.yml`).
#
# GUARDAS (no se toca nada si salta cualquiera de las dos):
#   · Menos de 4 objetos bajo bd/ -> no hay nada razonable que podar.
#   · Cualquier objeto bajo bd/ que NO tenga el nombre de un volcado
#     (`moloka_AAAA-MM-DD_HHMM.sql.gz`) -> se para y se dice CUAL, en vez de
#     ignorarlo en silencio (al reves que la poda de la v2, que si lo ignora:
#     aqui la regla la pidio Fernando mas estricta a proposito).
#
# EMPATES en "mas cercana a hace N dias": primero por dia (fecha, sin hora),
# luego por la hora completa, y si sigue empatado el mas antiguo por nombre
# (que en este formato es tambien el mas antiguo por fecha). Un mismo volcado
# puede ser el mas cercano para dos offsets a la vez: entonces se conservan
# MENOS de tres ficheros, y el informe lo dice.
# ============================================================================

import io
import os
import re
import sys
from datetime import datetime, timedelta, timezone

PATRON = re.compile(r'^moloka_(\d{4})-(\d{2})-(\d{2})_(\d{4})\.sql\.gz$')
OFFSETS = (7, 15, 21)


# ---------------------------------------------------------------------------
# 1) LA LOGICA PURA — sin red, para el banco de pruebas (test_podar_copia_bd.py)
# ---------------------------------------------------------------------------

def parsear_nombre(nombre):
    """`moloka_AAAA-MM-DD_HHMM.sql.gz` -> datetime (naive, UTC) · None si no casa."""
    m = PATRON.match(nombre or '')
    if not m:
        return None
    aaaa, mm, dd, hhmm = m.groups()
    try:
        return datetime(int(aaaa), int(mm), int(dd), int(hhmm[:2]), int(hhmm[2:]))
    except ValueError:
        return None


def analizar_listado(lineas):
    """[(nombre, tam), ...] -> (volcados, invalidos).

    `volcados`  : [{'nombre','fecha','tam'}, ...], solo los que CASAN el
                  patron del volcado.
    `invalidos` : nombres bajo bd/ que NO casan — un solo invalido basta para
                  que `construir_plan` no borre nada (ver la cabecera)."""
    volcados, invalidos = [], []
    for nombre, tam in lineas:
        fecha = parsear_nombre(nombre)
        if fecha is None:
            invalidos.append(nombre)
            continue
        volcados.append({'nombre': nombre, 'fecha': fecha, 'tam': tam})
    return volcados, invalidos


def elegir_conservar(volcados, hoy, offsets=OFFSETS):
    """{offset: volcado-mas-cercano-o-None}. `hoy` es un `date` (sin hora):
    "contados desde el dia en que se ejecuta", literal."""
    elegido = {}
    for offset in offsets:
        objetivo = hoy - timedelta(days=offset)
        mejor_clave, mejor_v = None, None
        for v in volcados:
            dist_dias = abs((v['fecha'].date() - objetivo).days)
            dist_segundos = abs((v['fecha'] - datetime.combine(objetivo, datetime.min.time())).total_seconds())
            clave = (dist_dias, dist_segundos, v['nombre'])
            if mejor_clave is None or clave < mejor_clave:
                mejor_clave, mejor_v = clave, v
        elegido[offset] = mejor_v
    return elegido


def construir_plan(volcados, invalidos, hoy, minimo=4, offsets=OFFSETS):
    """La guarda + la retencion, juntas.

    Devuelve {'ok', 'motivo', 'conservar', 'borrar'}. `conservar` y `borrar`
    son listas de dict con 'nombre','fecha','tam' — `conservar` lleva ademas
    'offsets' (para que el informe diga POR QUE se queda cada uno)."""
    if invalidos:
        return {'ok': False,
                'motivo': (f"{len(invalidos)} objeto(s) bajo bd/ no tienen el nombre de un "
                           f"volcado (moloka_AAAA-MM-DD_HHMM.sql.gz): " + ', '.join(sorted(invalidos))),
                'conservar': [], 'borrar': []}
    if len(volcados) < minimo:
        return {'ok': False,
                'motivo': f"solo hay {len(volcados)} volcado(s) bajo bd/ (minimo {minimo}); no se toca nada.",
                'conservar': [], 'borrar': []}

    elegido = elegir_conservar(volcados, hoy, offsets)
    por_nombre = {}
    for offset in offsets:
        v = elegido.get(offset)
        if v is None:
            continue
        entrada = por_nombre.setdefault(v['nombre'], dict(v, offsets=[]))
        entrada['offsets'].append(offset)
    conservar = sorted(por_nombre.values(), key=lambda v: v['fecha'])
    nombres_conservar = set(por_nombre)
    borrar = sorted((v for v in volcados if v['nombre'] not in nombres_conservar),
                    key=lambda v: v['fecha'])
    return {'ok': True, 'motivo': '', 'conservar': conservar, 'borrar': borrar}


# ---------------------------------------------------------------------------
# 2) LA PARTE QUE TOCA EL MUNDO — leer stdin, escribir el informe y la lista
# ---------------------------------------------------------------------------

def _leer_lineas(fh):
    """`nombre\\tbytes` por linea -> [(nombre, tam), ...]. Lineas raras (sin
    tabulador, tamano no numerico) se DICEN y no entran silenciosamente."""
    lineas, raras = [], []
    for cruda in fh:
        cruda = cruda.rstrip('\n')
        if not cruda:
            continue
        partes = cruda.split('\t')
        if len(partes) != 2:
            raras.append(cruda)
            continue
        nombre, tam = partes
        try:
            lineas.append((nombre, int(tam)))
        except ValueError:
            raras.append(cruda)
    return lineas, raras


def _fmt_mb(bytes_):
    return f"{bytes_ / 1_048_576:.2f} MB"


def main():
    lineas, raras = _leer_lineas(sys.stdin)
    # Una linea que no se puede leer es exactamente el caso que la guarda de
    # "fecha no se puede leer del nombre" existe para cazar: se trata como un
    # invalido mas, no se descarta en silencio.
    volcados, invalidos = analizar_listado(lineas)
    invalidos = invalidos + raras

    hoy_str = os.environ.get('HOY', '')
    if hoy_str:
        hoy = datetime.strptime(hoy_str, '%Y-%m-%d').date()
    else:
        hoy = datetime.now(timezone.utc).date()

    print(f"--- LISTADO (bd/) --- hoy={hoy.isoformat()}", flush=True)
    print(f"    objetos vistos: {len(lineas)} · volcados validos: {len(volcados)} · "
          f"invalidos: {len(invalidos)}", flush=True)

    plan = construir_plan(volcados, invalidos, hoy)

    salida_borrar = os.environ.get('SALIDA_BORRAR', '')
    if not plan['ok']:
        print(f"\n❌ GUARDA: {plan['motivo']}", flush=True)
        print("No se borra nada.", flush=True)
        if salida_borrar:
            io.open(salida_borrar, 'w', encoding='utf-8').close()
        sys.exit(1)

    print(f"\n--- CONSERVAR ({len(plan['conservar'])}) ---", flush=True)
    for v in plan['conservar']:
        offs = ','.join(f"~{o}d" for o in v['offsets'])
        print(f"    · {v['nombre']}  ·  {v['fecha'].isoformat()}  ·  "
              f"{_fmt_mb(v['tam'])}  ·  mas cercano a {offs}", flush=True)

    total_borrar = sum(v['tam'] for v in plan['borrar'])
    print(f"\n--- BORRAR ({len(plan['borrar'])}) --- total {_fmt_mb(total_borrar)}", flush=True)
    for v in plan['borrar']:
        print(f"    · {v['nombre']}  ·  {v['fecha'].isoformat()}  ·  {_fmt_mb(v['tam'])}", flush=True)
    if not plan['borrar']:
        print("    (nada que podar)", flush=True)

    if salida_borrar:
        with io.open(salida_borrar, 'w', encoding='utf-8') as fh:
            for v in plan['borrar']:
                fh.write(v['nombre'] + '\n')

    sys.exit(0)


if __name__ == '__main__':
    main()
