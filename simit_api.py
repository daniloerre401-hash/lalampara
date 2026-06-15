import asyncio
from playwright.async_api import async_playwright

async def monitor_simit_api():
    p = await async_playwright().start()
    b = await p.chromium.launch(headless=True, args=["--no-sandbox"])
    pg = await b.new_page()

    api_calls = []

    async def handle_request(request):
        url = request.url
        if any(k in url for k in ["api", "login", "consulta", "comparendo", "auth", "token"]):
            api_calls.append({
                "url": url[:150],
                "method": request.method,
                "headers": dict(request.headers),
                "post_data": request.post_data
            })

    pg.on("request", handle_request)

    try:
        await pg.goto("https://www.fcm.org.co/simit/#/consulta-public",
                      wait_until="networkidle", timeout=30000)
        await asyncio.sleep(6)
    except:
        pass

    print("=== SIMIT API CALLS CAPTURED ===")
    for call in api_calls:
        print(f"\n{call['method']} {call['url']}")
        if call['post_data']:
            print(f"  Data: {call['post_data'][:200]}")

    await pg.close()

    # Also try to find the login API endpoint
    pg = await b.new_page()
    api_calls2 = []
    pg.on("request", handle_request)
    try:
        await pg.goto("https://www.fcm.org.co/simit/", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(6)
    except:
        pass

    print("\n\n=== SIMIT HOME API CALLS ===")
    for call in api_calls:
        print(f"\n{call['method']} {call['url']}")

    await pg.close()
    await b.close()
    await p.stop()

asyncio.run(monitor_simit_api())
