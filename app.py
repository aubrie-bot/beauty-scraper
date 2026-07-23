import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import random
import time

HEADERS_LIST = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
]


def scrape_sephora_bestsellers():
    url = "https://www.sephora.com/bestsellers"
    headers = random.choice(HEADERS_LIST)
    products = []
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for card in soup.select('[data-comp="ProductGrid"] [data-comp="Product"]'):
            name_tag = card.select_one('[data-at="sku_item_name"]')
            brand_tag = card.select_one('[data-at="brand_name"]')
            price_tag = card.select_one('[data-at="sku_item_price_list"] span')
            rating_tag = card.select_one('[data-at="rating_count"]')
            img_tag = card.select_one("img")
            link_tag = card.select_one("a[href]")
            if name_tag:
                products.append({
                    "name": name_tag.get_text(strip=True),
                    "brand": brand_tag.get_text(strip=True) if brand_tag else "",
                    "price": price_tag.get_text(strip=True) if price_tag else "",
                    "rating": rating_tag.get_text(strip=True) if rating_tag else "",
                    "image": img_tag["src"] if img_tag and img_tag.get("src") else "",
                    "url": "https://www.sephora.com" + link_tag["href"] if link_tag else "",
                    "source": "Sephora",
                })
    except Exception as e:
        st.warning(f"Sephora 爬取失敗: {e}")
    return products


def scrape_ulta_bestsellers():
    url = "https://www.ulta.com/shop/skin-care/bestsellers"
    headers = random.choice(HEADERS_LIST)
    products = []
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for card in soup.select(".ProductCard"):
            name_tag = card.select_one(".ProductCard__product")
            brand_tag = card.select_one(".ProductCard__brand")
            price_tag = card.select_one(".ProductCard__price")
            img_tag = card.select_one("img")
            link_tag = card.select_one("a[href]")
            if name_tag:
                products.append({
                    "name": name_tag.get_text(strip=True),
                    "brand": brand_tag.get_text(strip=True) if brand_tag else "",
                    "price": price_tag.get_text(strip=True) if price_tag else "",
                    "rating": "",
                    "image": img_tag["src"] if img_tag and img_tag.get("src") else "",
                    "url": "https://www.ulta.com" + link_tag["href"] if link_tag else "",
                    "source": "Ulta",
                })
    except Exception as e:
        st.warning(f"Ulta 爬取失敗: {e}")
    return products


FALLBACK_PRODUCTS = [
    {"name": "Rare Beauty Soft Pinch Liquid Blush", "brand": "Rare Beauty", "price": "$23.00", "rating": "4.7 / 5", "image": "", "url": "https://www.sephora.com/product/soft-pinch-liquid-blush-P461711", "source": "Sephora (Popular)"},
    {"name": "NARS Blush", "brand": "NARS", "price": "$38.00", "rating": "4.8 / 5", "image": "", "url": "https://www.sephora.com/product/nars-blush-P159706", "source": "Sephora (Popular)"},
    {"name": "Fenty Beauty Pro Filt'r Soft Matte Foundation", "brand": "Fenty Beauty", "price": "$40.00", "rating": "4.6 / 5", "image": "", "url": "https://www.sephora.com/product/pro-filtr-soft-matte-longwear-foundation-P421498", "source": "Sephora (Popular)"},
    {"name": "Charlotte Tilbury Pillow Talk Lipstick", "brand": "Charlotte Tilbury", "price": "$34.00", "rating": "4.7 / 5", "image": "", "url": "https://www.sephora.com/product/matte-revolution-lipstick-P432312", "source": "Sephora (Popular)"},
    {"name": "Drunk Elephant Protini Polypeptide Cream", "brand": "Drunk Elephant", "price": "$68.00", "rating": "4.5 / 5", "image": "", "url": "https://www.sephora.com/product/protini-polypeptide-cream-P432564", "source": "Sephora (Popular)"},
    {"name": "Maybelline Lash Sensational Sky High Mascara", "brand": "Maybelline", "price": "$11.99", "rating": "4.6 / 5", "image": "", "url": "https://www.ulta.com/p/lash-sensational-sky-high-mascara-xlsImpprod15611231", "source": "Ulta (Popular)"},
    {"name": "The Ordinary Niacinamide 10% + Zinc 1%", "brand": "The Ordinary", "price": "$6.50", "rating": "4.5 / 5", "image": "", "url": "https://www.sephora.com/product/the-ordinary-niacinamide-10-zinc-1-P431229", "source": "Sephora (Popular)"},
    {"name": "CeraVe Moisturizing Cream", "brand": "CeraVe", "price": "$18.99", "rating": "4.7 / 5", "image": "", "url": "https://www.ulta.com/p/moisturizing-cream-xlsImpprod14121005", "source": "Ulta (Popular)"},
    {"name": "Tatcha Dewy Skin Cream", "brand": "Tatcha", "price": "$69.00", "rating": "4.6 / 5", "image": "", "url": "https://www.sephora.com/product/tatcha-the-dewy-skin-cream-P459611", "source": "Sephora (Popular)"},
    {"name": "Laura Mercier Translucent Loose Setting Powder", "brand": "Laura Mercier", "price": "$43.00", "rating": "4.7 / 5", "image": "", "url": "https://www.sephora.com/product/translucent-loose-setting-powder-P128006", "source": "Sephora (Popular)"},
    {"name": "Mario Badescu Facial Spray with Aloe Herbs & Rosewater", "brand": "Mario Badescu", "price": "$7.00", "rating": "4.5 / 5", "image": "", "url": "https://www.ulta.com/p/facial-spray-with-aloe-herbs-rosewater-pimprod2006261", "source": "Ulta (Popular)"},
    {"name": "Too Faced Better Than Sex Mascara", "brand": "Too Faced", "price": "$29.00", "rating": "4.5 / 5", "image": "", "url": "https://www.sephora.com/product/too-faced-better-than-sex-volumizing-mascara-P377327", "source": "Sephora (Popular)"},
]


st.set_page_config(page_title="北美美妝熱銷排行", page_icon="💄", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #fce4ec, #f3e5f5);
        border-radius: 12px; padding: 15px 20px;
    }
    [data-testid="stMetric"] label { color: #666; }
    [data-testid="stMetric"] [data-testid="stMetricValue"] { color: #e91e63; }
    .product-card {
        background: white; border-radius: 12px; padding: 16px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.08); margin-bottom: 12px;
        border: 1px solid #f0f0f0;
    }
    .product-card h4 { margin: 0 0 4px 0; font-size: 0.95rem; color: #333; }
    .product-card .brand { font-size: 0.8rem; color: #999; text-transform: uppercase; letter-spacing: 0.5px; }
    .product-card .price { font-size: 1.2rem; font-weight: 700; color: #e91e63; }
    .product-card .rating { color: #ffc107; font-size: 0.85rem; }
    .source-badge {
        display: inline-block; padding: 2px 10px; border-radius: 20px;
        font-size: 0.7rem; font-weight: 600; color: white; margin-bottom: 6px;
    }
    .source-sephora { background: #000; }
    .source-ulta { background: #e91e63; }
</style>
""", unsafe_allow_html=True)

st.title("北美美妝熱銷排行")
st.caption("即時爬取 Sephora / Ulta 最暢銷美妝產品")

if st.button("🔍 開始爬取", type="primary", use_container_width=True):
    with st.spinner("正在爬取資料中，請稍候..."):
        products = []
        with st.status("爬取中...", expanded=True) as status:
            st.write("正在爬取 Sephora...")
            sephora = scrape_sephora_bestsellers()
            products.extend(sephora)
            time.sleep(1)
            st.write("正在爬取 Ulta...")
            ulta = scrape_ulta_bestsellers()
            products.extend(ulta)
            if not products:
                st.write("即時爬取失敗，使用推薦清單")
                products = FALLBACK_PRODUCTS
            status.update(label="爬取完成！", state="complete")

    st.session_state["products"] = products

if "products" in st.session_state:
    products = st.session_state["products"]
    df = pd.DataFrame(products)

    sephora_count = len([p for p in products if "Sephora" in p["source"]])
    ulta_count = len([p for p in products if "Ulta" in p["source"]])

    c1, c2, c3 = st.columns(3)
    c1.metric("總產品數", len(products))
    c2.metric("Sephora", sephora_count)
    c3.metric("Ulta", ulta_count)

    st.divider()

    source_filter = st.selectbox("篩選來源", ["全部", "Sephora", "Ulta"])
    if source_filter != "全部":
        products = [p for p in products if source_filter in p["source"]]

    cols = st.columns(3)
    for i, p in enumerate(products):
        with cols[i % 3]:
            source_class = "source-sephora" if "Sephora" in p["source"] else "source-ulta"
            image_html = f'<img src="{p["image"]}" style="max-width:100%;max-height:140px;object-fit:contain;" />' if p["image"] else '<div style="text-align:center;font-size:3rem;padding:30px 0;">💄</div>'
            rating_html = f'<span class="rating">★ {p["rating"]}</span>' if p["rating"] else ""
            st.markdown(f"""
            <div class="product-card">
                {image_html}
                <span class="source-badge {source_class}">{p['source']}</span>
                <div class="brand">{p['brand']}</div>
                <h4>{p['name']}</h4>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span class="price">{p['price']}</span>
                    {rating_html}
                </div>
                <a href="{p['url']}" target="_blank" style="display:block;text-align:center;margin-top:10px;padding:8px;background:linear-gradient(135deg,#fce4ec,#f3e5f5);border-radius:8px;color:#e91e63;text-decoration:none;font-weight:600;font-size:0.85rem;">查看商品</a>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("點擊上方「開始爬取」按鈕獲取最新北美美妝熱銷產品。")
