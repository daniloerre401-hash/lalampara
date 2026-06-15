import asyncio
from playwright.async_api import async_playwright

async def try_simit_from_browser():
    p = await async_playwright().start()
    b = await p.chromium.launch(headless=True, args=["--no-sandbox"])
    pg = await b.new_page()

    try:
        await pg.goto("https://www.fcm.org.co/simit/#/consulta-public",
                      wait_until="networkidle", timeout=30000)
        await asyncio.sleep(6)

        # Call API from within the browser context
        result = await pg.evaluate("""() => {
            return new Promise((resolve) => {
                fetch('https://consultasimit.fcm.org.co/simit/microservices/estado-cuenta-simit/estadocuenta/getTipoDocumentoIdentidadPublic', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: '5'
                })
                .then(r => r.text())
                .then(t => resolve('OK:' + t.slice(0, 500)))
                .catch(e => resolve('ERR:' + e.message));
            });
        }""")
        print(f"getTipoDocumento (from browser): {result}")

        # Try consulta
        result2 = await pg.evaluate("""() => {
            return new Promise((resolve) => {
                fetch('https://consultasimit.fcm.org.co/simit/microservices/estado-cuenta-simit/estadocuenta/consultarComparendosPublic', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tipoDocumento: 'CC',
                        numeroDocumento: '91078897'
                    })
                })
                .then(r => r.text())
                .then(t => resolve('OK:' + t.slice(0, 1000)))
                .catch(e => resolve('ERR:' + e.message));
            });
        }""")
        print(f"consulta (from browser): {result2}")

    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await pg.close()
        await b.close()
        await p.stop()

asyncio.run(try_simit_from_browser())
