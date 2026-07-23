import html
import time

import pandas as pd
import streamlit as st

from utils import DEFAULT_BRANDS, parse_brand_input, run_analysis, sanitize_text

st.set_page_config(
    page_title="北美美妝品牌趨勢排行 - Google Trends版",
    page_icon="💄",
    layout="wide",
)

CACHE_TTL_SECONDS = 1800
SESSION_RATE_LIMIT_SECONDS = 90

st.markdown("""
<style>
.hero {
    padding: 1.2rem 1.4rem;
    border-radius: 20px;
    background: linear-gradient(135deg, #ffedf4 0%, #f7ecff 100%);
    border: 1px solid rgba(233, 30, 99, 0.12);
    margin-bottom: 1rem;
}
.card {
    background: #ffffff;
    border: 1px solid #f1d8e4;
    border-radius: 18px;
    padding: 16px 18px;
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
""", unsafe_allow_html=True)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_run_analysis(geo, categories, use_monitor_fallback, use_default_brands, custom_brands):
    return run_analysis(
        geo=geo,
        categories=list(categories),
        use_monitor_fallback=use_monitor_fallback,
        use_default_brands=use_default_brands,
        custom_brands=list(custom_brands),
    )


def check_rate_limit():
    now = time.time()
    last_run = st.session_state.get("last_run_ts", 0)
    if now - last_run < SESSION_RATE_LIMIT_SECONDS:
        remain = int(SESSION_RATE_LIMIT_SECONDS - (now - last_run))
        st.warning(f"請稍候再試，約 {remain} 秒後可重新分析。")
        return False
    st.session_state["last_run_ts"] = now
    return True


def clear_all_state():
    st.cache_data.clear()
    for key in list(st.session_state.keys()):
        del st.session_state[key]


st.markdown("""
<div class="hero">
    <h1>💄 北美美妝品牌趨勢排行</h1>
    <p>只使用實際存在的品牌做排名，搭配 Google Trends Trending Now 與 Sephora / Ulta 常見品牌池做品牌趨勢監測。</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("分析設定")

    geo = st.selectbox("地區", ["US", "CA"], index=0)

    category_label = st.radio(
        "分析範圍",
        ["只看彩妝", "只看保養", "彩妝 + 保養"],
        index=0,
    )

    if category_label == "只看彩妝":
        categories = ["makeup"]
    elif category_label == "只看保養":
        categories = ["skincare"]
    else:
        categories = ["makeup", "skincare"]

    use_default_brands = st.toggle(
        "使用 Sephora / Ulta 常見品牌池",
        value=True,
    )

    custom_brand_text = st.text_area(
        "自訂品牌清單（每行一個，或用逗號分隔）",
        value="Rhode\nSaie\nMerit\nHaus Labs",
        height=180,
    )

    custom_brands = parse_brand_input(custom_brand_text)

    use_monitor_fallback = st.toggle(
        "即時品牌不足時使用品牌監測關鍵字庫",
        value=True,
    )

    st.caption(f"目前自訂品牌數：{len(custom_brands)}")
    st.caption(f"內建參考品牌數：{len(DEFAULT_BRANDS)}")

    if st.button("♻️ 清除快取與狀態", width="stretch"):
        clear_all_state()
        st.success("已清除快取與狀態。")

run_clicked = st.button("🔍 開始分析", type="primary", width="stretch")

if run_clicked and check_rate_limit():
    with st.spinner("正在抓取 Google Trends 並分析品牌..."):
        result = cached_run_analysis(
            geo,
            tuple(categories),
            use_monitor_fallback,
            use_default_brands,
            tuple(custom_brands),
        )
        st.session_state["result"] = result

if "result" in st.session_state:
    result = st.session_state.get("result", {})
    aggregated = result.get("aggregated", [])
    live_terms_count = result.get("live_terms_count", 0)
    matched_live_count = result.get("matched_live_count", 0)
    fallback_used = result.get("fallback_used", False)
    progress_logs = result.get("progress_logs", [])
    raw_live_terms = result.get("raw_live_terms", [])
    brand_pool = result.get("brand_pool", [])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("即時趨勢原始詞數", live_terms_count)
    c2.metric("命中品牌詞數", matched_live_count)
    c3.metric("Fallback", "有啟用" if fallback_used else "未啟用")
    c4.metric("品牌池數量", len(brand_pool))

    with st.expander("目前品牌池", expanded=False):
        if brand_pool:
            st.write(", ".join(brand_pool))
        else:
            st.write("目前沒有品牌。")

    with st.expander("抓取紀錄", expanded=False):
        for line in progress_logs:
            st.write(sanitize_text(line, 300))

    with st.expander("Google Trends 原始熱門詞", expanded=False):
        if raw_live_terms:
            for term in raw_live_terms:
                st.write(f"- {sanitize_text(term, 120)}")
        else:
            st.write("目前沒有抓到原始熱門詞。")

    st.subheader("🏆 品牌排行")

    if not aggregated:
        st.warning("目前沒有抓到可用的品牌結果。你可以增加自訂品牌、改成彩妝 + 保養，或開啟 fallback。")

    for idx, item in enumerate(aggregated, start=1):
        brand = sanitize_text(item.get("brand", ""), 100)
        mention_count = item.get("mention_count", 0)
        total_score = item.get("total_score", 0)
        sources = ", ".join(item.get("sources", []))

        st.markdown(f"""
        <div class="card">
            <div class="rank">#{idx} {html.escape(brand)}</div>
            <div class="subtle">
                命中次數：{mention_count} ｜ 趨勢分數：{total_score}
            </div>
            <div class="tiny">來源：{html.escape(sources)}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("查看代表趨勢詞", expanded=False):
            top_items = item.get("top_items", [])
            if not top_items:
                st.write("無代表趨勢詞")
            else:
                for t in top_items:
                    keyword = sanitize_text(t.get("keyword", ""), 140)
                    source = sanitize_text(t.get("source", ""), 40)
                    trend_score = t.get("trend_score", 0)
                    st.write(f"**{keyword}**  \n來源：{source} ｜ 分數：{trend_score}")

    st.subheader("📊 原始統計表")
    df = pd.DataFrame([
        {
            "排名": i + 1,
            "品牌": sanitize_text(p.get("brand", ""), 100),
            "命中次數": p.get("mention_count", 0),
            "趨勢分數": p.get("total_score", 0),
            "來源": ", ".join(p.get("sources", [])),
        }
        for i, p in enumerate(aggregated)
    ])
    st.dataframe(df, width="stretch", hide_index=True)
else:
    st.info("請先設定條件，再按「開始分析」。")
