import requests, re

headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "es-CO,es"}

# Try to get the estado-cuenta plugin config
files = [
    "plugins/plugin-simit-vue/simit-vue-frontend/servicios/servicios.js",
    "plugins/plugin-simit-vue/simit-vue-frontend/config.js",
    "modulos/estado-cuenta/EstadoCuentaControllerImpl.js",
    "modulos/home-public/HomePublicControllerImpl.js",
]

for f in files:
    try:
        r = requests.get(f"https://www.fcm.org.co/simit/{f}", headers=headers, timeout=10)
        if r.status_code == 200:
            print(f"\n=== {f} ===")
            text = r.text[:3000]
            print(text)
            urls = re.findall(r'https?://[a-zA-Z0-9._/-]+(?:estado|consulta|comparendo|estadocuenta|multa)[a-zA-Z0-9._/-]*', text)
            if urls:
                print(f"API URLs: {urls}")
            # Also find relative paths that look like API endpoints
            apis = re.findall(r'["\'](?:estado|consulta|comparendo|estadocuenta|multa|get)[a-zA-Z0-9/_-]*["\']', text, re.IGNORECASE)
            if apis:
                print(f"API paths: {apis[:20]}")
        else:
            print(f"{f}: HTTP {r.status_code}")
    except Exception as e:
        print(f"{f}: ERROR {e}")

# Also try plugins.json
try:
    r = requests.get("https://www.fcm.org.co/simit/plugins/plugins.json", headers=headers, timeout=10)
    if r.status_code == 200:
        print(f"\n=== plugins.json ===")
        print(r.text[:2000])
except Exception as e:
    print(f"plugins.json: ERROR {e}")
