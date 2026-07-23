import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from urllib.parse import quote, urlencode

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

GOOGLE_HTML_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

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


def extract_mentions(text):
    text_lower = text.lower()
    return [b for b in KNOWN_BRANDS if b.lower() in text_lower] + \
           [k for k in PRODUCT_KEYWORDS if k.lower() in text_lower]


def fetch_redlib(session, sub):
    """Fetch subreddit posts from redlib public instances."""
    for base_url in REDLIB_INSTANCES:
        try:
            resp = session.get(f"{base_url}/r/{sub}", timeout=12, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            posts = []
            for post_el in soup.select(".post"):
                title_el = post_el.select_one(".post_title a, .post_link")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                body_el = post_el.select_one(".post_body, .post_text")
                body = body_el.get_text(strip=True) if body_el else ""
                score_el = post_el.select_one(".post_score, .score")
                score_text = score_el.get_text(strip=True) if score_el else "0"
                score = int(re.sub(r"[^0-9-]", "", score_text) or "0")
                comment_el = post_el.select_one(".post_comments a, .comment_count")
                comments = 0
                if comment_el:
                    ct = re.sub(r"[^0-9]", "", comment_el.get_text(strip=True))
                    comments = int(ct) if ct else 0
                full_url = href if href.startswith("http") else f"{base_url}{href}"
                posts.append({
                    "title": title, "content": body, "link": full_url,
                    "score": score, "comments": comments,
                })
            if posts:
                return posts
        except Exception:
            continue
    return []


def fetch_google_reddit(session, query):
    """Use Google search to find Reddit posts about beauty products."""
    posts = []
    params = {"q": f"site:reddit.com {query}", "num": 10, "hl": "en"}
    try:
        resp = session.get("https://www.google.com/search", params=params, headers=GOOGLE_HTML_HEADERS, timeout=12)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        for result in soup.select("div.g, div[data-sokoban-container]"):
            link_el = result.select_one("a[href]")
            title_el = result.select_one("h3")
            snippet_el = result.select_one(".VwiC3b, .IsZvec")
            if not link_el or not title_el:
                continue
            href = link_el["href"]
            if "reddit.com" not in href:
                continue
            title = title_el.get_text(strip=True)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            posts.append({
                "title": title, "content": snippet,
                "link": href, "score": 0, "comments": 0,
            })
    except Exception:
        pass
    return posts


def fetch_ddg_reddit(session, query):
    """Use DuckDuckGo Lite to find Reddit beauty posts."""
    posts = []
    try:
        resp = session.get(
            "https://lite.duckduckgo.com/lite/",
            params={"q": f"site:reddit.com {query}"},
            headers=GOOGLE_HTML_HEADERS, timeout=12,
        )
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.select("a.result-link"):
            href = link.get("href", "")
            title = link.get_text(strip=True)
            if "reddit.com" in href:
                posts.append({
                    "title": title, "content": "", "link": href,
                    "score": 0, "comments": 0,
                })
    except Exception:
        pass
    return posts


def scrape_reddit():
    session = requests.Session()
    all_posts = []
    method_counts = Counter()

    with st.status("爬取 Reddit 中...", expanded=True) as status:
        for sub in SUBREDDITS:
            st.write(f"正在爬取 r/{sub}...")

            posts = fetch_redlib(session, sub)
            if posts:
                method_counts["redlib"] += 1
                st.write(f"  ✓ r/{sub}: {len(posts)} 筆 (redlib)")
            else:
                queries = [f"r/{sub} best product", f"r/{sub} holy grail", f"r/{sub} favorite 2025"]
                for q in queries:
                    posts.extend(fetch_google_reddit(session, q))
                    time.sleep(1)
                if posts:
                    method_counts["google"] += 1
                    st.write(f"  ✓ r/{sub}: {len(posts)} 筆 (Google)")
                else:
                    for q in queries:
                        posts.extend(fetch_ddg_reddit(session, q))
                        time.sleep(1)
                    if posts:
                        method_counts["ddg"] += 1
                        st.write(f"  ✓ r/{sub}: {len(posts)} 筆 (DuckDuckGo)")
                    else:
                        method_counts["failed"] += 1
                        st.write(f"  ✗ r/{sub}: 所有方法失敗")

            for p in posts:
                combined = f"{p['title']} {p['content']}"
                mentions = extract_mentions(combined)
                if mentions:
                    all_posts.append({**p, "subreddit": sub, "mentions": mentions})
            time.sleep(1)

        search_queries = [
            "best makeup 2025 reddit", "holy grail beauty product reddit",
            "favorite skincare reddit", "best foundation reddit",
            "best blush reddit", "best serum reddit", "best moisturizer reddit",
            "must have beauty product reddit", "best drugstore makeup reddit",
            "HG makeup reddit",
        ]

        for query in search_queries:
            st.write(f"搜尋: {query}...")
            posts = fetch_google_reddit(session, query)
            if not posts:
                posts = fetch_ddg_reddit(session, query)
            for p in posts:
                combined = f"{p['title']} {p['content']}"
                mentions = extract_mentions(combined)
                if mentions:
                    all_posts.append({**p, "subreddit": "search", "mentions": mentions})
            time.sleep(1.5)

        st.write("分析討論度中...")
        brand_stats = {}
        for post in all_posts:
            engagement = post["score"] + post["comments"] * 2
            for mention in post["mentions"]:
                if mention not in brand_stats:
                    brand_stats[mention] = {
                        "brand": mention, "total_engagement": 0, "mention_count": 0,
                        "total_score": 0, "total_comments": 0, "top_posts": [],
                    }
                brand_stats[mention]["total_engagement"] += engagement
                brand_stats[mention]["mention_count"] += 1
                brand_stats[mention]["total_score"] += post["score"]
                brand_stats[mention]["total_comments"] += post["comments"]
                if len(brand_stats[mention]["top_posts"]) < 3:
                    brand_stats[mention]["top_posts"].append(post)

        method_str = " ".join(f"{k}:{v}" for k, v in method_counts.items())
        status.update(label=f"爬取完成！({method_str})", state="complete")

    sorted_products = sorted(brand_stats.values(), key=lambda x: x["total_engagement"], reverse=True)
    return sorted_products[:30], len(all_posts)


def get_search_url(brand):
    return f"https://www.reddit.com/search/?q={quote(brand + ' best product')}&sort=relevance&t=month"


st.set_page_config(page_title="Reddit 美妝討論度排行", page_icon="💄", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #fce4ec, #f3e5f5);
        border-radius: 12px; padding: 15px 20px;
    }
    [data-testid="stMetric"] label { color: #666; }
    [data-testid="stMetric"] [data-testid="stMetricValue"] { color: #e91e63; }
    .rank-badge {
        display: inline-flex; align-items: center; justify-content: center;
        width: 32px; height: 32px; border-radius: 50%; font-weight: 700;
        font-size: 0.9rem; color: white; margin-right: 10px; flex-shrink: 0;
    }
    .rank-1 { background: linear-gradient(135deg, #FFD700, #FFA000); }
    .rank-2 { background: linear-gradient(135deg, #C0C0C0, #9E9E9E); }
    .rank-3 { background: linear-gradient(135deg, #CD7F32, #8D6E63); }
    .rank-other { background: #e91e63; }
    .product-row {
        display: flex; align-items: center; background: white;
        border-radius: 12px; padding: 16px 20px; margin-bottom: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.06); border: 1px solid #f0f0f0;
    }
    .product-row:hover { transform: translateX(5px); }
    .product-info { flex: 1; }
    .product-info h4 { margin: 0; font-size: 1.1rem; color: #333; }
    .product-info .sub { font-size: 0.8rem; color: #999; margin-top: 2px; }
    .engagement { display: flex; gap: 20px; align-items: center; }
    .engagement .stat { text-align: center; }
    .engagement .stat .num { font-size: 1.2rem; font-weight: 700; color: #e91e63; }
    .engagement .stat .lbl { font-size: 0.7rem; color: #999; }
    .post-link {
        display: inline-block; padding: 4px 12px; background: #fff3e0;
        border-radius: 20px; font-size: 0.75rem; color: #e65100;
        text-decoration: none; margin: 2px;
    }
    .post-link:hover { background: #ffe0b2; }
    .source-tag {
        display: inline-block; padding: 2px 8px; border-radius: 10px;
        font-size: 0.7rem; font-weight: 600; color: white;
        background: #ff4500; margin-left: 8px;
    }
</style>
""", unsafe_allow_html=True)

st.title("Reddit 美妝討論度排行")
st.caption("從 r/MakeupAddiction, r/SkincareAddiction 等北美美妝版爬取討論度最高的產品")

if st.button("🔍 開始爬取 Reddit", type="primary", use_container_width=True):
    products, post_count = scrape_reddit()
    st.session_state["products"] = products
    st.session_state["post_count"] = post_count

if "products" in st.session_state:
    products = st.session_state["products"]
    post_count = st.session_state.get("post_count", 0)

    c1, c2, c3 = st.columns(3)
    c1.metric("熱門品牌/產品", len(products))
    c2.metric("分析貼文數", post_count)
    c3.metric("爬取版面", len(SUBREDDITS))

    st.divider()

    for rank, p in enumerate(products, 1):
        rank_class = f"rank-{rank}" if rank <= 3 else "rank-other"
        top_posts_html = ""
        for tp in p["top_posts"][:3]:
            title_short = tp["title"][:60] + "..." if len(tp["title"]) > 60 else tp["title"]
            top_posts_html += f'<a href="{tp["link"]}" target="_blank" class="post-link" title="{tp["title"]}">💬 {tp["score"]}↑ {title_short}</a> '
        search_url = get_search_url(p["brand"])

        st.markdown(f"""
        <div class="product-row">
            <div class="rank-badge {rank_class}">#{rank}</div>
            <div class="product-info">
                <h4>{p['brand']} <span class="source-tag">Reddit</span></h4>
                <div class="sub">被提及 {p['mention_count']} 次 ・ 總互動 {p['total_engagement']} ・ 帖文 {p['total_score']}↑ / {p['total_comments']}💬</div>
                <div style="margin-top:6px;">{top_posts_html}</div>
            </div>
            <div class="engagement">
                <div class="stat"><div class="num">{p['mention_count']}</div><div class="lbl">提及次數</div></div>
                <div class="stat"><div class="num">{p['total_engagement']}</div><div class="lbl">互動分</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f'<div style="text-align:right;margin-top:-8px;margin-bottom:8px;"><a href="{search_url}" target="_blank" style="font-size:0.8rem;color:#e91e63;">在 Reddit 搜尋 {p["brand"]} →</a></div>', unsafe_allow_html=True)

    st.divider()
    st.subheader("原始資料")
    df_data = [{
        "排名": i + 1,
        "品牌/產品": p["brand"],
        "提及次數": p["mention_count"],
        "互動分": p["total_engagement"],
        "帖文分數": p["total_score"],
        "留言數": p["total_comments"],
    } for i, p in enumerate(products)]
    st.dataframe(pd.DataFrame(df_data), use_container_width=True, hide_index=True)
else:
    st.info("點擊上方「開始爬取 Reddit」按鈕，分析北美美妝版討論度最高的產品。")
    st.markdown("""
    **爬取範圍：**
    - r/MakeupAddiction、r/SkincareAddiction、r/drugstoreMUA
    - r/BeautyGuruChatter、r/AsianBeauty
    - Reddit 全站美妝關鍵字搜尋

    **多層爬取策略：** redlib 鏡像 → Google 搜尋 → DuckDuckGo 搜尋
    """)
