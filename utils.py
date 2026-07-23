import logging
import re
import time
from typing import Any, Dict, List
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20

# 參考 Sephora / Ulta 常見北美美妝品牌池
DEFAULT_BRANDS = [
    "Rare Beauty", "Fenty Beauty", "NARS", "Charlotte Tilbury", "MAC",
    "Urban Decay", "Too Faced", "Tarte", "Benefit Cosmetics", "Clinique",
    "Estée Lauder", "Estee Lauder", "Lancôme", "Lancome", "Maybelline",
    "L'Oréal", "Loreal", "Revlon", "NYX", "e.l.f.", "Elf",
    "CeraVe", "The Ordinary", "Paula's Choice", "Drunk Elephant",
    "Tatcha", "Glossier", "Tower 28", "Kosas", "Patrick Ta",
    "Makeup by Mario", "Natasha Denona", "Huda Beauty",
    "Anastasia Beverly Hills", "ABH", "Morphe", "Laura Mercier",
    "Bobbi Brown", "Dior", "Chanel", "YSL", "Tom Ford", "Hourglass",
    "ColourPop", "Colourpop", "IT Cosmetics", "Fresh", "Laneige",
    "Innisfree", "COSRX", "Rhode", "Saie", "Merit", "Armani Beauty",
    "Haus Labs", "Milk Makeup", "Too Cool For School", "Beautyblender",
    "bareMinerals", "Ami Colé", "Basma", "Biossance", "belif",
    "Beauty of Joseon", "Supergoop!", "Shiseido", "Sol de Janeiro",
    "Dior Beauty", "Sephora Collection", "Ulta Beauty Collection",
]

MAKEUP_KEYWORDS = [
    "makeup", "blush", "foundation", "concealer", "mascara", "lipstick",
    "lip gloss", "eyeshadow", "palette", "primer", "setting spray",
    "setting powder", "bronzer", "highlighter", "lip liner", "tint",
    "skin tint", "cushion", "powder", "sephora", "ulta",
]

SKINCARE_KEYWORDS = [
    "skincare", "serum", "moisturizer", "cleanser", "sunscreen", "spf",
    "retinol", "vitamin c", "niacinamide", "hyaluronic", "toner",
    "exfoliant", "cream", "lotion", "mask",
]

DEFAULT_MONITOR_TERMS = [
    "Rare Beauty blush",
    "Fenty Beauty gloss",
    "Charlotte Tilbury foundation",
    "NARS concealer",
    "Maybelline mascara",
    "e.l.f. blush",
    "Sephora best makeup",
    "Ulta viral makeup",
    "CeraVe moisturizer",
    "The Ordinary serum",
    "Tower 28 blush",
    "Kosas concealer",
    "Rhode peptide lip treatment",
    "Saie blush",
    "Merit beauty stick",
    "Haus Labs foundation",
    "Milk Makeup blush",
    "Supergoop sunscreen",
    "Laneige lip mask",
    "Beauty of Joseon sunscreen",
]

TREND_WORDS = [
    "viral", "best", "favorite", "favourite", "top", "trending", "must have"
]


def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    })
    return session


def sanitize_text(text: Any, max_len: int = 300) -> str:
    if text is None:
        return ""
    text = str(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def parse_brand_input(text: str) -> List[str]:
    if not text:
        return []

    parts = re.split(r"[\n,;|]+", text)
    cleaned = []
    seen = set()

    for part in parts:
        brand = sanitize_text(part, 80)
        if not brand:
            continue
        key = brand.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(brand)

    return cleaned


def dedupe_strings(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def match_beauty_terms(text: str, categories: List[str], brand_pool: List[str]) -> List[str]:
    text_lower = text.lower()
    mentions = []

    for brand in brand_pool:
        if brand.lower() in text_lower:
            mentions.append(brand)

    if "makeup" in categories:
        for kw in MAKEUP_KEYWORDS:
            if kw.lower() in text_lower:
                mentions.append(kw)

    if "skincare" in categories:
        for kw in SKINCARE_KEYWORDS:
            if kw.lower() in text_lower:
                mentions.append(kw)

    for kw in TREND_WORDS:
        if kw.lower() in text_lower:
            mentions.append(kw)

    return dedupe_strings(mentions)


def fetch_google_trending_page(session: requests.Session, geo: str = "US") -> List[str]:
    url = f"https://trends.google.com/trending?geo={quote(geo.lower())}"

    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("Google Trends non-200 geo=%s code=%s", geo, resp.status_code)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text("\n", strip=True)

        lines = [sanitize_text(line, 120) for line in text.splitlines()]
        lines = [line for line in lines if line and len(line) >= 2]

        cleaned = []
        noise_patterns = [
            "google trends",
            "trending now",
            "search trends",
            "trend breakdown",
            "past 24 hours",
            "active:",
            "lasted:",
            "all trends",
            "all categories",
            "sort by",
            "search volume",
            "started",
            "export",
            "local unavailable",
            "privacy",
            "terms",
            "feedback",
        ]

        for line in lines:
            ll = line.lower()
            if any(n in ll for n in noise_patterns):
                continue
            if len(line) > 80:
                continue
            cleaned.append(line)

        return dedupe_strings(cleaned)

    except requests.RequestException as e:
        logger.warning("fetch_google_trending_page request error geo=%s err=%s", geo, e)
        return []
    except Exception as e:
        logger.warning("fetch_google_trending_page parse error geo=%s err=%s", geo, e)
        return []


def score_term(term: str, categories: List[str], brand_pool: List[str]) -> Dict[str, Any]:
    mentions = match_beauty_terms(term, categories, brand_pool)
    if not mentions:
        return {}

    score = len(mentions) * 10
    term_lower = term.lower()

    for brand in brand_pool:
        if brand.lower() in term_lower:
            score += 20

    return {
        "keyword": term,
        "mention_count": len(mentions),
        "trend_score": score,
        "mentions": mentions,
        "source": "google_trends_trending_now",
    }


def build_monitor_results(categories: List[str], brand_pool: List[str]) -> List[Dict[str, Any]]:
    results = []
    for term in DEFAULT_MONITOR_TERMS:
        mentions = match_beauty_terms(term, categories, brand_pool)
        if not mentions:
            continue
        results.append({
            "keyword": term,
            "mention_count": len(mentions),
            "trend_score": len(mentions) * 8,
            "mentions": mentions,
            "source": "beauty_monitor_list",
        })

    # 額外加入使用者品牌池的監測詞
    for brand in brand_pool[:40]:
        synthetic_term = f"{brand} best seller"
        mentions = match_beauty_terms(synthetic_term, categories, brand_pool)
        if not mentions:
            continue
        results.append({
            "keyword": synthetic_term,
            "mention_count": len(mentions),
            "trend_score": len(mentions) * 6,
            "mentions": mentions,
            "source": "custom_brand_monitor",
        })

    results.sort(key=lambda x: (x["trend_score"], x["mention_count"]), reverse=True)
    return results


def aggregate_mentions(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}

    for item in results:
        keyword = item.get("keyword", "")
        trend_score = item.get("trend_score", 0)
        source = item.get("source", "")
        mentions = item.get("mentions", [])

        for mention in mentions:
            if mention not in stats:
                stats[mention] = {
                    "brand": mention,
                    "mention_count": 0,
                    "total_score": 0,
                    "top_items": [],
                    "sources": set(),
                }

            row = stats[mention]
            row["mention_count"] += 1
            row["total_score"] += trend_score
            row["sources"].add(source)
            row["top_items"].append({
                "keyword": keyword,
                "source": source,
                "trend_score": trend_score,
            })

    final = []
    for row in stats.values():
        row["top_items"] = sorted(
            row["top_items"],
            key=lambda x: x["trend_score"],
            reverse=True,
        )[:3]
        row["sources"] = sorted(list(row["sources"]))
        final.append(row)

    final.sort(
        key=lambda x: (x["total_score"], x["mention_count"]),
        reverse=True,
    )
    return final[:50]


def build_brand_pool(use_default_brands: bool, custom_brands: List[str]) -> List[str]:
    pool = []
    if use_default_brands:
        pool.extend(DEFAULT_BRANDS)
    pool.extend(custom_brands)
    return dedupe_strings(pool)


def run_analysis(
    geo: str,
    categories: List[str],
    use_monitor_fallback: bool,
    use_default_brands: bool,
    custom_brands: List[str],
) -> Dict[str, Any]:
    session = create_session()
    progress_logs = []

    brand_pool = build_brand_pool(
        use_default_brands=use_default_brands,
        custom_brands=custom_brands,
    )

    progress_logs.append(f"品牌池數量：{len(brand_pool)}")
    progress_logs.append(f"抓取 Google Trends Trending Now（{geo}）...")

    live_terms = fetch_google_trending_page(session, geo=geo)

    scored_live = []
    for term in live_terms:
        row = score_term(term, categories, brand_pool)
        if row:
            scored_live.append(row)

    scored_live = sorted(
        scored_live,
        key=lambda x: (x["trend_score"], x["mention_count"]),
        reverse=True,
    )

    fallback_terms = []
    if use_monitor_fallback and len(scored_live) < 5:
        progress_logs.append("即時美妝趨勢不足，啟用品牌監測關鍵字庫...")
        fallback_terms = build_monitor_results(categories, brand_pool)

    combined = scored_live + fallback_terms
    aggregated = aggregate_mentions(combined)

    return {
        "aggregated": aggregated,
        "live_terms_count": len(live_terms),
        "matched_live_count": len(scored_live),
        "fallback_used": bool(fallback_terms),
        "progress_logs": progress_logs,
        "generated_at": int(time.time()),
        "raw_live_terms": live_terms[:50],
        "brand_pool": brand_pool,
    }
