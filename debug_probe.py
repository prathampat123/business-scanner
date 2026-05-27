"""Debug probe — checks what Yelp and Yellow Pages actually return."""
import asyncio
import json
import re
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}


async def probe_yelp(client: httpx.AsyncClient) -> None:
    url = "https://www.yelp.com/search?find_desc=pizza+restaurants&find_loc=New+York%2C+NY"
    r = await client.get(url)
    print(f"Yelp  status: {r.status_code}")
    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.title.string if soup.title else "NO TITLE"
    print(f"Yelp  title : {title[:80]}")

    # __NEXT_DATA__ (React SSR payload — best data source)
    nd = soup.find("script", id="__NEXT_DATA__")
    print(f"Yelp  __NEXT_DATA__: {nd is not None}")
    if nd:
        try:
            data = json.loads(nd.string)
            raw = json.dumps(data)
            names = re.findall(r'"name":"([^"]{3,50})"', raw)[:10]
            print(f"Yelp  sample names: {names}")
        except Exception as exc:
            print(f"Yelp  parse error: {exc}")

    biz_links = [a for a in soup.select("a") if "/biz/" in (a.get("href") or "")]
    print(f"Yelp  /biz/ links: {len(biz_links)}")
    seen: set[str] = set()
    for a in biz_links[:6]:
        txt = a.get_text(strip=True)
        if txt and txt not in seen and len(txt) > 2:
            seen.add(txt)
            print(f"   - {txt[:60]}")


async def probe_yp(client: httpx.AsyncClient) -> None:
    url = (
        "https://www.yellowpages.com/search"
        "?search_terms=pizza+restaurants&geo_location_terms=New+York%2C+NY"
    )
    r = await client.get(url)
    print(f"\nYP    status: {r.status_code}")
    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.title.string if soup.title else "NO TITLE"
    print(f"YP    title : {title[:80]}")
    blocked = any(w in r.text.lower() for w in ("captcha", "robot", "blocked", "cloudflare"))
    print(f"YP    blocked: {blocked}")
    cards = soup.select("div.result") or soup.select("article.result")
    print(f"YP    cards found: {len(cards)}")
    if cards:
        name_tag = cards[0].select_one("a.business-name")
        print(f"YP    first card name: {name_tag.get_text(strip=True) if name_tag else 'n/a'}")


async def main() -> None:
    async with httpx.AsyncClient(follow_redirects=True, timeout=15, headers=HEADERS) as client:
        await probe_yelp(client)
        await probe_yp(client)


if __name__ == "__main__":
    asyncio.run(main())
