import html
import logging
import re
import time
from collections import Counter
from typing import List, Dict, Any, Optional
from urllib.parse import quote, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------------------------
# 基本設定
# ---------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="北美流行化妝品排行",
    page_icon="💄",
    layout="wide",
)

SUBREDDITS = [
    "MakeupAddiction",
    "SkincareAddiction",
    "drugstoreMUA",
    "BeautyGuruChatter",
    "AsianBeauty",
]

REDLIB_INSTANCES = [
    "https://redlib.tux.pizza",
    "https://redlib.seasi.dev",
    "https://redlib.catsarch.com",
    "https://redlib.freedit.eu",
    "https://red.ngn.tf",
]

SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_DOMAINS = {
    "reddit.com",
    "www.reddit.com",
    "old.reddit.com",
    "redlib.tux.pizza",
    "redlib.seasi.dev",
    "redlib.catsarch.com",
    "redlib.freedit.eu",
    "red.ngn.tf",
    "www.google.com",
    "lite.duckduckgo.com",
}

REQUEST_TIMEOUT = 12
CACHE_TTL_SECONDS = 60 * 60
SESSION_RATE_LIMIT_SECONDS = 300
MAX_POSTS_PER_SOURCE = 20
MAX_TOP_POSTS_PER_BRAND = 3
SEARCH_DELAY_SECONDS = 1.0

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

PRODUCT_KEYWORDS = [
    "blush", "foundation", "concealer", "mascara", "lipstick", "lip gloss",
    "eyeshadow", "palette", "serum", "moisturizer", "cleanser", "sunscreen",
    "SPF", "retinol", "vitamin c", "niacinamide", "hyaluronic",
    "toner", "exfoliant", "primer", "setting spray", "setting powder",
    "bronzer", "highlighter", "cream", "lotion", "oil", "mask",
    "holy grail", "HG", "favorite", "recommend", "must have", "best of",
]


# ---------------------------
# 安全與工具函式
# ---------------------------
def create_session() -> requests.Session:
    session = requests.Session()

    retry = Retry(
        total=2,
        read=2,
        connect=2,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(SEARCH_HEADERS)
    return session


def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ALLOWED_SCHEMES and parsed.netloc.lower() != ""
    except Exception:
        return False


def domain_in_allowlist(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower() in ALLOWED_DOMAINS
    except Exception:
        return False


def sanitize_text(text: Any, max_len: int = 300) -> str:
    if text is None:
        return ""
    text = str(text).strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def safe_int(value: Any, default: int = 0) -> int:
    try:
        digits = re.sub(r"[^0-9-]", "", str(value))
        return int(digits) if digits else default
    except Exception:
        return default


def normalize_post(post: Dict[str, Any], subreddit: str, source: str) -> Optional[Dict[str, Any]]:
    title = sanitize_text(post.get("title", ""), 200)
    content = sanitize_text(post.get("content", ""), 600)
    link = str(post.get("link", "")).strip()
    score = safe_int(post.get("score", 0))
    comments = safe_int(post.get("comments", 0))

    if not title:
        return None
    if not is_safe_url(link):
        return None

    return {
        "title": title,
        "content": content,
        "link": link,
        "score": max(score, 0),
        "comments": max(comments, 0),
        "subreddit": subreddit,
        "source": source,
    }


def dedupe_posts(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    results = []
    for p in posts:
        key = (p.get("title", "").lower(), p.get("link", ""))
        if key in seen:
            continue
        seen.add(key)
        results.append(p)
    return results


def extract_mentions(text: str) -> List[str]:
    text_lower = text.lower()
    matches = []

    for brand in KNOWN_BRANDS:
        if brand.lower() in text_lower:
            matches.append(brand)

    for keyword in PRODUCT_KEYWORDS:
        if keyword.lower() in text_lower:
            matches.append(keyword)

    return matches


def get_search_url(brand: str) -> str:
    q = quote(f"{brand} best product")
    return f"https://www.reddit.com/search/?q={q}&sort=relevance&t=month"


# ---------------------------
# 抓取函式
# ---------------------------
def fetch_redlib(session: requests.Session, sub: str) -> List[Dict[str, Any]]:
    posts: List[Dict[str, Any]] = []

    for base_url in REDLIB_INSTANCES:
        if not domain_in_allowlist(base_url):
            continue

        try:
            url = f"{base_url}/r/{sub}"
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                logger.info("Redlib non-200 for %s via %s: %s", sub, base_url, resp.status_code)
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            for post_el in soup.select(".post")[:MAX_POSTS_PER_SOURCE]:
                title_el = post_el.select_one(".post_title a, .post_link")
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                href = title_el.get("href", "").strip()

                body_el = post_el.select_one(".post_body, .post_text")
                body = body_el.get_text(strip=True) if body_el else ""

                score_el = post_el.select_one(".post_score, .score")
                score = safe_int(score_el.get_text(strip=True) if score_el else "0")

                comment_el = post_el.select_one(".post_comments a, .comment_count")
                comments = safe_int(comment_el.get_text(strip=True) if comment_el else "0")

                full_url = href if href.startswith("http") else f"{base_url}{href}"
                if not is_safe_url(full_url):
                    continue

                post = normalize_post(
                    {
                        "title": title,
                        "content": body,
                        "link": full_url,
                        "score": score,
                        "comments": comments,
                    },
                    subreddit=sub,
                    source="redlib",
                )
                if post:
                    posts.append(post)

            if posts:
                return dedupe_posts(posts)

        except requests.RequestException as e:
            logger.warning("fetch_redlib request failed for %s via %s: %s", sub, base_url, e)
        except Exception as e:
            logger.warning("fetch_redlib parse failed for %s via %s: %s", sub, base_url, e)

    return []


def fetch_google_reddit(session: requests.Session, query: str, subreddit: str = "search") -> List[Dict[str, Any]]:
    posts: List[Dict[str, Any]] = []
    params = {"q": f"site:reddit.com {query}", "num": 10, "hl": "en"}

    try:
        resp = session.get(
            "https://www.google.com/search",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.info("Google non-200 for query=%s: %s", query, resp.status_code)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        for result in soup.select("div.g, div[data-sokoban-container]"):
            link_el = result.select_one("a[href]")
            title_el = result.select_one("h3")
            snippet_el = result.select_one(".VwiC3b, .IsZvec")

            if not link_el or not title_el:
                continue

            href = link_el.get("href", "").strip()
            title = title_el.get_text(strip=True)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            if "reddit.com" not in href:
                continue
            if not is_safe_url(href):
                continue

            post = normalize_post(
                {
                    "title": title,
                    "content": snippet,
                    "link": href,
                    "score": 0,
                    "comments": 0,
                },
                subreddit=subreddit,
                source="google",
            )
            if post:
                posts.append(post)

    except requests.RequestException as e:
        logger.warning("fetch_google_reddit request failed for query=%s: %s", query, e)
    except Exception as e:
        logger.warning("fetch_google_reddit parse failed for query=%s: %s", query, e)

    return dedupe_posts(posts)


def fetch_ddg_reddit(session: requests.Session, query: str, subreddit: str = "search") -> List[Dict[str, Any]]:
    posts: List[Dict[str, Any]] = []

    try:
        resp = session.get(
            "https://lite.duckduckgo.com/lite/",
            params={"q": f"site:reddit.com {query}"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.info("DDG non-200 for query=%s: %s", query, resp.status_code)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        for link in soup.select("a.result-link")[:10]:
            href = link.get("href", "").strip()
            title = link.get_text(strip=True)

            if "reddit.com" not in href:
                continue
            if not is_safe_url(href):
                continue

            post = normalize_post(
                {
                    "title": title,
                    "content": "",
                    "link": href,
                    "score": 0,
                    "comments": 0,
                },
                subreddit=subreddit,
                source="duckduckgo",
            )
            if post:
                posts.append(post)

    except requests.RequestException as e:
        logger.warning("fetch_ddg_reddit request failed for query=%s: %s", query, e)
    except Exception as e:
        logger.warning("fetch_ddg_reddit parse failed for query=%s: %s", query, e)

    return dedupe_posts(posts)


# ---------------------------
# 主分析邏輯
# ---------------------------
def aggregate_brand_stats(all_posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    brand_stats: Dict[str, Dict[str, Any]] = {}

    for post in all_posts:
        engagement = post["score"] + post["comments"] * 2
        combined = f"{post['title']} {post['content']}"
        mentions = extract_mentions(combined)

        if not mentions:
            continue

        for mention in mentions:
            if mention not in brand_stats:
                brand_stats[mention] = {
                    "brand": mention,
                    "total_engagement": 0,
                    "mention_count": 0,
                    "total_score": 0,
                    "total_comments": 0,
                    "top_posts": [],
                }

            item = brand_stats[mention]
            item["total_engagement"] += engagement
            item["mention_count"] += 1
            item["total_score"] += post["score"]
            item["total_comments"] += post["comments"]

            if len(item["top_posts"]) < MAX_TOP_POSTS_PER_BRAND:
                item["top_posts"].append(post)
            else:
                smallest_idx = min(
                    range(len(item["top_posts"])),
                    key=lambda i: item["top_posts"][i]["score"] + item["top_posts"][i]["comments"] * 2,
                )
                smallest_value = (
                    item["top_posts"][smallest_idx]["score"]
                    + item["top_posts"][smallest_idx]["comments"] * 2
                )
                if engagement > smallest_value:
                    item["top_posts"][smallest_idx] = post

    results = sorted(
        brand_stats.values(),
        key=lambda x: (x["total_engagement"], x["mention_count"]),
        reverse=True,
    )

    for item in results:
        item["top_posts"] = sorted(
            item["top_posts"],
            key=lambda p: (p["score"] + p["comments"] * 2),
            reverse=True,
        )

    return results[:30]


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_scrape_reddit() -> Dict[str, Any]:
    session = create_session()
    all_posts: List[Dict[str, Any]] = []
    method_counts = Counter()
    progress_logs = []

    for sub in SUBREDDITS:
        progress_logs.append(f"正在抓取 r/{sub}...")

        posts = fetch_redlib(session, sub)

        if posts:
            method_counts["redlib"] += 1
            progress_logs.append(f"✓ r/{sub}: {len(posts)} 筆（redlib）")
        else:
            queries = [
                f"r/{sub} best product",
                f"r/{sub} holy grail",
                f"r/{sub} favorite 2025",
            ]
            temp_posts = []
            for q in queries:
                temp_posts.extend(fetch_google_reddit(session, q, subreddit=sub))
                time.sleep(SEARCH_DELAY_SECONDS)

            if temp_posts:
                posts = dedupe_posts(temp_posts)
                method_counts["google"] += 1
                progress_logs.append(f"✓ r/{sub}: {len(posts)} 筆（Google）")
            else:
                temp_posts = []
                for q in queries:
                    temp_posts.extend(fetch_ddg_reddit(session, q, subreddit=sub))
                    time.sleep(SEARCH_DELAY_SECONDS)

                if temp_posts:
                    posts = dedupe_posts(temp_posts)
                    method_counts["ddg"] += 1
                    progress_logs.append(f"✓ r/{sub}: {len(posts)} 筆（DuckDuckGo）")
                else:
                    method_counts["failed"] += 1
                    progress_logs.append(f"✗ r/{sub}: 所有方法失敗")
                    posts = []

        all_posts.extend(posts)
        time.sleep(SEARCH_DELAY_SECONDS)

    search_queries = [
        "best makeup 2025 reddit",
        "holy grail beauty product reddit",
        "favorite skincare reddit",
        "best foundation reddit",
        "best blush reddit",
        "best serum reddit",
        "best moisturizer reddit",
        "must have beauty product reddit",
        "best drugstore makeup reddit",
        "HG makeup reddit",
    ]

    for query in search_queries:
        progress_logs.append(f"搜尋：{query}")
        posts = fetch_google_reddit(session, query)
        if not posts:
            posts = fetch_ddg_reddit(session, query)

        all_posts.extend(posts)
        time.sleep(SEARCH_DELAY_SECONDS)

    all_posts = dedupe_posts(all_posts)
    products = aggregate_brand_stats(all_posts)

    return {
        "products": products,
        "post_count": len(all_posts),
        "method_counts": dict(method_counts),
        "progress_logs": progress_logs,
        "generated_at": int(time.time()),
    }


def check_rate_limit() -> bool:
    now = time.time()
    last_run = st.session_state.get("last_run_ts", 0)

    if now - last_run < SESSION_RATE_LIMIT_SECONDS:
        remain = int(SESSION_RATE_LIMIT_SECONDS - (now - last_run))
        st.warning(f"請稍候再試，約 {remain} 秒後可重新抓取。")
        return False

    st.session_state["last_run_ts"] = now
    return True


# ---------------------------
# UI
# ---------------------------
st.title("💄 北美流行化妝品排名")
st.caption("從美妝相關 Reddit 討論來源整理熱門品牌／產品關鍵字排行")

with st.expander("資料來源與限制", expanded=False):
    st.write("• 來源包含 Reddit 相關搜尋結果與公開鏡像頁面。")
    st.write("• 本工具為趨勢觀察用途，不代表官方銷量、專業評測或醫療建議。")
    st.write("• 搜尋結果頁結構可能變動，因此資料完整性與穩定性有限。")

col_a, col_b = st.columns([2, 1])

with col_a:
    if st.button("🔍 開始分析", type="primary", use_container_width=True):
        if check_rate_limit():
            with st.spinner("正在抓取與分析資料，請稍候..."):
                result = cached_scrape_reddit()
                st.session_state["result"] = result

with col_b:
    if st.button("♻️ 重新整理快取結果", use_container_width=True):
        cached_scrape_reddit.clear()
        st.success("快取已清除，下一次會重新抓取。")

if "result" not in st.session_state:
    st.info("點擊「開始分析」後，系統會整理北美美妝熱門討論。")
else:
    result = st.session_state["result"]
    products = result["products"]
    post_count = result["post_count"]
    method_counts = result["method_counts"]
    progress_logs = result["progress_logs"]

    c1, c2, c3 = st.columns(3)
    c1.metric("熱門品牌/產品", len(products))
    c2.metric("分析貼文數", post_count)
    c3.metric("爬取版面", len(SUBREDDITS))

    st.divider()

    method_text = " / ".join(f"{k}: {v}" for k, v in method_counts.items()) if method_counts else "無統計"
    st.caption(f"抓取方式統計：{method_text}")

    with st.expander("抓取紀錄", expanded=False):
        for line in progress_logs:
            st.write(sanitize_text(line, 300))

    st.subheader("排行榜")

    for idx, item in enumerate(products, start=1):
        brand = sanitize_text(item["brand"], 100)
        search_url = get_search_url(brand)

        with st.container(border=True):
            left, right = st.columns([3, 1])

            with left:
                st.markdown(f"### #{idx} {html.escape(brand)}")
                st.write(
                    f"提及次數：{item['mention_count']} ｜ "
                    f"互動分：{item['total_engagement']} ｜ "
                    f"貼文分數：{item['total_score']} ｜ "
                    f"留言數：{item['total_comments']}"
                )

                if is_safe_url(search_url):
                    st.link_button(
                        label=f"在 Reddit 搜尋 {brand}",
                        url=search_url,
                        use_container_width=False,
                    )

            with right:
                st.metric("提及次數", item["mention_count"])
                st.metric("互動分", item["total_engagement"])

            if item["top_posts"]:
                with st.expander("查看代表貼文", expanded=False):
                    for post in item["top_posts"]:
                        title = sanitize_text(post["title"], 120)
                        source = sanitize_text(post["source"], 20)
                        subreddit = sanitize_text(post["subreddit"], 40)
                        score = post["score"]
                        comments = post["comments"]
                        link = post["link"]

                        st.write(
                            f"**{title}**  \n"
                            f"來源：{source} ｜ 版面：{subreddit} ｜ "
                            f"分數：{score} ｜ 留言：{comments}"
                        )

                        if is_safe_url(link):
                            st.link_button(
                                label=f"開啟貼文：{title[:40]}",
                                url=link,
                                use_container_width=False,
                            )

    st.divider()
    st.subheader("原始統計表")

    df_data = [
        {
            "排名": i + 1,
            "品牌/產品": sanitize_text(p["brand"], 100),
            "提及次數": p["mention_count"],
            "互動分": p["total_engagement"],
            "貼文分數": p["total_score"],
            "留言數": p["total_comments"],
        }
        for i, p in enumerate(products)
    ]

    df = pd.DataFrame(df_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
