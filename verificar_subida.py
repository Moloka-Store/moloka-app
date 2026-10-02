# -*- coding: utf-8 -*-
"""¿Está ESTE fichero en Storage? — la verificación de una subida, por su nombre.

Encargo AH (2-oct-2026). La usan el escáner viejo (moloka_escaner_nube.py) y el Pro
(moloka_escaner_pro_nube.py) justo después de subir el Excel; de su respuesta sale
`subido_ok`, y de `subido_ok` salen dos cosas: el `fichero` de la fila de la Biblioteca
(escaner_resultados) y si se limpia el buzón del escáner.

🔴 POR QUÉ NO SE LISTA LA CARPETA ENTERA. Antes la verificación era
       any(o['name'] == nombre for o in sb.storage.from_(BUCKET).list(CARPETA_RESULTADOS))
   y `.list(carpeta)` sin opciones devuelve, por defecto del SDK, las 100 PRIMERAS entradas
   por nombre (storage3 2.31.0: DEFAULT_SEARCH_OPTIONS = limit 100, offset 0, sortBy name
   asc). `resultados/` guarda los Excel de todos los escaneos y los de TCG van los ÚLTIMOS
   del alfabeto: en cuanto la carpeta pasa de 100 entradas por delante, la subida que fue
   bien se da por fallida. El 30-sep-2026 12:04 UTC el Excel de TCG (id=1688) se subió,
   el log dijo «verificado: False» y la fila quedó con `fichero` NULL.

🔑 Se pide el fichero CONCRETO: `.list(carpeta, {'search': nombre})`. En el servidor,
   storage.search filtra por `name ILIKE carpeta/ || search || '%'` (leído en producción
   el 2-oct-2026), así que vuelven el fichero y, como mucho, los que empiezan igual; y
   aquí se exige igualdad EXACTA, porque `_` es comodín en ILIKE y «empieza igual» no es
   «es el mismo».
   No se usa `.exists()`: en la 2.31.0 hace un HEAD, y un 401 o un 500 acaban también en
   False (la respuesta de un HEAD no trae cuerpo y el SDK lo traga como «no existe»). Una
   verificación que no distingue «no está» de «no he podido mirar» no verifica.

🔑 Si la primera mirada no lo ve —o la propia mirada falla—, se espera y se mira otra vez
   antes de dar el fichero por no subido. La subida no lanzó excepción: decir «no está»
   a la primera es lo que deja una fila sin fichero y un buzón sin limpiar.
"""
import time

ESPERA_REINTENTO = 1.5   # segundos entre la primera mirada y la segunda
INTENTOS = 2             # la primera + un reintento


def fichero_en_storage(sb, bucket, carpeta, nombre, intentos=INTENTOS,
                       espera=ESPERA_REINTENTO, dormir=time.sleep, imprimir=print):
    """True si `carpeta/nombre` está en el bucket, mirándolo por su nombre exacto.
    Nunca lanza: si no puede mirar, lo dice y cuenta como «no visto» en ese intento."""
    for intento in range(1, intentos + 1):
        try:
            objs = sb.storage.from_(bucket).list(carpeta, {'search': nombre, 'limit': 100}) or []
            if any(o.get('name') == nombre for o in objs):
                if intento > 1:
                    imprimir(f"   verificación de {carpeta}/{nombre}: visto en el intento {intento}.")
                return True
            motivo = 'no aparece al buscarlo por su nombre'
        except Exception as ex:
            motivo = f'no se pudo mirar ({type(ex).__name__}: {ex})'
        if intento < intentos:
            imprimir(f"   verificación de {carpeta}/{nombre}: {motivo}; "
                     f"reintento en {espera:g} s ({intento}/{intentos}).")
            dormir(espera)
        else:
            imprimir(f"   verificación de {carpeta}/{nombre}: {motivo} "
                     f"tras {intentos} intento(s).")
    return False
