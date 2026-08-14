"""
Noon Egypt tracker - sales leaderboard dashboard.
The primary metric is 'sold_recently' (units sold in the last period, as shown on Noon).
"""
import sqlite3
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).parent / "noon_data.db"

st.set_page_config(page_title="Noon EG Sales Tracker", page_icon="🔥", layout="wide")


@st.cache_data(ttl=600)
def load_data():
    if not DB_PATH.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM snapshots", conn, parse_dates=["snapshot_date"])
    conn.close()
    return df


df = load_data()

if df.empty:
    st.warning("🚧 No data yet. Run `python scraper.py` first.")
    st.stop()


latest_date = df["snapshot_date"].max()
prev_dates = sorted(df["snapshot_date"].unique())
prev_date = prev_dates[-2] if len(prev_dates) >= 2 else None

c1, c2, c3, c4 = st.columns(4)
c1.metric("📅 Latest", latest_date.strftime("%d %b %Y"))
c2.metric("📊 Days tracked", df["snapshot_date"].nunique())
c3.metric("🏷️ Products", df["product_id"].nunique())
c4.metric("📦 Units sold today",
          f"{int(df[df['snapshot_date'] == latest_date]['sold_recently'].fillna(0).sum()):,}")

st.markdown("---")

st.sidebar.title("🔥 Filters")
categories = sorted(df["category"].unique())
selected_cats = st.sidebar.multiselect("Category", categories, default=categories)
df = df[df["category"].isin(selected_cats)]

min_sold = st.sidebar.slider("Min. units sold", 0, 3000, 0, step=50,
                             help="Hide products selling less than this")

view = st.sidebar.radio(
    "View",
    ["🏆 Sales Leaderboard", "📈 Biggest Movers", "🆕 New Best Sellers",
     "💰 Price Changes", "🔍 Search Product", "📊 Raw Data"],
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Noon shows sold counts as ranges ('210+'). "
    "The dashboard captures the lower bound. Use as **trend signals**, not exact totals."
)


def compare_dates(metric):
    if prev_date is None:
        return pd.DataFrame()
    prev = df[df["snapshot_date"] == prev_date][
        ["product_id", "title", "category", metric, "price_egp", "url", "best_seller"]
    ].rename(columns={metric: f"{metric}_prev", "price_egp": "price_prev"})
    curr = df[df["snapshot_date"] == latest_date][
        ["product_id", "title", "category", metric, "price_egp", "url", "best_seller"]
    ].rename(columns={metric: f"{metric}_curr", "price_egp": "price_curr"})
    m = pd.merge(curr, prev[["product_id", f"{metric}_prev", "price_prev"]],
                 on="product_id", how="left")
    m["change"] = m[f"{metric}_curr"] - m[f"{metric}_prev"]
    return m


if view == "🏆 Sales Leaderboard":
    st.title("🏆 Sales Leaderboard")
    st.caption(f"Every product ranked by 🔥 units sold recently — {latest_date.strftime('%d %b %Y')}")

    board = df[df["snapshot_date"] == latest_date].copy()
    board = board[board["sold_recently"].fillna(0) >= min_sold]
    board = board.sort_values("sold_recently", ascending=False, na_position="last")

    if prev_date is not None:
        prev_map = df[df["snapshot_date"] == prev_date].set_index("product_id")["sold_recently"]
        board["Δ vs prev"] = board["sold_recently"] - board["product_id"].map(prev_map)

    display_cols = ["category", "title", "sold_recently"]
    if "Δ vs prev" in board.columns:
        display_cols.append("Δ vs prev")
    display_cols += ["price_egp", "rating", "reviews_count", "best_seller", "url"]

    max_sold = int(board["sold_recently"].max() or 1000)
    st.dataframe(
        board[display_cols].rename(columns={
            "category": "Category", "title": "Product",
            "sold_recently": "🔥 Sold", "price_egp": "EGP",
            "rating": "★", "reviews_count": "Reviews",
            "best_seller": "BS", "url": "Link",
        }),
        width="stretch",
        column_config={
            "Link": st.column_config.LinkColumn("Link", display_text="→"),
            "🔥 Sold": st.column_config.ProgressColumn(
                "🔥 Sold", format="%d", min_value=0, max_value=max_sold),
        },
        hide_index=True, height=700,
    )

elif view == "📈 Biggest Movers":
    st.title("📈 Biggest Sales Movers")
    if prev_date is None:
        st.info("⏳ Need 2+ days of data. Come back tomorrow.")
    else:
        st.caption(f"{prev_date.strftime('%d %b')} → {latest_date.strftime('%d %b')}")
        moves = compare_dates("sold_recently")
        moves = moves[moves["change"].notna() & (moves["change"] != 0)]
        moves = moves[moves["sold_recently_curr"].fillna(0) >= min_sold]

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🚀 Biggest Jumps")
            ups = moves.sort_values("change", ascending=False).head(20)
            st.dataframe(
                ups[["title", "category", "sold_recently_prev", "sold_recently_curr",
                     "change", "price_curr", "url"]].rename(columns={
                    "title": "Product", "category": "Cat",
                    "sold_recently_prev": "Was", "sold_recently_curr": "Now",
                    "change": "+", "price_curr": "EGP", "url": "→",
                }),
                width="stretch",
                column_config={"→": st.column_config.LinkColumn("Link", display_text="→")},
                hide_index=True, height=600,
            )
        with col2:
            st.subheader("📉 Biggest Drops")
            downs = moves.sort_values("change").head(20)
            st.dataframe(
                downs[["title", "category", "sold_recently_prev", "sold_recently_curr",
                       "change", "price_curr", "url"]].rename(columns={
                    "title": "Product", "category": "Cat",
                    "sold_recently_prev": "Was", "sold_recently_curr": "Now",
                    "change": "−", "price_curr": "EGP", "url": "→",
                }),
                width="stretch",
                column_config={"→": st.column_config.LinkColumn("Link", display_text="→")},
                hide_index=True, height=600,
            )

elif view == "🆕 New Best Sellers":
    st.title("🆕 New Best Sellers & Products")
    if prev_date is None:
        st.info("⏳ Need 2+ days of data.")
    else:
        curr = df[df["snapshot_date"] == latest_date]
        prev = df[df["snapshot_date"] == prev_date]
        prev_ids = set(prev["product_id"])
        prev_bs = set(prev[prev["best_seller"] == 1]["product_id"])

        newly_bs = curr[(curr["best_seller"] == 1) & (~curr["product_id"].isin(prev_bs))]
        newly_bs = newly_bs.sort_values("sold_recently", ascending=False, na_position="last")

        st.subheader(f"⭐ Newly badged Best Seller ({len(newly_bs)})")
        if len(newly_bs) > 0:
            st.dataframe(
                newly_bs[["category", "title", "sold_recently", "price_egp",
                          "rating", "url"]].rename(columns={
                    "category": "Category", "title": "Product",
                    "sold_recently": "🔥 Sold", "price_egp": "EGP",
                    "rating": "★", "url": "→",
                }),
                width="stretch",
                column_config={"→": st.column_config.LinkColumn("Link", display_text="→")},
                hide_index=True,
            )
        else:
            st.caption("None today.")

        brand_new = curr[~curr["product_id"].isin(prev_ids)]
        brand_new = brand_new[brand_new["sold_recently"].fillna(0) >= min_sold]
        brand_new = brand_new.sort_values("sold_recently", ascending=False, na_position="last")

        st.subheader(f"🆕 New in listings ({len(brand_new)})")
        if len(brand_new) > 0:
            st.dataframe(
                brand_new[["category", "title", "sold_recently", "price_egp",
                           "rating", "best_seller", "url"]].rename(columns={
                    "category": "Category", "title": "Product",
                    "sold_recently": "🔥 Sold", "price_egp": "EGP",
                    "rating": "★", "best_seller": "BS", "url": "→",
                }),
                width="stretch",
                column_config={"→": st.column_config.LinkColumn("Link", display_text="→")},
                hide_index=True,
            )

elif view == "💰 Price Changes":
    st.title("💰 Price Changes (selling products only)")
    if prev_date is None:
        st.info("⏳ Need 2+ days of data.")
    else:
        moves = compare_dates("price_egp")
        moves = moves[moves["price_prev"].notna() & moves["price_curr"].notna()]
        moves["Δ%"] = ((moves["price_curr"] - moves["price_prev"]) / moves["price_prev"]) * 100
        moves = moves[moves["Δ%"].abs() >= 1]
        latest_sold = df[df["snapshot_date"] == latest_date].set_index("product_id")["sold_recently"]
        moves["sold"] = moves["product_id"].map(latest_sold)
        moves = moves[moves["sold"].fillna(0) >= min_sold]

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("⬇️ Price Drops")
            drops = moves[moves["Δ%"] < 0].sort_values("Δ%").head(20)
            st.dataframe(
                drops[["title", "category", "price_prev", "price_curr", "Δ%", "sold", "url"]].rename(columns={
                    "title": "Product", "category": "Cat",
                    "price_prev": "Was", "price_curr": "Now",
                    "sold": "🔥", "url": "→",
                }),
                width="stretch",
                column_config={"→": st.column_config.LinkColumn("Link", display_text="→")},
                hide_index=True, height=600,
            )
        with col2:
            st.subheader("⬆️ Price Increases")
            ups = moves[moves["Δ%"] > 0].sort_values("Δ%", ascending=False).head(20)
            st.dataframe(
                ups[["title", "category", "price_prev", "price_curr", "Δ%", "sold", "url"]].rename(columns={
                    "title": "Product", "category": "Cat",
                    "price_prev": "Was", "price_curr": "Now",
                    "sold": "🔥", "url": "→",
                }),
                width="stretch",
                column_config={"→": st.column_config.LinkColumn("Link", display_text="→")},
                hide_index=True, height=600,
            )

elif view == "🔍 Search Product":
    st.title("🔍 Search & History")
    q = st.text_input("Search by title keyword", placeholder="anker, ugreen, 65w, ...")
    if q:
        latest = df[df["snapshot_date"] == latest_date]
        hits = latest[latest["title"].str.contains(q, case=False, na=False)]
        hits = hits.sort_values("sold_recently", ascending=False, na_position="last")
        st.caption(f"{len(hits)} matches on {latest_date.date()}")
        st.dataframe(
            hits[["category", "title", "sold_recently", "price_egp",
                  "rating", "best_seller", "url"]].rename(columns={
                "category": "Cat", "title": "Product",
                "sold_recently": "🔥 Sold", "price_egp": "EGP",
                "rating": "★", "best_seller": "BS", "url": "→",
            }),
            width="stretch",
            column_config={"→": st.column_config.LinkColumn("Link", display_text="→")},
            hide_index=True,
        )
        if not hits.empty:
            top_pid = hits.iloc[0]["product_id"]
            hist = df[df["product_id"] == top_pid].sort_values("snapshot_date")
            if len(hist) > 1:
                st.subheader(f"History — {hits.iloc[0]['title'][:80]}")
                a, b = st.columns(2)
                with a:
                    st.line_chart(hist.set_index("snapshot_date")["sold_recently"], height=250)
                    st.caption("🔥 Units sold recently")
                with b:
                    st.line_chart(hist.set_index("snapshot_date")["price_egp"], height=250)
                    st.caption("Price (EGP)")

elif view == "📊 Raw Data":
    st.title("📊 Raw Data")
    st.dataframe(df.sort_values(["snapshot_date", "sold_recently"],
                                ascending=[False, False]),
                 width="stretch", hide_index=True)
    st.download_button("⬇️ Download CSV",
                       df.to_csv(index=False).encode("utf-8"),
                       f"noon_snapshots_{dt.date.today()}.csv",
                       "text/csv")
