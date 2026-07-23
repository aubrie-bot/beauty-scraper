import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from urllib.parse import quote

SUBREDDITS = [
    "MakeupAddiction",
    "SkincareAddiction",
    "drugstoreMUA",
    "BeautyGuruChatter",
    "AsianBeauty",
]

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
]

def get_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA_LIST[0],
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s

def try_json(session, url, params=None):
    try:
        resp = session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("data", {}).get("children", [])
    except Exception:
        return None

def try_rss(session, url):
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        entries = []
        for entry in root.findall(".//entry") or root.findall(".//{http://www.w3.org/2005/Atom}entry"):
            title = entry.findtext("title") or ""
            content_el = entry.find("content") or entry.find("{http://www.w3.org/2005/Atom}content")
            content = content_el.text if content_el is not None else ""
            link_el = entry.find("link") or entry.find("{http://www.w3.org/2005/Atom}link")
            link = link_el.get("href", "") if link_el is not None else ""
            author_el = entry.find("author") or entry.find("{http://www.w3.org/2005/Atom}author")
            author_name = ""
            if author_el is not None:
                name_el = author_el.find("name") or author_el.find("{http://www.w3.org/2005/Atom}name")
                author_name = name_el.text if name_el is not None else ""
            entries.append({"title": title, "content": content or "", "link": link, "author": author_name})
        return entries
    except Exception:
        return None

def try_html(session, url):
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        posts = []
        for post in soup.select("a[data-click-id='body'], a[data-href-click='post'], div[data-testid='post-container']"):
            title = post.get("aria-label", "") or post.get_text(strip=True)[:200]
            href = post.get("href", "")
            if title and href:
                posts.append({"title": title, "content": "", "link": f"https://www.reddit.com{href}" if href.startswith("/") else href})
        return posts
    except Exception:
        return None


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


def scrape_reddit():
    session = get_session()
    all_posts = []
    methods_used = {"json": 0, "rss": 0, "html": 0, "none": 0}

    with st.status("爬取 Reddit 中...", expanded=True) as status:
        for sub in SUBREDDITS:
            st.write(f"正在爬取 r/{sub}...")
            posts_data = []

            data = try_json(session, f"https://www.reddit.com/r/{sub}/hot.json", {"limit": 50, "t": "week"})
            if data is not None:
                for item in data:
                    d = item.get("data", {})
                    posts_data.append({
                        "title": d.get("title", ""),
                        "content": d.get("selftext", ""),
                        "link": f"https://reddit.com{d.get('permalink', '')}",
                        "score": d.get("score", 0),
                        "comments": d.get("num_comments", 0),
                    })
                methods_used["json"] += 1
            else:
                data = try_json(session, f"https://old.reddit.com/r/{sub}/hot.json", {"limit": 50, "t": "week"})
                if data is not None:
                    for item in data:
                        d = item.get("data", {})
                        posts_data.append({
                            "title": d.get("title", ""),
                            "content": d.get("selftext", ""),
                            "link": f"https://reddit.com{d.get('permalink', '')}",
                            "score": d.get("score", 0),
                            "comments": d.get("num_comments", 0),
                        })
                    methods_used["json"] += 1

            if not posts_data:
                entries = try_rss(session, f"https://www.reddit.com/r/{sub}/.rss")
                if entries is not None:
                    for e in entries:
                        posts_data.append({
                            "title": e["title"],
                            "content": e["content"],
                            "link": e["link"],
                            "score": 0,
                            "comments": 0,
                        })
                    methods_used["rss"] += 1

            if not posts_data:
                entries = try_rss(session, f"https://www.reddit.com/r/{sub}/hot/.rss?limit=50")
                if entries is not None:
                    for e in entries:
                        posts_data.append({
                            "title": e["title"],
                            "content": e["content"],
                            "link": e["link"],
                            "score": 0,
                            "comments": 0,
                        })
                    methods_used["rss"] += 1

            if not posts_data:
                html_posts = try_html(session, f"https://www.reddit.com/r/{sub}/hot/")
                if html_posts:
                    for hp in html_posts:
                        posts_data.append({**hp, "score": 0, "comments": 0})
                    methods_used["html"] += 1
                else:
                    methods_used["none"] += 1
                    st.warning(f"r/{sub} 所有方法均失敗")

            for p in posts_data:
                combined = f"{p['title']} {p['content']}"
                mentions = extract_mentions(combined)
                if mentions:
                    all_posts.append({**p, "subreddit": sub, "mentions": mentions})

            time.sleep(1.5)

        search_queries = [
            "best makeup 2025", "holy grail product", "favorite skincare",
            "best foundation", "best blush", "best serum", "best moisturizer",
            "must have beauty", "best drugstore makeup", "HG products",
        ]

        for query in search_queries:
            st.write(f"搜尋: {query}...")
            data = try_json(session, "https://www.reddit.com/search.json", {"q": query, "sort": "top", "t": "month", "limit": 25})
            if data is None:
                data = try_json(session, "https://old.reddit.com/search.json", {"q": query, "sort": "top", "t": "month", "limit": 25})
            if data is not None:
                for item in data:
                    d = item.get("data", {})
                    combined = f"{d.get('title', '')} {d.get('selftext', '')}"
                    mentions = extract_mentions(combined)
                    if mentions:
                        all_posts.append({
                            "title": d.get("title", ""),
                            "content": d.get("selftext", ""),
                            "link": f"https://reddit.com{d.get('permalink', '')}",
                            "score": d.get("score", 0),
                            "comments": d.get("num_comments", 0),
                            "subreddit": "search",
                            "mentions": mentions,
                        })
                methods_used["json"] += 1
            else:
                rss_entries = try_rss(session, f"https://www.reddit.com/search/.rss?q={quote(query)}&sort=top&t=month")
                if rss_entries:
                    for e in rss_entries:
                        mentions = extract_mentions(f"{e['title']} {e['content']}")
                        if mentions:
                            all_posts.append({
                                "title": e["title"], "content": e["content"],
                                "link": e["link"], "score": 0, "comments": 0,
                                "subreddit": "search", "mentions": mentions,
                            })
                    methods_used["rss"] += 1
                else:
                    methods_used["none"] += 1
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

        status.update(label=f"爬取完成！（JSON:{methods_used['json']} RSS:{methods_used['rss']} HTML:{methods_used['html']}）", state="complete")

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

    **多層爬取策略：** JSON API → RSS Feed → HTML 解析，自動嘗試直到成功
    """)
