from fastapi import APIRouter, HTTPException, Query, Response
from urllib.parse import unquote, urljoin
import httpx
import re

router = APIRouter(prefix="/api/image", tags=["image"])

OG_IMG_META = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)["\']',
    flags=re.IGNORECASE,
)
IMG_TAG = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', flags=re.IGNORECASE)

async def _fetch(url: str, headers: dict) -> httpx.Response:
    timeout = httpx.Timeout(12.0, connect=6.0)
    async with httpx.AsyncClient(follow_redirects=True, headers=headers, timeout=timeout) as client:
        return await client.get(url)

@router.get("/proxy")
async def proxy(u: str = Query(..., description="URL-encoded absolute image (or page) URL")):
    """
    Same-origin image proxy to bypass Referer/CORS/hotlinking blocks.
    If the URL is a page (text/html), attempt to extract og:image/twitter:image/first <img>.
    """
    url = unquote(u or "")
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL")

    headers = {
        "referer": "",  # drop Referer to avoid hotlink blocks
        "user-agent": "Mozilla/5.0 (compatible; Revival365AI/1.0)",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*,*/*;q=0.8",
    }

    # 1) Fetch upstream
    r = await _fetch(url, headers)
    if r.status_code >= 400:
        raise HTTPException(r.status_code, f"Upstream returned {r.status_code}")

    ctype = r.headers.get("content-type", "")
    content = r.content or b""

    # 2) If already an image, return as-is
    if ctype.startswith("image/"):
        return Response(content=content, media_type=ctype or "image/jpeg")

    # 3) If HTML, extract a best-guess image and fetch that
    if "text/html" in ctype.lower():
        html = r.text or ""
        # Try og:image / twitter:image
        m = OG_IMG_META.search(html)
        candidate = m.group(1) if m else None
        # Fallback: first <img src="...">
        if not candidate:
            m2 = IMG_TAG.search(html)
            if m2:
                candidate = m2.group(1)

        if candidate:
            # Resolve relative paths against page URL
            cand_abs = urljoin(r.url, candidate)
            r2 = await _fetch(cand_abs, headers | {"accept": "image/*,*/*;q=0.8"})
            if r2.status_code < 400 and r2.headers.get("content-type", "").startswith("image/"):
                return Response(content=r2.content, media_type=r2.headers.get("content-type", "image/jpeg"))

    # 4) Fallback: return original bytes/content-type
    return Response(content=content, media_type=ctype or "application/octet-stream")
