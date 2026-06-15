import requests
import re

headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "es-CO,es"}
files_to_check = [
    "core/config/config.js",
    "core/servicios/servicios.js",
    "core/seguridad/logicaSeguridad.js",
    "dist/scripts/core.min.js",
]

for f in files_to_check:
    try:
        r = requests.get(f"https://www.fcm.org.co/simit/{f}", headers=headers, timeout=10)
        if r.status_code == 200:
            print(f"\n=== {f} ===")
            text = r.text[:3000]
            print(text)
            # Find API URLs
            urls = re.findall(r'https?://[a-zA-Z0-9._/-]*(?:simit|estado|consulta|comparendo|microservice)[a-zA-Z0-9._/-]*', text)
            if urls:
                print(f"\nAPI URLs: {urls}")
        else:
            print(f"{f}: HTTP {r.status_code}")
    except Exception as e:
        print(f"{f}: ERROR {e}")
