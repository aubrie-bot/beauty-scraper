import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from collections import Counter
from urllib.parse import quote

SUBREDDITS = [
    "MakeupAddiction",
    "SkincareAddiction",
    "drugstoreMUA",
    "BeautyGuruChatter",
    "AsianBeauty",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

KNOWN_BRANDS = [
    "Rare Beauty", "Fenty Beauty", "NARS", "Charlotte Tilbury", "MAC",
    "Urban Decay", "Too Faced", "Tarte", "Benefit", "Clinique",
    "Estee Lauder", "Lancome", "Maybelline", "L'Oreal", "Revlon",
    "NYX", "e.l.f.", "Elf", "CeraVe", "The Ordinary", "Paula's Choice",
    "Drunk Elephant", "Tatcha", "Glossier", "Tower 28", "Kosas",
    "Patrick Ta", "Makeup by Mario", "Natasha Denona", "Patrick Ta",
    "Huda Beauty", "Anastasia Beverly Hills", "ABH", "Morphe",
    "Laura Mercier", "Bobbi Brown", "Dior", "Chanel", "YSL",
    "Tom Ford", "Hourglass", "Natasha Denona", "Colourpop", "ColourPop",
    "IT Cosmetics", "Mario Badescu", "First Aid Beauty", "Fresh",
    "Laneige", "Innisfree", "Etude House", "Missha", "COSRX",
]

PRODUCT_KEYWORDS = [
    "blush", "foundation", "concealer", "mascara", "lipstick", "lip gloss",
    "eyeshadow", "palette", "serum", "moisturizer", "cleanser", "sunscreen",
    "SPF", "retinol", "vitamin c", "niacinamide", "hyaluronic acid",
    "toner", "exfoliant", "primer", "setting spray", "setting powder",
    "bronzer", "highlighter", "brow", "liner", "shadow",
    "cream", "lotion", "oil", "mask", "peel", "essence",
    "best product", "Holy Grail", "HG", "holy grail", "favorite",
    "recommend", "must have", "best of", "top product",
]


def fetch_reddit_json(subreddit, sort="hot", limit=25, time_filter="week"):
    url = f"https://old.reddit.com/r/{subreddit}/{sort}.json"
    params = {"limit": limit, "t": time_filter}
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("children", [])
    except Exception as e:
        st.warning(f"r/{subreddit} 爬取失敗: {e}")
        return []


def fetch_reddit_search(query, subreddit=None, sort="relevance", limit=25):
    if subreddit:
        url = f"https://old.reddit.com/r/{subreddit}/search.json"
        params = {"q": query, "restrict_sr": "on", "sort": sort, "t": "month", "limit": limit}
    else:
        url = "https://old.reddit.com/search.json"
        params = {"q": query, "sort": sort, "t": "month", "limit": limit}
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("children", [])
    except Exception:
        return []


def extract_product_mentions(text):
    text_lower = text.lower()
    mentions = []
    for brand in KNOWN_BRANDS:
        if brand.lower() in text_lower:
            mentions.append(brand)
    for kw in PRODUCT_KEYWORDS:
        if kw.lower() in text_lower:
            mentions.append(kw)
    return mentions


def scrape_reddit_beauty():
    products = []
    post_count = Counter()

    search_queries = [
        "best makeup 2025",
        "holy grail product",
        "favorite skincare",
        "best foundation",
        "best blush",
        "best serum",
        "best moisturizer",
        "must have beauty",
        "best drugstore makeup",
        "HG products",
        "best mascara",
        "best lipstick",
        "best eyeshadow palette",
    ]

    all_posts = []

    with st.status("爬取 Reddit 中...", expanded=True) as status:
        for sub in SUBREDDITS:
            st.write(f"正在爬取 r/{sub}...")
            posts = fetch_reddit_json(sub, sort="hot", limit=50, time_filter="month")
            for post in posts:
                d = post.get("data", {})
                title = d.get("title", "")
                selftext = d.get("selftext", "")
                score = d.get("score", 0)
                num_comments = d.get("num_comments", 0)
                permalink = d.get("permalink", "")
                combined = f"{title} {selftext}"
                mentions = extract_product_mentions(combined)
                if mentions:
                    all_posts.append({
                        "title": title,
                        "text": selftext,
                        "score": score,
                        "comments": num_comments,
                        "url": f"https://reddit.com{permalink}",
                        "subreddit": sub,
                        "mentions": mentions,
                    })
            time.sleep(1)

        for query in search_queries:
            st.write(f"搜尋: {query}...")
            posts = fetch_reddit_search(query, sort="top", limit=25)
            for post in posts:
                d = post.get("data", {})
                title = d.get("title", "")
                selftext = d.get("selftext", "")
                score = d.get("score", 0)
                num_comments = d.get("num_comments", 0)
                permalink = d.get("permalink", "")
                combined = f"{title} {selftext}"
                mentions = extract_product_mentions(combined)
                if mentions:
                    all_posts.append({
                        "title": title,
                        "text": selftext,
                        "score": score,
                        "comments": num_comments,
                        "url": f"https://reddit.com{permalink}",
                        "subreddit": "search",
                        "mentions": mentions,
                    })
            time.sleep(1)

        st.write("分析討論度中...")
        brand_stats = {}
        for post in all_posts:
            engagement = post["score"] + post["comments"] * 2
            for mention in post["mentions"]:
                if mention not in brand_stats:
                    brand_stats[mention] = {
                        "brand": mention,
                        "total_engagement": 0,
                        "mention_count": 0,
                        "total_score": 0,
                        "total_comments": 0,
                        "top_posts": [],
                    }
                brand_stats[mention]["total_engagement"] += engagement
                brand_stats[mention]["mention_count"] += 1
                brand_stats[mention]["total_score"] += post["score"]
                brand_stats[mention]["total_comments"] += post["comments"]
                if len(brand_stats[mention]["top_posts"]) < 3:
                    brand_stats[mention]["top_posts"].append(post)

        status.update(label="爬取完成！", state="complete")

    sorted_products = sorted(brand_stats.values(), key=lambda x: x["total_engagement"], reverse=True)
    return sorted_products[:30], len(all_posts)


def get_search_url(brand):
    query = quote(f"{brand} best product")
    return f"https://www.reddit.com/search/?q={query}&sort=relevance&t=month"


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
        transition: transform 0.2s;
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
    products, post_count = scrape_reddit_beauty()
    st.session_state["products"] = products
    st.session_state["post_count"] = post_count

if "products" in st.session_state:
    products = st.session_state["products"]
    post_count = st.session_state.get("post_count", 0)

    c1, c2, c3 = st.columns(3)
    c1.metric("熱門產品/品牌", len(products))
    c2.metric("分析貼文數", post_count)
    c3.metric("爬取版面", len(SUBREDDITS))

    st.divider()

    for rank, p in enumerate(products, 1):
        rank_class = f"rank-{rank}" if rank <= 3 else "rank-other"
        top_posts_html = ""
        for tp in p["top_posts"][:3]:
            title_short = tp["title"][:60] + "..." if len(tp["title"]) > 60 else tp["title"]
            top_posts_html += f'<a href="{tp["url"]}" target="_blank" class="post-link" title="{tp["title"]}">💬 {tp["score"]}↑ {title_short}</a> '
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
    - r/MakeupAddiction
    - r/SkincareAddiction
    - r/drugstoreMUA
    - r/BeautyGuruChatter
    - r/AsianBeauty
    - Reddit 全站美妝關鍵字搜尋

    **排名邏輯：** 以品牌/產品在貼文中的出現次數 × 互動分（帖文分數 + 留言×2）排序
    """)
