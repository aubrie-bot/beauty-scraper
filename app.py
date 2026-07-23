import time
import html
import logging

import pandas as pd
import streamlit as st

from utils import (
    SUBREDDITS,
    get_reddit_search_url,
    is_safe_url,
    run_analysis,
    sanitize_text,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="北美流行化妝品排行",
    page_icon="💄",
    layout="wide",
)

CACHE_TTL_SECONDS = 3600
SESSION_RATE_LIMIT_SECONDS = 180

CUSTOM_CSS = """
<style>
    .main {
        background: linear-gradient(180deg, #fff8fb 0%, #fff 100%);
    }
    .hero {
        padding: 1.2rem 1.4rem;
        border-radius: 20px;
        background: linear-gradient(135deg, #ffedf4 0%, #f7ecff 100%);
        border: 1px solid rgba(233, 30, 99, 0.12);
        margin-bottom: 1rem;
    }
    .hero h1 {
        margin: 0;
        color: #c2185b;
        font-size: 2rem;
    }
    .hero p {
        margin: 0.5rem 0 0 0;
        color: #6a5160;
        font-size: 0.98rem;
    }
    .card {
        background: #ffffff;
        border: 1px solid #f1d8e4;
        border-radius: 18px;
        padding: 16px 18px;
        box-shadow: 0 6px 20px rgba(80, 20, 50, 0.05);
        margin-bottom: 12px;
    }
    .rank {
        font-size: 1.15rem;
        font-weight: 800;
        color: #d81b60;
    }
    .subtle {
        color: #7a6a72;
        font-size: 0.9rem;
    }
    .tiny {
        color: #8d7b84;
        font-size: 0.8rem;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_run_analysis(
    selected_subreddits,
    allowed_categories,
    only_2026,
    include_hot,
    include_top_year,
    include_new,
    per_feed_limit,
):
    return run_analysis(
        selected_subreddits=list(selected_subreddits),
        allowed_categories=list(allowed_categories),
        only_2026=only_2026,
        include_hot=include_hot,
        include_top_year=include_top_year,
        include_new=include_new,
        per_feed_limit=per_feed_limit,
    )


def check_rate_limit() -> bool:
    now = time.time()
    last_run = st.session_state.get("last_run_ts", 0)
    if now - last_run < SESSION_RATE_LIMIT_SECONDS:
        wait_sec = int(SESSION_RATE_LIMIT_SECONDS - (now - last_run))
        st.warning(f"請稍候再重新分析，約 {wait_sec} 秒後可再次執行。")
        return False
    st.session_state["last_run_ts"] = now
    return True


st.markdown("""
<div class="hero">
    <h1>💄 北美流行化妝品排行</h1>
    <p>
        依據 Reddit 美妝社群公開貼文整理品牌／彩妝關鍵字熱度，
        適合做北美美妝趨勢觀察、作品集展示與市場研究草稿。
    </p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 分析設定")

    selected_subreddits = st.multiselect(
        "選擇要分析的 subreddit",
        SUBREDDITS,
        default=SUBREDDITS,
    )

    category_label = st.radio(
        "分析範圍",
        ["只看彩妝", "只看保養", "彩妝 + 保養"],
        index=0,
    )

    if category_label == "只看彩妝":
        allowed_categories = ["makeup"]
    elif category_label == "只看保養":
        allowed_categories = ["skincare"]
    else:
        allowed_categories = ["makeup", "skincare"]

    only_2026 = st.toggle("只分析 2026 熱門內容", value=True)

    st.divider()
    st.caption("資料源設定")

    include_hot = st.checkbox("抓取 Hot", value=True)
    include_top_year = st.checkbox("抓取 Top（year）", value=True)
    include_new = st.checkbox("抓取 New", value=False)

    per_feed_limit = st.slider(
        "每個 feed 抓取數量",
        min_value=10,
        max_value=50,
        value=25,
        step=5,
    )

    st.divider()
    if st.button("♻️ 清除快取", width="stretch"):
        cached_run_analysis.clear()
        st.success("已清除快取。")

col1, col2, col3 = st.columns(3)
col1.metric("預設分析社群", len(selected_subreddits))
col2.metric("資料來源", "Reddit JSON")
col3.metric("年度篩選", "2026" if only_2026 else "不限")

with st.expander("資料來源與方法說明", expanded=False):
    st.write("• 本版優先使用 Reddit 公開 JSON feed，而非搜尋引擎 HTML 爬取。")
    st.write("• 可分析 hot / top(year) / new 三種貼文流。")
    st.write("• 2026 篩選為作品集用途的趨勢過濾，屬啟發式規則，不是官方年份標記。")
    st.write("• 本工具適合做市場趨勢觀察，不代表實際銷售排行。")

run_col, info_col = st.columns([1.2, 2])

with run_col:
    run_clicked = st.button("🔍 開始分析", type="primary", width="stretch")

with info_col:
    st.info("建議先分析彩妝類別；若要更廣的美容趨勢，再切換成「彩妝 + 保養」。")

if run_clicked:
    if not selected_subreddits:
        st.error("請至少選擇一個 subreddit。")
    elif not (include_hot or include_top_year or include_new):
        st.error("請至少選擇一種資料源 feed。")
    elif check_rate_limit():
        with st.spinner("正在抓取 Reddit 公開資料並分析，請稍候..."):
            result = cached_run_analysis(
                tuple(selected_subreddits),
                tuple(allowed_categories),
                only_2026,
                include_hot,
                include_top_year,
                include_new,
                per_feed_limit,
            )
            st.session_state["result"] = result

if "result" in st.session_state:
    result = st.session_state["result"]
    products = result["products"]
    raw_post_count = result["raw_post_count"]
    filtered_post_count = result["filtered_post_count"]
    method_counts = result["method_counts"]
    progress_logs = result["progress_logs"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("抓取原始貼文", raw_post_count)
    m2.metric("有效分析貼文", filtered_post_count)
    m3.metric("熱門品牌/關鍵字", len(products))
    m4.metric("分析社群", len(selected_subreddits))

    st.caption(
        "Feed 統計：" +
        " / ".join(f"{k}: {v}" for k, v in method_counts.items()) if method_counts else "Feed 統計：無"
    )

    with st.expander("抓取紀錄", expanded=False):
        for line in progress_logs:
            st.write(sanitize_text(line, 300))

    st.divider()
    st.subheader("🏆 排行榜")

    if not products:
        st.warning("目前沒有符合條件的結果。你可以關閉「只分析 2026 熱門內容」後再試一次。")
    else:
        for idx, item in enumerate(products, start=1):
            brand = sanitize_text(item["brand"], 100)
            mention_count = item["mention_count"]
            total_engagement = item["total_engagement"]
            total_score = item["total_score"]
            total_comments = item["total_comments"]
            subreddits = ", ".join(item.get("subreddits", []))
            reddit_search_url = get_reddit_search_url(brand)

            st.markdown(f"""
            <div class="card">
                <div class="rank">#{idx} {html.escape(brand)}</div>
                <div class="subtle">
                    提及次數：{mention_count} ｜ 互動分：{total_engagement} ｜ 
                    帖文分數：{total_score} ｜ 留言數：{total_comments}
                </div>
                <div class="tiny">出現版面：{html.escape(subreddits)}</div>
            </div>
            """, unsafe_allow_html=True)

            b1, b2 = st.columns([1, 4])
            with b1:
                if is_safe_url(reddit_search_url):
                    st.link_button(f"搜尋 {brand}", reddit_search_url, width="stretch")

            with b2:
                with st.expander("查看代表貼文", expanded=False):
                    top_posts = item.get("top_posts", [])
                    if not top_posts:
                        st.write("無代表貼文")
                    else:
                        for p in top_posts:
                            title = sanitize_text(p["title"], 140)
                            subreddit = sanitize_text(p["subreddit"], 40)
                            source = sanitize_text(p["source"], 40)
                            score = p["score"]
                            comments = p["comments"]
                            link = p["link"]

                            st.write(
                                f"**{title}**  \n"
                                f"版面：{subreddit} ｜ 來源：{source} ｜ 👍 {score} ｜ 💬 {comments}"
                            )

                            if is_safe_url(link):
                                st.link_button(
                                    label=f"開啟貼文：{title[:36]}",
                                    url=link,
                                    width="content",
                                )

        st.divider()
        st.subheader("📊 原始統計表")

        df = pd.DataFrame([
            {
                "排名": i + 1,
                "品牌/關鍵字": sanitize_text(p["brand"], 100),
                "提及次數": p["mention_count"],
                "互動分": p["total_engagement"],
                "貼文分數": p["total_score"],
                "留言數": p["total_comments"],
                "出現版面": ", ".join(p.get("subreddits", [])),
            }
            for i, p in enumerate(products)
        ])

        st.dataframe(df, width="stretch", hide_index=True)

else:
    st.info("請在左側設定條件後，點擊「開始分析」。")
