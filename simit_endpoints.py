import asyncio
from playwright.async_api import async_playwright

async def find_simit_endpoints():
    p = await async_playwright().start()
    b = await p.chromium.launch(headless=True, args=["--no-sandbox"])
    pg = await b.new_page()

    # Capture all network requests
    api_endpoints = set()
    
    async def capture(request):
        url = request.url
        if "consultasimit.fcm.org.co" in url or "simit" in url.lower():
            if "google" not in url and "paymentez" not in url:
                api_endpoints.add(f"{request.method} {url}")

    pg.on("request", capture)

    try:
        await pg.goto("https://www.fcm.org.co/simit/#/consulta-public",
                      wait_until="networkidle", timeout=30000)
        await asyncio.sleep(8)

        # Look for all JS files loaded
        scripts = await pg.evaluate("""() => {
            return Array.from(document.querySelectorAll('script[src]')).map(s => s.src);
        }""")
        print("=== SCRIPTS ===")
        for s in scripts:
            print(f"  {s[:120]}")

        print("\n=== API ENDPOINTS ===")
        for ep in sorted(api_endpoints):
            print(f"  {ep}")

        # Search for endpoint names in the page's JS
        js_content = await pg.evaluate("""() => {
            const scripts = document.querySelectorAll('script:not([src])');
            let text = '';
            scripts.forEach(s => text += s.innerText + '\\n');
            return text.slice(0, 5000);
        }""")
        
        # Search for keywords in JS
        for keyword in ['estadocuenta/', 'comparendo', 'consultar', 'getTipo']:
            indices = []
            idx = 0
            while True:
                idx = js_content.find(keyword, idx)
                if idx == -1:
                    break
                context = js_content[max(0,idx-30):idx+len(keyword)+60]
                indices.append(context)
                idx += 1
            if indices:
                print(f"\n=== '{keyword}' in JS ===")
                for ctx in indices[:5]:
                    print(f"  ...{ctx}...")

    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await pg.close()
        await b.close()
        await p.stop()

asyncio.run(find_simit_endpoints())
