import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import date, timedelta

import data_processor as dp
import ai_analyzer as ai

st.set_page_config(
    page_title="AsiaYo 業績儀表板",
    page_icon="🌏",
    layout="wide"
)


st.title("🌏 AsiaYo 業績儀表板")

# ── 載入資料 ──────────────────────────────────────────────
with st.spinner("載入資料中..."):
    try:
        df_all = dp.load_data()
    except Exception as e:
        st.error(f"資料載入失敗：{e}")
        st.stop()

# ── 側邊欄篩選 ────────────────────────────────────────────
with st.sidebar:
    affiliate_options = dp.get_affiliate_options(df_all)
    selected_affiliates = st.multiselect(
        "行銷管道（Affiliate ID）",
        options=affiliate_options,
        default=None,
        placeholder="不選 = 顯示全部"
    )

    st.divider()
    page = st.selectbox("頁面導覽", [
        "📊 總覽", "🚢 郵輪", "🌍 GIT",
        "🏠 住宿 & 露營", "🏃 SEB", "🚄 高鐵",
        "📱 eSIM", "🗺️ Day Tour", "📣 行銷管道", "💡 自動洞察"
    ])

    st.divider()
    st.header("篩選條件")

    min_date = df_all["order_date"].min().date()
    max_date = df_all["order_date"].max().date()

    # 週從星期天開始
    today = date.today()
    days_since_sunday = (today.weekday() + 1) % 7
    this_week_sun = today - timedelta(days=days_since_sunday)
    last_week_sun = this_week_sun - timedelta(days=7)

    preset = st.selectbox("快速選擇日期", [
        "自訂", "本週", "前一週", "近7天", "近30天", "近90天"
    ], index=1)

    if preset == "本週":
        default_start = this_week_sun
        default_end = min(this_week_sun + timedelta(days=6), max_date)
    elif preset == "前一週":
        default_start = last_week_sun
        default_end = this_week_sun - timedelta(days=1)
    elif preset == "近7天":
        default_start = max_date - timedelta(days=6)
        default_end = max_date
    elif preset == "近30天":
        default_start = max_date - timedelta(days=29)
        default_end = max_date
    elif preset == "近90天":
        default_start = max_date - timedelta(days=89)
        default_end = max_date
    else:
        default_start = max(min_date, max_date - timedelta(days=90))
        default_end = max_date

    start_date = st.date_input("下單日期（起）", value=default_start, min_value=min_date, max_value=max_date)
    end_date = st.date_input("下單日期（迄）", value=default_end, min_value=min_date, max_value=max_date)

    _n = (end_date - start_date).days + 1
    _pe = start_date - timedelta(days=1)
    _ps = _pe - timedelta(days=_n - 1)
    st.caption(f"比較前期：{_ps.strftime('%m/%d')} ～ {_pe.strftime('%m/%d')}（共 {_n} 天）")

    all_statuses = sorted(df_all["booking_status"].dropna().unique().tolist())
    selected_statuses = st.multiselect("訂單狀態", options=all_statuses, default=all_statuses)

    st.divider()
    trend_freq = st.radio("趨勢圖週期", ["D", "W", "M"],
                          format_func=lambda x: {"D": "天", "W": "週", "M": "月"}[x],
                          horizontal=True)

df = dp.filter_df(
    df_all, start_date, end_date, None, selected_statuses,
    affiliate_ids=selected_affiliates if selected_affiliates else None
)

if df.empty:
    st.warning("目前篩選條件下無資料，請調整篩選範圍。")
    st.stop()

# ── 前期資料（自動往前推相同天數）────────────────────────────
_period_days = (end_date - start_date).days + 1
_prev_end    = start_date - timedelta(days=1)
_prev_start  = _prev_end  - timedelta(days=_period_days - 1)
df_prev = dp.filter_df(
    df_all, _prev_start, _prev_end, None, selected_statuses,
    affiliate_ids=selected_affiliates if selected_affiliates else None
)

# ── KPI helper ───────────────────────────────────────────
def kpi(col, label: str, current: float, prev: float, fmt: str = "money"):
    """st.metric with delta vs previous period."""
    if fmt == "money":
        val_str  = f"NT${current:,.0f}"
        prev_str = f"NT${prev:,.0f}"
    elif fmt == "count":
        val_str  = f"{int(current):,}"
        prev_str = f"{int(prev):,}"
    else:
        val_str  = f"{current:.1f}"
        prev_str = f"{prev:.1f}"

    if prev > 0:
        pct = (current - prev) / prev * 100
        delta_str = f"{pct:+.1f}%（前期 {prev_str}）"
    else:
        delta_str = f"前期 {prev_str}"

    col.metric(label, val_str, delta=delta_str)


# ── 圖表 helper ───────────────────────────────────────────
_MAX_LABEL = 22


def hbar(df: pd.DataFrame, x: str, y: str, title: str, **kwargs) -> "go.Figure":
    """水平長條圖。標籤超過 _MAX_LABEL 字時截斷並加 …，完整名稱放 hover。"""
    df = df.copy()
    full_col = f"_{y}_full"
    df[full_col] = df[y].astype(str)
    df[y] = df[full_col].apply(
        lambda s: s[:_MAX_LABEL] + "…" if len(s) > _MAX_LABEL else s
    )
    n = len(df)
    fig = px.bar(df, x=x, y=y, orientation="h", title=title,
                 labels={y: ""}, hover_data={full_col: True, y: False},
                 **kwargs)
    fig.update_traces(hovertemplate="%{customdata[0]}<br>%{x:,.0f}<extra></extra>")
    fig.update_yaxes(autorange="reversed", automargin=False, tickfont_size=12)
    fig.update_layout(
        height=max(360, n * 34 + 80),
        margin=dict(l=220, r=20, t=40, b=40),
    )
    return fig


def render_simple_tab(sub_df: pd.DataFrame, label: str,
                      has_checkin: bool = True,
                      type_col=None,
                      prev_df: pd.DataFrame = None):
    """商品排行 + 出發月份（可選）的通用頁籤內容。"""
    if sub_df.empty:
        st.info(f"此篩選範圍內無 {label} 訂單。")
        return

    if prev_df is None:
        prev_df = pd.DataFrame(columns=sub_df.columns)

    c1, c2, c3 = st.columns(3)
    kpi(c1, f"{label} 營收",   sub_df["twd_amount"].sum(), prev_df["twd_amount"].sum())
    kpi(c2, f"{label} 訂單數", len(sub_df), len(prev_df), fmt="count")
    avg = sub_df["twd_amount"].mean()
    c3.metric("平均客單價", f"NT${avg:,.0f}")

    col1, col2 = st.columns(2)

    with col1:
        # 若有 type_col（如高鐵的 bnb_type），先用它分群
        if type_col and type_col in sub_df.columns:
            type_rev = (sub_df.groupby(type_col)
                              .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
                              .reset_index())
            fig_t = px.pie(type_rev, names=type_col, values="營收",
                           title=f"{label} 類型佔比", hole=0.4)
            st.plotly_chart(fig_t, use_container_width=True)

        prod_df = (sub_df.groupby("bnb_name")
                         .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
                         .sort_values("營收", ascending=False)
                         .reset_index()
                         .head(20))
        fig_p = hbar(prod_df, x="營收", y="bnb_name", title=f"{label} 商品排行（前20）")
        st.plotly_chart(fig_p, use_container_width=True)

    with col2:
        if has_checkin:
            sub_df = sub_df.copy()
            sub_df["check_in_month"] = sub_df["check_in"].dt.to_period("M").astype(str)
            ci = (sub_df.groupby("check_in_month")
                        .agg(訂單數=("order_id", "count"))
                        .reset_index())
            fig_c = px.bar(ci, x="check_in_month", y="訂單數",
                           title=f"{label} 出發月份分佈",
                           labels={"check_in_month": "出發月份"})
            st.plotly_chart(fig_c, use_container_width=True)
        else:
            # eSIM 等沒有出發日期的，改顯示裝置平台
            plat = (sub_df.groupby("platform")["order_id"].count()
                          .reset_index(name="訂單數"))
            fig_plat = px.pie(plat, names="platform", values="訂單數",
                              title=f"{label} 下單裝置", hole=0.4)
            st.plotly_chart(fig_plat, use_container_width=True)


st.subheader(page)


# ════════════════════════════════════════════════════════
# 總覽
# ════════════════════════════════════════════════════════
if page == "📊 總覽":
    total_rev = df["twd_amount"].sum()
    total_orders = len(df)
    avg_order = total_rev / total_orders if total_orders else 0

    prev_rev    = df_prev["twd_amount"].sum()
    prev_orders = len(df_prev)
    prev_avg    = prev_rev / prev_orders if prev_orders else 0
    c1, c2, c3 = st.columns(3)
    kpi(c1, "總營收",    total_rev,    prev_rev)
    kpi(c2, "總訂單數",  total_orders, prev_orders, fmt="count")
    kpi(c3, "平均客單價", avg_order,    prev_avg)

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        pl_df = dp.revenue_by_product_line(df)
        fig = px.bar(pl_df, x="product_line", y="營收", color="product_line",
                     title="各產品線營收", text_auto=".2s",
                     labels={"product_line": "產品線"})
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        pl_df["佔比"] = (pl_df["營收"] / pl_df["營收"].sum() * 100).round(1).astype(str) + "%"
        fig2 = px.treemap(
            pl_df, path=["product_line"], values="營收",
            title="各產品線營收佔比",
            custom_data=["佔比", "訂單數"]
        )
        fig2.update_traces(
            texttemplate="<b>%{label}</b><br>%{customdata[0]}<br>%{value:,.0f}",
            textfont_size=13
        )
        st.plotly_chart(fig2, use_container_width=True)

    trend = dp.revenue_trend(df, freq=trend_freq)
    fig3 = px.line(trend, x="日期", y="營收", title="營收趨勢", markers=True)
    st.plotly_chart(fig3, use_container_width=True)

    st.subheader("各產品線明細")
    st.dataframe(pl_df, use_container_width=True)

# ════════════════════════════════════════════════════════
# 郵輪
# ════════════════════════════════════════════════════════
elif page == "🚢 郵輪":
    cruise_df = df[df["product_line"] == "Cruise"]
    if cruise_df.empty:
        st.info("此篩選範圍內無郵輪訂單。")
    else:
        # 整體 KPI
        cruise_prev = df_prev[df_prev["product_line"] == "Cruise"]
        homeport_df = cruise_df[cruise_df["cruise_type"] == "母港出發"]
        fly_df      = cruise_df[cruise_df["cruise_type"] == "飛航郵輪"]
        c1, c2, c3, c4 = st.columns(4)
        kpi(c1, "郵輪總營收", cruise_df["twd_amount"].sum(), cruise_prev["twd_amount"].sum())
        kpi(c2, "總訂單數",   len(cruise_df), len(cruise_prev), fmt="count")
        kpi(c3, "母港出發",   len(homeport_df),
            len(cruise_prev[cruise_prev["cruise_type"] == "母港出發"]), fmt="count")
        kpi(c4, "飛航郵輪",   len(fly_df),
            len(cruise_prev[cruise_prev["cruise_type"] == "飛航郵輪"]), fmt="count")

        st.divider()
        ctab_home, ctab_fly = st.tabs(["🛳️ 母港出發", "✈️ 飛航郵輪"])

        # ── 母港出發 ──────────────────────────────────────
        with ctab_home:
            if homeport_df.empty:
                st.info("此篩選範圍內無母港出發訂單。")
            else:
                hp = cruise_prev[cruise_prev["cruise_type"] == "母港出發"]
                h1, h2, h3 = st.columns(3)
                kpi(h1, "營收",   homeport_df["twd_amount"].sum(), hp["twd_amount"].sum())
                kpi(h2, "訂單數", len(homeport_df), len(hp), fmt="count")
                h3.metric("平均晚數", f"{homeport_df['nights'].mean():.1f} 晚")

                col1, col2 = st.columns(2)
                with col1:
                    brand_df = dp.cruise_by_brand(df)
                    home_brand = brand_df[brand_df["cruise_type"] == "母港出發"]
                    fig = px.bar(home_brand, x="品牌", y="營收", color="品牌",
                                 title="母港郵輪品牌營收", text_auto=".2s")
                    fig.update_layout(showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)

                with col2:
                    h_nights = (homeport_df.groupby("nights")
                                           .agg(訂單數=("order_id", "count"))
                                           .reset_index()
                                           .sort_values("nights"))
                    fig2 = px.bar(h_nights, x="nights", y="訂單數",
                                  title="訂購晚數分佈", labels={"nights": "晚數"})
                    st.plotly_chart(fig2, use_container_width=True)

                homeport_ci = homeport_df.copy()
                homeport_ci["check_in_month"] = homeport_ci["check_in"].dt.to_period("M").astype(str)
                homeport_ci["品牌"] = homeport_ci["bnb_name"].apply(dp._cruise_brand)
                ci_home = (homeport_ci.groupby(["check_in_month", "品牌"])
                                      .agg(訂單數=("order_id", "count"))
                                      .reset_index())
                fig3 = px.bar(ci_home, x="check_in_month", y="訂單數", color="品牌",
                              barmode="stack", title="出發月份 × 船",
                              labels={"check_in_month": "出發月份"},
                              color_discrete_map={
                                  "麗星郵輪": "#1f77b4",
                                  "MSC地中海": "#ff7f0e",
                                  "歌詩達":   "#2ca02c",
                              })
                st.plotly_chart(fig3, use_container_width=True)

        # ── 飛航郵輪 ──────────────────────────────────────
        with ctab_fly:
            if fly_df.empty:
                st.info("此篩選範圍內無飛航郵輪訂單。")
            else:
                fp = cruise_prev[cruise_prev["cruise_type"] == "飛航郵輪"]
                f1, f2, f3 = st.columns(3)
                kpi(f1, "營收",   fly_df["twd_amount"].sum(), fp["twd_amount"].sum())
                kpi(f2, "訂單數", len(fly_df), len(fp), fmt="count")
                f3.metric("平均晚數", f"{fly_df['nights'].mean():.1f} 晚")

                col1, col2 = st.columns(2)
                with col1:
                    route_df = (fly_df.groupby("bnb_name")
                                      .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
                                      .sort_values("營收", ascending=False)
                                      .reset_index()
                                      .head(20))
                    fig = hbar(route_df, x="營收", y="bnb_name", title="飛航郵輪商品排行（前20）")
                    st.plotly_chart(fig, use_container_width=True)

                with col2:
                    f_nights = (fly_df.groupby("nights")
                                      .agg(訂單數=("order_id", "count"))
                                      .reset_index()
                                      .sort_values("nights"))
                    fig2 = px.bar(f_nights, x="nights", y="訂單數",
                                  title="訂購晚數分佈", labels={"nights": "晚數"})
                    st.plotly_chart(fig2, use_container_width=True)

                fly_ci = fly_df.copy()
                fly_ci["check_in_month"] = fly_ci["check_in"].dt.to_period("M").astype(str)
                fly_ci["品牌"] = fly_ci["bnb_name"].apply(dp._cruise_brand)
                ci_fly = (fly_ci.groupby(["check_in_month", "品牌"])
                                .agg(訂單數=("order_id", "count"))
                                .reset_index())
                fig3 = px.bar(ci_fly, x="check_in_month", y="訂單數", color="品牌",
                              barmode="stack", title="出發月份 × 船",
                              labels={"check_in_month": "出發月份"})
                st.plotly_chart(fig3, use_container_width=True)

# ════════════════════════════════════════════════════════
# GIT
# ════════════════════════════════════════════════════════
elif page == "🌍 GIT":
    git_df = df[df["product_line"] == "GIT"]
    if git_df.empty:
        st.info("此篩選範圍內無 GIT 訂單。")
    else:
        git_prev = df_prev[df_prev["product_line"] == "GIT"]
        c1, c2 = st.columns(2)
        kpi(c1, "GIT 營收",   git_df["twd_amount"].sum(), git_prev["twd_amount"].sum())
        kpi(c2, "GIT 訂單數", len(git_df), len(git_prev), fmt="count")

        col1, col2 = st.columns(2)
        with col1:
            region_df = dp.git_region_distribution(df)
            fig = hbar(region_df, x="營收", y="bnb_name", title="GIT 商品排行（前20）")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            ci_df = dp.checkin_monthly(df, "GIT")
            fig2 = px.bar(ci_df, x="check_in_month", y="訂單數",
                          title="GIT 出發月份分佈",
                          labels={"check_in_month": "出發月份"})
            st.plotly_chart(fig2, use_container_width=True)

# ════════════════════════════════════════════════════════
# 住宿 & 露營
# ════════════════════════════════════════════════════════
elif page == "🏠 住宿 & 露營":
    sub_tabs = st.tabs(["🇹🇼 台灣住宿", "🇰🇷 韓國住宿", "🇯🇵 日本住宿", "⛺ 露營"])
    configs = [
        ("TW", sub_tabs[0], "台灣"),
        ("KR", sub_tabs[1], "韓國"),
        ("JP", sub_tabs[2], "日本"),
        ("Camping", sub_tabs[3], "露營"),
    ]
    for pl, tab, label in configs:
        with tab:
            sub = df[df["product_line"] == pl]
            if sub.empty:
                st.info(f"此篩選範圍內無{label}訂單。")
                continue
            sub_prev = df_prev[df_prev["product_line"] == pl]
            c1, c2 = st.columns(2)
            kpi(c1, f"{label}營收",   sub["twd_amount"].sum(), sub_prev["twd_amount"].sum())
            kpi(c2, f"{label}訂單數", len(sub), len(sub_prev), fmt="count")

            col1, col2 = st.columns(2)
            with col1:
                city_df = dp.accommodation_region_distribution(df, pl)
                fig = hbar(city_df, x="營收", y="bnb_city", title=f"{label} 城市排行（前20）")
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                ci_df = dp.checkin_monthly(df, pl)
                fig2 = px.bar(ci_df, x="check_in_month", y="訂單數",
                              title=f"{label} 入住月份分佈",
                              labels={"check_in_month": "入住月份"})
                st.plotly_chart(fig2, use_container_width=True)

            if pl == "JP":
                st.subheader("星野飯店訂單")
                hoshino = sub[sub["bnb_name"].str.contains("星野|Hoshino", case=False, na=False)]
                if not hoshino.empty:
                    h_df = (hoshino.groupby("bnb_name")
                                   .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
                                   .sort_values("營收", ascending=False)
                                   .reset_index())
                    st.dataframe(h_df, use_container_width=True)
                else:
                    st.info("目前篩選範圍內無星野飯店訂單。")

# ════════════════════════════════════════════════════════
# SEB
# ════════════════════════════════════════════════════════
elif page == "🏃 SEB":
    render_simple_tab(df[df["product_line"] == "SEB"], "SEB",
                      prev_df=df_prev[df_prev["product_line"] == "SEB"])

# ════════════════════════════════════════════════════════
# 高鐵
# ════════════════════════════════════════════════════════
elif page == "🚄 高鐵":
    render_simple_tab(df[df["product_line"] == "高鐵"], "高鐵", type_col="bnb_type",
                      prev_df=df_prev[df_prev["product_line"] == "高鐵"])

# ════════════════════════════════════════════════════════
# eSIM
# ════════════════════════════════════════════════════════
elif page == "📱 eSIM":
    render_simple_tab(df[df["product_line"] == "eSIM"], "eSIM", has_checkin=False,
                      prev_df=df_prev[df_prev["product_line"] == "eSIM"])

# ════════════════════════════════════════════════════════
# Day Tour
# ════════════════════════════════════════════════════════
elif page == "🗺️ Day Tour":
    daytour_df = df[df["product_line"] == "Day Tour"]
    if daytour_df.empty:
        st.info("此篩選範圍內無 Day Tour 訂單。")
    else:
        render_simple_tab(daytour_df, "Day Tour", type_col="bnb_type",
                          prev_df=df_prev[df_prev["product_line"] == "Day Tour"])

# ════════════════════════════════════════════════════════
# 行銷管道
# ════════════════════════════════════════════════════════
elif page == "📣 行銷管道":
    ch_df = dp.marketing_channel(df)
    top_channels = ch_df.groupby("channel")["營收"].sum().sort_values(ascending=False).head(15).index
    ch_top = ch_df[ch_df["channel"].isin(top_channels)]

    ch_rev = (ch_top.groupby("channel")["營收"].sum()
                    .reset_index().sort_values("營收", ascending=False))
    fig = hbar(ch_rev, x="營收", y="channel", title="行銷管道營收（前15）")
    st.plotly_chart(fig, use_container_width=True)

    ch_stack = (ch_top.groupby(["channel", "product_line"])["營收"].sum()
                      .reset_index()
                      .sort_values("營收", ascending=False))
    fig2 = hbar(ch_stack, x="營收", y="channel", title="行銷管道 × 產品線",
                color="product_line", barmode="stack")
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("管道明細")
    pivot = (ch_df.pivot_table(index="channel", columns="product_line",
                               values="營收", aggfunc="sum", fill_value=0)
                  .reset_index())
    st.dataframe(pivot, use_container_width=True)

# ════════════════════════════════════════════════════════
# 自動洞察
# ════════════════════════════════════════════════════════
elif page == "💡 自動洞察":
    st.subheader("📊 自動業績洞察")
    st.caption("根據目前篩選條件自動計算，點按鈕重新產生。")

    if st.button("產生洞察報告", type="primary"):
        with st.spinner("分析中..."):
            insight = ai.generate_insights(df)
            st.session_state["insight_text"] = insight

    if "insight_text" in st.session_state:
        st.markdown(st.session_state["insight_text"])
