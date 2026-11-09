# -*- coding: utf-8 -*-
"""LA TABLA ÚNICA DE LOS NOMBRES DE COLUMNA DEL CSV DE KEEPA (encargo keepa-nombres-columnas, 9-nov-2026).

QUÉ PASÓ. Desde el 9-nov-2026 (el 8-nov aún entró con los nombres de siempre) el Visualizador de Keepa
en español llama distinto a 124 columnas. No hay columnas nuevas: es una equivalencia 1 a 1 y en el mismo
orden, y desaparece una que venía vacía («Clasificación de Ventas: Histórico»). Además cambian dos formatos
de valor. Medido columna a columna sobre los cuatro export del 6-nov (561 columnas) y los cuatro del 9-nov
(560), comparando por posición.

QUÉ HACE ESTO. Devuelve el fichero a LOS NOMBRES Y FORMATOS DE SIEMPRE justo al leerlo, antes de mirar
ninguna columna. Por eso `TIPADAS`, las claves de `keepa_escaparate.crudo` y las vistas que leen
`crudo ->> '…'` (v_escaparate, v_suficiencia_decision) no cambian ni una letra, y el histórico sigue
siendo homogéneo. Lo usan los dos sitios que leen el CSV: procesador_keepa_escaparate.py y el escáner 2
(escaner2_motor._leer_crudo y el lector heredado, por su desvío en escaner2_desvios.py).

🔒 LA TABLA ES LITERAL, NO UNA REGLA DE «CAMBIA BUY BOX POR CAJA DE COMPRA». Es la regla de la casa que mató al
   PR #26 («ningún encabezado se conjetura») y aquí además sería falsa, dos veces:
     · «Comisión de referencia basada en el precio actual de la Buy Box» se llamaba ya así y NO se traduce;
     · las 19 columnas «Caja de Compra Usado: …» NO han cambiado de nombre.
   Una columna que Keepa añada mañana con «Buy Box» en el nombre se guarda con su nombre, sin inventarle otro.

🔒 UN FICHERO DE ANTES SIGUE ENTRANDO IGUAL: ningún nombre antiguo está en la tabla como clave.
"""
from decimal import Decimal, InvalidOperation

# 🔑 NUEVO → ANTIGUO. Generada de los ficheros reales, en el orden en que aparecen en el CSV.
EQUIVALENCIAS = {
    'Buy Box: Actual': 'Caja de Compra: Actual',
    'Buy Box: Gastos de envío': 'Caja de Compra: Gastos de envío',
    'Buy Box: Promedio de 30 días': 'Caja de Compra: Promedio de 30 días',
    'Buy Box: Promedio de 90 días': 'Caja de Compra: Promedio de 90 días',
    'Buy Box: Promedio de 180 días': 'Caja de Compra: Promedio de 180 días',
    'Buy Box: Promedio de 365 días': 'Caja de Compra: Promedio de 365 días',
    'Buy Box: Caída de 1 día %': 'Caja de Compra: Caída de 1 día %',
    'Buy Box: Caída de 7 días %': 'Caja de Compra: Caída de 7 días %',
    'Buy Box: Caída de 30 días %': 'Caja de Compra: Caída de 30 días %',
    'Buy Box: Caída de 90 días %': 'Caja de Compra: Caída de 90 días %',
    'Buy Box: Caída desde la última visita': 'Caja de Compra: Caída desde la última visita',
    'Buy Box: Caída % desde la última visita': 'Caja de Compra: Caída % desde la última visita',
    'Buy Box: Última visita': 'Caja de Compra: Última visita',
    'Buy Box: Es el mínimo': 'Caja de Compra: Es el mínimo',
    'Buy Box: Es el mínimo en 90 días': 'Caja de Compra: Es el mínimo en 90 días',
    'Buy Box: El más bajo': 'Caja de Compra: El más bajo',
    'Buy Box: El más alto': 'Caja de Compra: El más alto',
    'Buy Box: Stock': 'Caja de Compra: Stock',
    'Buy Box: 90 días A.G.': 'Caja de Compra: 90 días A.G.',
    'Buy Box: Vendedor Buy Box': 'Caja de Compra: Vendedor Caja de Compra',
    'Buy Box: País de envío': 'Caja de Compra: País de envío',
    'Buy Box: Disponibilidad de la Buy Box': 'Caja de Compra: Disponibilidad de la Caja de Compra',
    'Buy Box: Tiempo de envío': 'Caja de Compra: Tiempo de envío',
    'Buy Box: Precio tachado': 'Caja de Compra: Precio tachado',
    'Buy Box: Tipo de precio tachado': 'Caja de Compra: Tipo de precio tachado',
    'Buy Box: % Amazon 30 días': 'Caja de Compra: % Amazon 30 días',
    'Buy Box: % Amazon 90 días': 'Caja de Compra: % Amazon 90 días',
    'Buy Box: % Amazon 180 días': 'Caja de Compra: % Amazon 180 días',
    'Buy Box: % Amazon 365 días': 'Caja de Compra: % Amazon 365 días',
    'Buy Box: % Mejor vendedor 30 días': 'Caja de Compra: % Mejor vendedor 30 días',
    'Buy Box: % Mejor vendedor 90 días': 'Caja de Compra: % Mejor vendedor 90 días',
    'Buy Box: % Mejor vendedor 180 días': 'Caja de Compra: % Mejor vendedor 180 días',
    'Buy Box: % Mejor vendedor 365 días': 'Caja de Compra: % Mejor vendedor 365 días',
    'Buy Box: Recuento de ganadores 30 días': 'Caja de Compra: Recuento de ganadores 30 días',
    'Buy Box: Recuento de ganadores 90 días': 'Caja de Compra: Recuento de ganadores 90 días',
    'Buy Box: Recuento de ganadores 180 días': 'Caja de Compra: Recuento de ganadores 180 días',
    'Buy Box: Recuento de ganadores 365 días': 'Caja de Compra: Recuento de ganadores 365 días',
    'Buy Box: Desviación estándar 30 días': 'Caja de Compra: Desviación estándar 30 días',
    'Buy Box: Desviación estándar 90 días': 'Caja de Compra: Desviación estándar 90 días',
    'Buy Box: Desviación estándar 365 días': 'Caja de Compra: Desviación estándar 365 días',
    'Buy Box: Capacidad de cambio 30 días': 'Caja de Compra: Capacidad de cambio 30 días',
    'Buy Box: Capacidad de cambio 90 días': 'Caja de Compra: Capacidad de cambio 90 días',
    'Buy Box: Capacidad de cambio 365 días': 'Caja de Compra: Capacidad de cambio 365 días',
    'Buy Box: Es FBA': 'Caja de Compra: Es FBA',
    'Buy Box: No calificado': 'Caja de Compra: No calificado',
    'Buy Box: Pre-ordenado': 'Caja de Compra: Pre-ordenado',
    'Buy Box: Pedido pendiente': 'Caja de Compra: Pedido pendiente',
    'Buy Box: Exclusivo Prime': 'Caja de Compra: Exclusivo Prime',
    'Buy Box: Prime elegible': 'Caja de Compra: Prime elegible',
    'Buy Box: Compra recurrente': 'Caja de Compra: Compra recurrente',
    'Recuento de ofertas elegibles para la Buy Box: Nuevo FBA': 'Recuento de ofertas elegibles para la Caja de Compra: Nuevo FBA',
    'Recuento de ofertas elegibles para la Buy Box: Nuevo FBM': 'Recuento de ofertas elegibles para la Caja de Compra: Nuevo FBM',
    'Recuento de ofertas elegibles para la Buy Box: Usado FBA': 'Recuento de ofertas elegibles para la Caja de Compra: Usado FBA',
    'Recuento de ofertas elegibles para la Buy Box: Usado FBM': 'Recuento de ofertas elegibles para la Caja de Compra: Usado FBM',
    'Recuento de ofertas elegibles para la Buy Box: De coleccionista FBA': 'Recuento de ofertas elegibles para la Caja de Compra: De coleccionista FBA',
    'Recuento de ofertas elegibles para la Buy Box: De coleccionista FBM': 'Recuento de ofertas elegibles para la Caja de Compra: De coleccionista FBM',
    'Recuento de ofertas elegibles para la Buy Box: Reacondicionado FBA': 'Recuento de ofertas elegibles para la Caja de Compra: Reacondicionado FBA',
    'Recuento de ofertas elegibles para la Buy Box: Reacondicionado FBM': 'Recuento de ofertas elegibles para la Caja de Compra: Reacondicionado FBM',
    'Nuevo, terceros FBA: Actual': 'Nuevo, de Vendedor Externo FBA: Actual',
    'Nuevo, terceros FBA: Promedio de 30 días': 'Nuevo, de Vendedor Externo FBA: Promedio de 30 días',
    'Nuevo, terceros FBA: Promedio de 90 días': 'Nuevo, de Vendedor Externo FBA: Promedio de 90 días',
    'Nuevo, terceros FBA: Promedio de 180 días': 'Nuevo, de Vendedor Externo FBA: Promedio de 180 días',
    'Nuevo, terceros FBA: Promedio de 365 días': 'Nuevo, de Vendedor Externo FBA: Promedio de 365 días',
    'Nuevo, terceros FBA: Caída de 1 día %': 'Nuevo, de Vendedor Externo FBA: Caída de 1 día %',
    'Nuevo, terceros FBA: Caída de 7 días %': 'Nuevo, de Vendedor Externo FBA: Caída de 7 días %',
    'Nuevo, terceros FBA: Caída de 30 días %': 'Nuevo, de Vendedor Externo FBA: Caída de 30 días %',
    'Nuevo, terceros FBA: Caída de 90 días %': 'Nuevo, de Vendedor Externo FBA: Caída de 90 días %',
    'Nuevo, terceros FBA: Caída desde la última visita': 'Nuevo, de Vendedor Externo FBA: Caída desde la última visita',
    'Nuevo, terceros FBA: Caída % desde la última visita': 'Nuevo, de Vendedor Externo FBA: Caída % desde la última visita',
    'Nuevo, terceros FBA: Última visita': 'Nuevo, de Vendedor Externo FBA: Última visita',
    'Nuevo, terceros FBA: Es el mínimo': 'Nuevo, de Vendedor Externo FBA: Es el mínimo',
    'Nuevo, terceros FBA: Es el mínimo en 90 días': 'Nuevo, de Vendedor Externo FBA: Es el mínimo en 90 días',
    'Nuevo, terceros FBA: El más bajo': 'Nuevo, de Vendedor Externo FBA: El más bajo',
    'Nuevo, terceros FBA: El más alto': 'Nuevo, de Vendedor Externo FBA: El más alto',
    'Nuevo, terceros FBA: Stock': 'Nuevo, de Vendedor Externo FBA: Stock',
    'Nuevo, terceros FBM: Actual': 'Nuevo, de Vendedor Externo FBM: Actual',
    'Nuevo, terceros FBM: Promedio de 30 días': 'Nuevo, de Vendedor Externo FBM: Promedio de 30 días',
    'Nuevo, terceros FBM: Promedio de 90 días': 'Nuevo, de Vendedor Externo FBM: Promedio de 90 días',
    'Nuevo, terceros FBM: Promedio de 180 días': 'Nuevo, de Vendedor Externo FBM: Promedio de 180 días',
    'Nuevo, terceros FBM: Promedio de 365 días': 'Nuevo, de Vendedor Externo FBM: Promedio de 365 días',
    'Nuevo, terceros FBM: Caída de 1 día %': 'Nuevo, de Vendedor Externo FBM: Caída de 1 día %',
    'Nuevo, terceros FBM: Caída de 7 días %': 'Nuevo, de Vendedor Externo FBM: Caída de 7 días %',
    'Nuevo, terceros FBM: Caída de 30 días %': 'Nuevo, de Vendedor Externo FBM: Caída de 30 días %',
    'Nuevo, terceros FBM: Caída de 90 días %': 'Nuevo, de Vendedor Externo FBM: Caída de 90 días %',
    'Nuevo, terceros FBM: Caída desde la última visita': 'Nuevo, de Vendedor Externo FBM: Caída desde la última visita',
    'Nuevo, terceros FBM: Caída % desde la última visita': 'Nuevo, de Vendedor Externo FBM: Caída % desde la última visita',
    'Nuevo, terceros FBM: Última visita': 'Nuevo, de Vendedor Externo FBM: Última visita',
    'Nuevo, terceros FBM: Es el mínimo': 'Nuevo, de Vendedor Externo FBM: Es el mínimo',
    'Nuevo, terceros FBM: Es el mínimo en 90 días': 'Nuevo, de Vendedor Externo FBM: Es el mínimo en 90 días',
    'Nuevo, terceros FBM: El más bajo': 'Nuevo, de Vendedor Externo FBM: El más bajo',
    'Nuevo, terceros FBM: El más alto': 'Nuevo, de Vendedor Externo FBM: El más alto',
    'Nuevo, terceros FBM: Stock': 'Nuevo, de Vendedor Externo FBM: Stock',
    'Warehouse Deals: Actual': 'Oferta de almacén: Actual',
    'Warehouse Deals: Promedio de 30 días': 'Oferta de almacén: Promedio de 30 días',
    'Warehouse Deals: Promedio de 90 días': 'Oferta de almacén: Promedio de 90 días',
    'Warehouse Deals: Promedio de 180 días': 'Oferta de almacén: Promedio de 180 días',
    'Warehouse Deals: Promedio de 365 días': 'Oferta de almacén: Promedio de 365 días',
    'Warehouse Deals: Caída de 1 día %': 'Oferta de almacén: Caída de 1 día %',
    'Warehouse Deals: Caída de 7 días %': 'Oferta de almacén: Caída de 7 días %',
    'Warehouse Deals: Caída de 30 días %': 'Oferta de almacén: Caída de 30 días %',
    'Warehouse Deals: Caída de 90 días %': 'Oferta de almacén: Caída de 90 días %',
    'Warehouse Deals: Caída desde la última visita': 'Oferta de almacén: Caída desde la última visita',
    'Warehouse Deals: Caída % desde la última visita': 'Oferta de almacén: Caída % desde la última visita',
    'Warehouse Deals: Última visita': 'Oferta de almacén: Última visita',
    'Warehouse Deals: Es el mínimo': 'Oferta de almacén: Es el mínimo',
    'Warehouse Deals: Es el mínimo en 90 días': 'Oferta de almacén: Es el mínimo en 90 días',
    'Warehouse Deals: El más bajo': 'Oferta de almacén: El más bajo',
    'Warehouse Deals: El más alto': 'Oferta de almacén: El más alto',
    'Precio recomendado: Actual': 'Lista de precio: Actual',
    'Precio recomendado: Promedio de 30 días': 'Lista de precio: Promedio de 30 días',
    'Precio recomendado: Promedio de 90 días': 'Lista de precio: Promedio de 90 días',
    'Precio recomendado: Promedio de 180 días': 'Lista de precio: Promedio de 180 días',
    'Precio recomendado: Promedio de 365 días': 'Lista de precio: Promedio de 365 días',
    'Precio recomendado: Caída de 1 día %': 'Lista de precio: Caída de 1 día %',
    'Precio recomendado: Caída de 7 días %': 'Lista de precio: Caída de 7 días %',
    'Precio recomendado: Caída de 30 días %': 'Lista de precio: Caída de 30 días %',
    'Precio recomendado: Caída de 90 días %': 'Lista de precio: Caída de 90 días %',
    'Precio recomendado: Caída desde la última visita': 'Lista de precio: Caída desde la última visita',
    'Precio recomendado: Caída % desde la última visita': 'Lista de precio: Caída % desde la última visita',
    'Precio recomendado: Última visita': 'Lista de precio: Última visita',
    'Precio recomendado: Es el mínimo': 'Lista de precio: Es el mínimo',
    'Precio recomendado: Es el mínimo en 90 días': 'Lista de precio: Es el mínimo en 90 días',
    'Precio recomendado: El más bajo': 'Lista de precio: El más bajo',
    'Precio recomendado: El más alto': 'Lista de precio: El más alto',
}

# ANTIGUO → NUEVO, solo para decir los dos nombres cuando falta una columna.
_NUEVO_DE = {antiguo: nuevo for nuevo, antiguo in EQUIVALENCIAS.items()}

# La que desaparece. 🔬 Vacía en las 2.405 filas de los cuatro export del 6-nov: nadie la lee, y `crudo` conserva la clave.
COLUMNA_RETIRADA = 'Clasificación de Ventas: Histórico'

# Los dos valores que cambian de formato, por su nombre ANTIGUO (la cabecera ya viene traducida).
COL_PLAZO_CAJA = 'Caja de Compra: Tiempo de envío'
COL_PRECIO_INFERIOR = 'Precio inferior sugerido'
PLAZO_SIN_DATO_NUEVO = '0 dia'

_BOM, _NBSP = chr(0xFEFF), chr(0xA0)


class CabeceraAmbigua(ValueError):
    """El fichero trae a la vez el nombre nuevo y el antiguo de una columna: no se elige."""


def _limpia(texto):
    return ('' if texto is None else str(texto)).replace(_BOM, '').replace(_NBSP, ' ').strip()


def nombre_para_aviso(antiguo):
    """Cómo se nombra una columna que falta: con los dos nombres si los tiene, para que el aviso sirva con
    cualquiera de los dos ficheros."""
    nuevo = _NUEVO_DE.get(antiguo)
    return "'%s' (o '%s')" % (antiguo, nuevo) if nuevo else "'%s'" % antiguo


def normalizar_cabecera(cabecera):
    """La cabecera con los nombres de siempre. Sin BOM ni espacios sobrantes.

    🔴 Si trae a la vez el nombre nuevo y el antiguo de una columna, CabeceraAmbigua: al traducir saldrían
       dos columnas con el mismo nombre y una taparía a la otra sin que nadie se enterase."""
    limpias = [_limpia(h) for h in cabecera]
    presentes = set(limpias)
    choques = [h for h in limpias if h in EQUIVALENCIAS and EQUIVALENCIAS[h] in presentes]
    if choques:
        raise CabeceraAmbigua('El CSV trae la misma columna con su nombre nuevo y con el antiguo: '
                              + ', '.join("'%s' y '%s'" % (h, EQUIVALENCIAS[h]) for h in choques)
                              + '. No se elige ninguna: vuelve a exportarlo de Keepa.')
    return [EQUIVALENCIAS.get(h, h) for h in limpias]


def normalizar_valor(cabecera_antigua, valor):
    """El valor con el formato de siempre. Solo toca las dos columnas que han cambiado; el resto, tal cual.

    · «Tiempo de envío» de la caja: antes vacío si no había plazo, ahora '0 dia'. 🔴 Solo ESTA columna:
      «Amazon: Retraso en el envío…» ya traía '0 dia' antes del cambio, y ahí es un dato.
    · «Precio inferior sugerido»: antes céntimos enteros (1898) y vacío; ahora euros (18.98) y '-'.
      Lo que no sean céntimos exactos se deja como viene: aquí no se redondea ni se adivina."""
    if cabecera_antigua == COL_PLAZO_CAJA:
        return '' if _limpia(valor) == PLAZO_SIN_DATO_NUEVO else valor
    if cabecera_antigua == COL_PRECIO_INFERIOR:
        texto = _limpia(valor)
        if texto == '-':
            return ''
        if '.' in texto:
            try:
                centimos = Decimal(texto) * 100
            except InvalidOperation:
                return valor
            if centimos == centimos.to_integral_value():
                return str(int(centimos))
        return valor
    return valor


def normalizar_export(cabecera, filas):
    """(cabecera, filas) del CSV, devueltas con los nombres y los formatos de siempre.

    Con un fichero de los de antes solo se limpia la cabecera. Con uno de los nuevos, además se añade al final
    la columna retirada, vacía: así la fila guardada tiene las mismas claves que las de antes."""
    limpias = [_limpia(h) for h in cabecera]
    es_nueva = any(h in EQUIVALENCIAS for h in limpias)
    salida = normalizar_cabecera(limpias)
    a_tocar = [(i, h) for i, h in enumerate(salida) if h in (COL_PLAZO_CAJA, COL_PRECIO_INFERIOR)]
    anadir_retirada = es_nueva and COLUMNA_RETIRADA not in salida
    n = len(salida)
    resultado = []
    for fila in filas:
        nueva = list(fila)
        for i, h in a_tocar:
            if i < len(nueva):
                nueva[i] = normalizar_valor(h, nueva[i])
        if anadir_retirada:
            # Primero a la medida de la cabecera, para que el vacío caiga en SU columna.
            nueva = (nueva + [''] * n)[:n] + ['']
        resultado.append(nueva)
    if anadir_retirada:
        salida = salida + [COLUMNA_RETIRADA]
    return salida, resultado
