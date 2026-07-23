import logging
import re
import time
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
    "must have", "best of", "2026",
]

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_DOMAINS = {"www.reddit.com", "reddit.com", "old.reddit.com"}

REQUEST_TIMEOUT = 12
MAX_POSTS_PER_FEED = 50


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
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "BeautyTrendDashboard/1.0",
        "Accept": "application/json,text/plain,*/*",
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
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def normalize_reddit_post(child: Dict[str, Any], subreddit: str, feed_type: str) -> Optional[Dict[str, Any]]:
    data = child.get("data", {})
    title = sanitize_text(data.get("title", ""), 220)
    selftext = sanitize_text(data.get("selftext", ""), 1200)
    permalink = data.get("permalink", "")
    score = safe_int(data.get("score", 0))
    comments = safe_int(data.get("num_comments", 0))
    created_utc = safe_int(data.get("created_utc", 0))
    author = sanitize_text(data.get("author", ""), 60)
    over_18 = bool(data.get("over_18", False))

    if not title or not permalink or over_18:
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
        "created_utc": created_utc,
        "author": author,
        "subreddit": subreddit,
        "source": f"reddit_json_{feed_type}",
    }


def fetch_reddit_feed(session: requests.Session, subreddit: str, feed_type: str = "hot", limit: int = 30, time_filter: str = "year") -> List[Dict[str, Any]]:
    if feed_type not in {"hot", "top", "new"}:
        return []

    url = f"https://www.reddit.com/r/{subreddit}/{feed_type}.json"
    params = {"limit": min(limit, MAX_POSTS_PER_FEED)}
    if feed_type == "top":
        params["t"] = time_filter

    try:
        resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("Reddit feed non-200: subreddit=%s feed=%s code=%s", subreddit, feed_type, resp.status_code)
            return []

        payload = resp.json()
        children = payload.get("data", {}).get("children", [])
        posts = []

        for child in children:
            post = normalize_reddit_post(child, subreddit, feed_type)
            if post:
                posts.append(post)

        return posts

    except requests.RequestException as e:
        logger.warning("fetch_reddit_feed request error subreddit=%s feed=%s err=%s", subreddit, feed_type, e)
        return []
    except Exception as e:
        logger.warning("fetch_reddit_feed parse error subreddit=%s feed=%s err=%s", subreddit, feed_type, e)
        return []


def dedupe_posts(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []
    for p in posts:
        key = (p.get("title", "").lower(), p.get("link", ""))
        if key in seen:
            continue
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


def filter_posts(posts: List[Dict[str, Any]], allowed_categories: List[str], only_2026: bool = False) -> List[Dict[str, Any]]:
    filtered = []

    for post in posts:
        combined = f"{post['title']} {post['content']}"
        mentions = match_terms(combined, allowed_categories)
        if not mentions:
            continue

        if only_2026:
            text_lower = combined.lower()
            if "2026" not in text_lower and "best of" not in text_lower and "favorite" not in text_lower and "favourite" not in text_lower:
                continue

        new_post = dict(post)
        new_post["mentions"] = mentions
        filtered.append(new_post)

    return filtered


def aggregate_brand_stats(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}

    for post in posts:
        engagement = post["score"] + post["comments"] * 2

        for mention in post.get("mentions", []):
            if mention not in stats:
                stats[mention] = {
                    "brand": mention,
                    "total_engagement": 0,
                    "mention_count": 0,
                    "total_score": 0,
                    "total_comments": 0,
                    "top_posts": [],
                    "subreddits": set(),
                }

            item = stats[mention]
            item["total_engagement"] += engagement
            item["mention_count"] += 1
            item["total_score"] += post["score"]
            item["total_comments"] += post["comments"]
            item["subreddits"].add(post["subreddit"])

            item["top_posts"].append({
                "title": post["title"],
                "link": post["link"],
                "score": post["score"],
                "comments": post["comments"],
                "subreddit": post["subreddit"],
                "source": post["source"],
            })

    results = []
    for item in stats.values():
        item["top_posts"] = sorted(
            item.get("top_posts", []),
            key=lambda x: (x["score"] + x["comments"] * 2),
            reverse=True,
        )[:3]
        item["subreddits"] = sorted(item.get("subreddits", []))
        results.append(item)

    results.sort(key=lambda x: (x["total_engagement"], x["mention_count"]), reverse=True)
    return results[:30]


def get_reddit_search_url(keyword: str) -> str:
    q = quote(keyword)
    return f"https://www.reddit.com/search/?q={q}&sort=relevance&t=year"


def run_analysis(selected_subreddits: List[str], allowed_categories: List[str], only_2026: bool, include_hot: bool, include_top_year: bool, include_new: bool, per_feed_limit: int = 25) -> Dict[str, Any]:
    session = create_session()

    all_posts: List[Dict[str, Any]] = []
    method_counts = Counter()
    progress_logs = []

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
            posts = fetch_reddit_feed(
                session=session,
                subreddit=sub,
                feed_type=feed_type,
                limit=per_feed_limit,
                time_filter=time_filter or "year",
            )
            all_posts.extend(posts)
            method_counts[feed_type] += len(posts)
            progress_logs.append(f"  - {feed_type}: {len(posts)} 筆")
            time.sleep(0.3)

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
