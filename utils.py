import logging
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

SUBREDDITS = [
    "MakeupAddiction",
    "SkincareAddiction",
    "drugstoreMUA",
    "BeautyGuruChatter",
    "AsianBeauty",
]

KNOWN_BRANDS = [
    "Rare Beauty", "Fenty Beauty", "NARS", "Charlotte Tilbury", "MAC",
    "Urban Decay", "Too Faced", "Tarte", "Benefit", "Clinique",
    "Estee Lauder", "Lancome", "Maybelline", "L'Oreal", "Revlon",
    "NYX", "e.l.f.", "Elf", "CeraVe", "The Ordinary", "Paula's Choice",
    "Drunk Elephant", "Tatcha", "Glossier", "Tower 28", "Kosas",
    "Patrick Ta", "Makeup by Mario", "Natasha Denona",
    "Huda Beauty", "Anastasia Beverly Hills", "ABH", "Morphe",
    "Laura Mercier", "Bobbi Brown", "Dior", "Chanel", "YSL",
    "Tom Ford", "Hourglass", "Colourpop", "ColourPop",
    "IT Cosmetics", "Mario Badescu", "First Aid Beauty", "Fresh",
    "Laneige", "Innisfree", "COSRX",
]

MAKEUP_KEYWORDS = [
    "blush", "foundation", "concealer", "mascara", "lipstick", "lip gloss",
    "eyeshadow", "palette", "primer", "setting spray", "setting powder",
    "bronzer", "highlighter", "lip liner", "tint", "cushion", "powder",
    "cream blush", "skin tint",
]

SKINCARE_KEYWORDS = [
    "serum", "moisturizer", "cleanser", "sunscreen", "spf", "retinol",
    "vitamin c", "niacinamide", "hyaluronic", "toner", "exfoliant",
    "cream", "lotion", "oil", "mask",
]

GENERAL_TREND_KEYWORDS = [
    "holy grail", "hg", "favorite", "favourite", "recommend",
    "must have", "best of", "top 2026", "2026 favorites",
]

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_DOMAINS = {
    "www.reddit.com",
    "reddit.com",
    "old.reddit.com",
}

REDLIB_MIRRORS = [
    "https://redlib.tux.pizza",
    "https://redlib.catsarch.com",
    "https://rl.bloat.cat",
    "https://redlib.perennialte.ch",
    "https://red.ngn.tf",
    "https://redlib.freedit.eu",
]

SEARXNG_INSTANCES = [
    "https://search.sapti.me",
    "https://search.ononoki.org",
    "https://searx.be",
    "https://searxng.ch",
]

REQUEST_TIMEOUT = 10
MAX_POSTS_PER_FEED = 50


def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2, connect=2, read=2, backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/json,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return session


def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ALLOWED_SCHEMES and parsed.netloc.lower() in ALLOWED_DOMAINS
    except Exception:
        return False


def sanitize_text(text: Any, max_len: int = 300) -> str:
    if text is None:
        return ""
    text = str(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len - 3] + "..." if len(text) > max_len else text


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def normalize_reddit_post(child: Dict[str, Any], subreddit: str, source: str) -> Optional[Dict[str, Any]]:
    data = child.get("data", {})
    title = sanitize_text(data.get("title", ""), 220)
    selftext = sanitize_text(data.get("selftext", ""), 1200)
    permalink = data.get("permalink", "")
    score = safe_int(data.get("score", 0))
    comments = safe_int(data.get("num_comments", 0))

    if not title or not permalink or bool(data.get("over_18", False)):
        return None

    full_url = f"https://www.reddit.com{permalink}"
    if not is_safe_url(full_url):
        return None

    return {
        "title": title,
        "content": selftext,
        "link": full_url,
        "score": max(score, 0),
        "comments": max(comments, 0),
        "subreddit": subreddit,
        "source": source,
    }


def _fetch_reddit_json(session: requests.Session, url: str, params: dict) -> List[Dict[str, Any]]:
    try:
        resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("children", [])
    except Exception:
        pass
    return []


def _fetch_redlib(session: requests.Session, sub: str) -> List[Dict[str, Any]]:
    for base_url in REDLIB_MIRRORS:
        try:
            resp = session.get(f"{base_url}/r/{sub}", timeout=8)
            if resp.status_code != 200:
                continue
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            posts = []
            for el in soup.select(".post"):
                title_a = el.select_one(".post_title a")
                if not title_a:
                    continue
                title = title_a.get_text(strip=True)
                href = title_a.get("href", "")
                body_el = el.select_one(".post_body")
                body = body_el.get_text(strip=True)[:1200] if body_el else ""
                score_el = el.select_one(".score")
                score = safe_int(re.sub(r"[^0-9-]", "", score_el.get_text()) if score_el else "0")
                comment_el = el.select_one(".post_comments a")
                comments = safe_int(re.sub(r"[^0-9]", "", comment_el.get_text()) if comment_el else "0")
                full_url = href if href.startswith("http") else f"{base_url}{href}"
                posts.append({
                    "title": title, "content": body, "link": full_url,
                    "score": max(score, 0), "comments": max(comments, 0),
                    "subreddit": sub, "source": f"redlib_{base_url.split('//')[1]}",
                })
            if posts:
                return posts
        except Exception:
            continue
    return []


def _fetch_searxng(session: requests.Session, query: str) -> List[Dict[str, Any]]:
    for base_url in SEARXNG_INSTANCES:
        try:
            resp = session.get(
                f"{base_url}/search",
                params={"q": query, "format": "json", "categories": "general"},
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            posts = []
            for r in data.get("results", [])[:15]:
                url = r.get("url", "")
                if "reddit.com" not in url:
                    continue
                posts.append({
                    "title": sanitize_text(r.get("title", ""), 220),
                    "content": sanitize_text(r.get("content", ""), 800),
                    "link": url,
                    "score": 0, "comments": 0,
                    "subreddit": "search",
                    "source": f"searxng_{base_url.split('//')[1]}",
                })
            if posts:
                return posts
        except Exception:
            continue
    return []


def _fetch_google(session: requests.Session, query: str) -> List[Dict[str, Any]]:
    try:
        resp = session.get(
            "https://www.google.com/search",
            params={"q": query, "num": 10, "hl": "en"},
            timeout=8,
        )
        if resp.status_code != 200:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = []
        for g in soup.select("div.g"):
            a = g.select_one("a[href]")
            h3 = g.select_one("h3")
            snippet = g.select_one(".VwiC3b")
            if not a or not h3:
                continue
            href = a["href"]
            if "reddit.com" not in href:
                continue
            posts.append({
                "title": sanitize_text(h3.get_text(strip=True), 220),
                "content": sanitize_text(snippet.get_text(strip=True), 800) if snippet else "",
                "link": href,
                "score": 0, "comments": 0,
                "subreddit": "search",
                "source": "google",
            })
        return posts
    except Exception:
        return []


def fetch_posts_multi_strategy(
    session: requests.Session,
    subreddit: str,
    feed_type: str = "hot",
    limit: int = 30,
    time_filter: str = "year",
) -> List[Dict[str, Any]]:
    # Strategy 1: Reddit JSON API (www.reddit.com)
    url = f"https://www.reddit.com/r/{subreddit}/{feed_type}.json"
    params = {"limit": min(limit, MAX_POSTS_PER_FEED)}
    if feed_type == "top":
        params["t"] = time_filter
    children = _fetch_reddit_json(session, url, params)
    if children:
        posts = [normalize_reddit_post(c, subreddit, f"reddit_{feed_type}") for c in children]
        return [p for p in posts if p]

    # Strategy 2: Reddit JSON API (old.reddit.com)
    url2 = f"https://old.reddit.com/r/{subreddit}/{feed_type}.json"
    children2 = _fetch_reddit_json(session, url2, params)
    if children2:
        posts = [normalize_reddit_post(c, subreddit, f"reddit_old_{feed_type}") for c in children2]
        return [p for p in posts if p]

    # Strategy 3: Redlib mirrors
    posts = _fetch_redlib(session, subreddit)
    if posts:
        return posts

    # Strategy 4: SearXNG
    posts = _fetch_searxng(session, f"r/{subreddit} best product")
    if posts:
        return posts

    # Strategy 5: Google
    posts = _fetch_google(session, f"site:reddit.com/r/{subreddit} best product 2025 2026")
    return posts


def dedupe_posts(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []
    for p in posts:
        key = (p.get("title", "").lower(), p.get("link", ""))
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def match_terms(text: str, allowed_categories: List[str]) -> List[str]:
    text_lower = text.lower()
    mentions = []
    for brand in KNOWN_BRANDS:
        if brand.lower() in text_lower:
            mentions.append(brand)
    if "makeup" in allowed_categories:
        for kw in MAKEUP_KEYWORDS:
            if kw.lower() in text_lower:
                mentions.append(kw)
    if "skincare" in allowed_categories:
        for kw in SKINCARE_KEYWORDS:
            if kw.lower() in text_lower:
                mentions.append(kw)
    for kw in GENERAL_TREND_KEYWORDS:
        if kw.lower() in text_lower:
            mentions.append(kw)
    return mentions


def filter_posts(
    posts: List[Dict[str, Any]],
    allowed_categories: List[str],
    only_2026: bool = False,
) -> List[Dict[str, Any]]:
    filtered = []
    for post in posts:
        combined = f"{post['title']} {post['content']}"
        mentions = match_terms(combined, allowed_categories)
        if not mentions:
            continue
        if only_2026:
            tl = combined.lower()
            if not any(kw in tl for kw in ["2026", "this year", "favorites", "favourites", "best of"]):
                continue
        new_post = dict(post)
        new_post["mentions"] = mentions
        filtered.append(new_post)
    return filtered


def aggregate_brand_stats(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    for post in posts:
        engagement = post["score"] + post["comments"] * 2
        for mention in post["mentions"]:
            if mention not in stats:
                stats[mention] = {
                    "brand": mention, "total_engagement": 0, "mention_count": 0,
                    "total_score": 0, "total_comments": 0, "top_posts": [], "subreddits": set(),
                }
            item = stats[mention]
            item["total_engagement"] += engagement
            item["mention_count"] += 1
            item["total_score"] += post["score"]
            item["total_comments"] += post["comments"]
            item["subreddits"].add(post["subreddit"])
            item["top_posts"].append({
                "title": post["title"], "link": post["link"],
                "score": post["score"], "comments": post["comments"],
                "subreddit": post["subreddit"], "source": post["source"],
            })
    results = []
    for _, item in stats.items():
        item["top_posts"] = sorted(
            item["top_posts"], key=lambda x: (x["score"] + x["comments"] * 2), reverse=True,
        )[:3]
        item["subreddits"] = sorted(item["subreddits"])
        results.append(item)
    results.sort(key=lambda x: (x["total_engagement"], x["mention_count"]), reverse=True)
    return results[:30]


def get_reddit_search_url(keyword: str) -> str:
    return f"https://www.reddit.com/search/?q={quote(keyword)}&sort=relevance&t=year"


def run_analysis(
    selected_subreddits: List[str],
    allowed_categories: List[str],
    only_2026: bool,
    include_hot: bool,
    include_top_year: bool,
    include_new: bool,
    per_feed_limit: int = 25,
) -> Dict[str, Any]:
    session = create_session()
    all_posts: List[Dict[str, Any]] = []
    method_counts: Counter = Counter()
    progress_logs: List[str] = []

    feed_plan = []
    if include_hot:
        feed_plan.append(("hot", None))
    if include_top_year:
        feed_plan.append(("top", "year"))
    if include_new:
        feed_plan.append(("new", None))

    for sub in selected_subreddits:
        progress_logs.append(f"抓取 r/{sub} ...")
        for feed_type, time_filter in feed_plan:
            posts = fetch_posts_multi_strategy(
                session=session, subreddit=sub, feed_type=feed_type,
                limit=per_feed_limit, time_filter=time_filter or "year",
            )
            all_posts.extend(posts)
            method_counts[feed_type] += len(posts)
            progress_logs.append(f"  - {feed_type}: {len(posts)} 筆")
            if posts:
                progress_logs.append(f"    來源: {posts[0].get('source', 'unknown')}")
            time.sleep(1)

    all_posts = dedupe_posts(all_posts)
    filtered_posts = filter_posts(all_posts, allowed_categories, only_2026)
    ranked = aggregate_brand_stats(filtered_posts)

    return {
        "products": ranked,
        "raw_post_count": len(all_posts),
        "filtered_post_count": len(filtered_posts),
        "method_counts": dict(method_counts),
        "progress_logs": progress_logs,
        "generated_at": int(time.time()),
    }
