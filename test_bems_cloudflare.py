# -*- coding: utf-8 -*-
"""
PRUEBA AISLADA: ¿curl_cffi pasa el Cloudflare de BEMS desde GitHub Actions?

NO toca nada del escáner ni del ActualizarApp. Solo intenta obtener el token
de BEMS desde la IP de datacenter de GitHub Actions y reporta el resultado.

Credenciales: SOLO desde variables de entorno (GitHub Secrets).
NUNCA se imprime el token entero ni las credenciales.
"""

import os
import sys

# Log en vivo (lección 16-jun: el "log mudo" del buffer)
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print(">>> ARRANCA PRUEBA BEMS / CLOUDFLARE <<<")

try:
    from curl_cffi import requests as curl_requests
except Exception as e:
    print(f"ERROR: no se pudo importar curl_cffi: {e}")
    sys.exit(1)

LOGIN = os.environ.get("BEMS_LOGIN")
PASSWORD = os.environ.get("BEMS_PASSWORD")
SECRET_KEY = os.environ.get("BEMS_SECRET_KEY")

# Comprobar que los secrets están puestos, SIN imprimir su valor
faltan = [n for n, v in [
    ("BEMS_LOGIN", LOGIN),
    ("BEMS_PASSWORD", PASSWORD),
    ("BEMS_SECRET_KEY", SECRET_KEY),
] if not v]
if faltan:
    print(f"ERROR: faltan estos GitHub Secrets: {', '.join(faltan)}")
    print("Ponlos en el repo (Settings > Secrets and variables > Actions) y relanza.")
    sys.exit(1)

print("Credenciales presentes (valores ocultos). OK.")

URL = "https://www.probems.be/API/TOKEN"
DATA = {"login": LOGIN, "password": PASSWORD, "secret_key": SECRET_KEY}
HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}

# Probamos varias huellas de Chrome por si una pasa y otra no
PERFILES = ["chrome120", "chrome131", "chrome110", "chrome116"]

resultado_global = "NINGUNO"

for perfil in PERFILES:
    print(f"\n--- Intento con impersonate='{perfil}' ---")
    try:
        r = curl_requests.post(
            URL,
            data=DATA,
            headers=HEADERS,
            impersonate=perfil,
            timeout=30,
        )
    except Exception as e:
        print(f"  EXCEPCION de red/conexion: {type(e).__name__}: {e}")
        continue

    code = r.status_code
    print(f"  HTTP status: {code}")

    # Cuerpo recortado para diagnostico, sin filtrar el token
    cuerpo = (r.text or "")[:300]
    es_cloudflare = ("cloudflare" in cuerpo.lower()
                     or "cf-ray" in str(r.headers).lower()
                     or "just a moment" in cuerpo.lower()
                     or "attention required" in cuerpo.lower())

    if code == 200:
        try:
            j = r.json()
        except Exception:
            j = None
        if isinstance(j, dict) and j.get("access_token"):
            tok = j["access_token"]
            print(f"  >>> EXITO: token obtenido (longitud {len(tok)}, "
                  f"empieza por '{tok[:6]}...'). Cloudflare NO bloquea desde Actions.")
            resultado_global = f"PASA con {perfil}"
            break
        else:
            print(f"  200 pero sin access_token. Respuesta (recorte): {cuerpo}")
            resultado_global = f"200 raro con {perfil}"
    elif code == 401:
        # Pasó Cloudflare (la API contestó), pero credenciales/permiso
        print(f"  401: la API RESPONDIO (Cloudflare dejo pasar), pero rechazo el "
              f"login/clave. Respuesta (recorte): {cuerpo}")
        print("  => Para la pregunta de hoy es BUENA noticia: Cloudflare no bloquea. "
              "Revisar credenciales aparte.")
        resultado_global = f"PASA Cloudflare (401 credenciales) con {perfil}"
        break
    elif code == 403:
        if es_cloudflare:
            print("  403 de CLOUDFLARE: bloqueo a nivel TLS/IP. "
                  "Este perfil NO pasa desde Actions.")
        else:
            print(f"  403 (no parece Cloudflare). Respuesta (recorte): {cuerpo}")
        resultado_global = "BLOQUEADO (403)"
    else:
        print(f"  Status inesperado {code}. Respuesta (recorte): {cuerpo}")
        resultado_global = f"INESPERADO {code}"

print("\n========================================")
print(f"RESULTADO: {resultado_global}")
print("========================================")
print("Lectura:")
print(" - 'PASA ...'            => curl_cffi vale desde Actions. Seguimos por Actions.")
print(" - 'PASA Cloudflare (401 ...)' => Cloudflare OK; solo hay que revisar credenciales.")
print(" - 'BLOQUEADO (403)'     => Cloudflare bloquea la IP de Actions. Plan B: puente Vercel.")
