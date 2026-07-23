import html
import time

import pandas as pd
import streamlit as st

from utils import (
    SUBREDDITS,
    get_reddit_search_url,
    is_safe_url,
    run_analysis,
    sanitize_text,
)

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


def clear_all_state():
    st.cache_data.clear()
    for key in list(st.session_state.keys()):
        del st.session_state[key]


st.markdown("""
<div class="hero">
    <h1>💄 北美流行化妝品排行</h1>
    <p>依據 Reddit 公開貼文整理品牌／彩妝／保養關鍵字熱度，適合做美妝趨勢觀察與作品集展示。</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 分析設定")

    selected_subreddits = st.multiselect(
        "選擇 subreddit",
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
    st.caption("Reddit Feed 設定")

    include_hot = st.checkbox("Hot", value=True)
    include_top_year = st.checkbox("Top（year）", value=True)
    include_new = st.checkbox("New", value=False)

    per_feed_limit = st.slider(
        "每個 feed 抓取數量",
        min_value=10,
        max_value=50,
        value=25,
        step=5,
    )

    st.divider()
    if st.button("♻️ 清除快取與狀態", width="stretch"):
        clear_all_state()
        st.success("已清除快取與狀態，請重新操作。")

col1, col2, col3 = st.columns(3)
col1.metric("資料來源", "Reddit JSON")
col2.metric("分析社群數", len(selected_subreddits))
col3.metric("年度篩選", "2026" if only_2026 else "不限")

with st.expander("資料來源與限制說明", expanded=False):
    st.write("• 本工具使用 Reddit 公開 JSON feed，不再依賴第三方鏡像或搜尋頁爬取。")
    st.write("• 排行為討論熱度估計，不代表實際銷售排行。")
    st.write("• 2026 篩選採關鍵字啟發式規則，適合做趨勢觀察與作品展示。")
    st.write("• 若結果過少，可關閉「只分析 2026 熱門內容」後再試。")

run_clicked = st.button("🔍 開始分析", type="primary", width="stretch")

if run_clicked:
    if not selected_subreddits:
        st.error("請至少選擇一個 subreddit。")
    elif not (include_hot or include_top_year or include_new):
        st.error("請至少選擇一種 feed。")
    elif check_rate_limit():
        with st.spinner("正在抓取並分析 Reddit 公開資料，請稍候..."):
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
    result = st.session_state.get("result", {})
    products = result.get("products", [])
    raw_post_count = result.get("raw_post_count", 0)
    filtered_post_count = result.get("filtered_post_count", 0)
    method_counts = result.get("method_counts", {})
    progress_logs = result.get("progress_logs", [])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("抓取原始貼文", raw_post_count)
    m2.metric("有效分析貼文", filtered_post_count)
    m3.metric("熱門品牌/關鍵字", len(products))
    m4.metric("已選社群", len(selected_subreddits))

    if method_counts:
        st.caption("Feed 統計：" + " / ".join(f"{k}: {v}" for k, v in method_counts.items()))
    else:
        st.caption("Feed 統計：目前無資料")

    with st.expander("抓取紀錄", expanded=False):
        if progress_logs:
            for line in progress_logs:
                st.write(sanitize_text(line, 300))
        else:
            st.write("目前沒有抓取紀錄。")

    st.subheader("🏆 排行榜")

    if not products:
        st.warning("沒有符合條件的結果。你可以關閉 2026 篩選，或改成彩妝 + 保養後再試。")
    else:
        for idx, item in enumerate(products, start=1):
            brand = sanitize_text(item.get("brand", ""), 100)
            mention_count = item.get("mention_count", 0)
            total_engagement = item.get("total_engagement", 0)
            total_score = item.get("total_score", 0)
            total_comments = item.get("total_comments", 0)
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

            if is_safe_url(reddit_search_url):
                st.link_button(
                    label=f"搜尋 {brand}",
                    url=reddit_search_url,
                    width="content",
                )

            top_posts = item.get("top_posts", [])
            with st.expander("查看代表貼文", expanded=False):
                if not top_posts:
                    st.write("無代表貼文")
                else:
                    for p in top_posts:
                        title = sanitize_text(p.get("title", ""), 140)
                        subreddit = sanitize_text(p.get("subreddit", ""), 40)
                        source = sanitize_text(p.get("source", ""), 40)
                        score = p.get("score", 0)
                        comments = p.get("comments", 0)
                        link = p.get("link", "")

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

        st.subheader("📊 原始統計表")
        df = pd.DataFrame([
            {
                "排名": i + 1,
                "品牌/關鍵字": sanitize_text(p.get("brand", ""), 100),
                "提及次數": p.get("mention_count", 0),
                "互動分": p.get("total_engagement", 0),
                "貼文分數": p.get("total_score", 0),
                "留言數": p.get("total_comments", 0),
                "出現版面": ", ".join(p.get("subreddits", [])),
            }
            for i, p in enumerate(products)
        ])
        st.dataframe(df, width="stretch", hide_index=True)
else:
    st.info("請先在左側設定分析條件，再點擊「開始分析」。")
