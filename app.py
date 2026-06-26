import json
import os

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import date, timedelta

import data_processor as dp
import ai_analyzer as ai

st.set_page_config(
    page_title="AsiaYo 業績儀表板",
    page_icon="🌏",
    layout="wide"
)


@st.cache_data
def _read_geojson(path, _mtime):
    # _mtime 納入快取鍵：檔案內容更新時自動失效重載
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_tw_geojson():
    path = os.path.join(os.path.dirname(__file__), "taiwan_counties.geojson")
    return _read_geojson(path, os.path.getmtime(path))


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

    # 從 URL 還原行銷管道選擇（多選用 | 分隔儲存）
    _aff_url = st.query_params.get("affiliates", "")
    _aff_default = [a for a in _aff_url.split("|") if a in affiliate_options] if _aff_url else []

    def _on_aff_change():
        vals = st.session_state.aff_sel
        st.query_params["affiliates"] = "|".join(vals) if vals else ""

    selected_affiliates = st.multiselect(
        "行銷管道（Affiliate ID）",
        options=affiliate_options,
        default=_aff_default,
        placeholder="不選 = 顯示全部",
        key="aff_sel",
        on_change=_on_aff_change
    )

    st.divider()
    _PAGES = [
        "📊 總覽", "🚢 郵輪", "🌍 GIT",
        "🏠 住宿 & 露營", "🏃 SEB", "🚄 高鐵",
        "📱 eSIM", "🗺️ Day Tour", "📣 行銷管道",
        "📶 WAU", "🔍 訂單查詢", "💡 自動洞察"
    ]
    _cur = st.query_params.get("page", _PAGES[0])
    if _cur not in _PAGES:
        _cur = _PAGES[0]

    def _on_page_change():
        st.query_params["page"] = st.session_state.nav_page

    page = st.selectbox("頁面導覽", _PAGES,
                        index=_PAGES.index(_cur),
                        key="nav_page",
                        on_change=_on_page_change)

    st.divider()
    st.header("篩選條件")

    min_date = df_all["order_date"].min().date()
    max_date = df_all["order_date"].max().date()

    # 週從星期天開始
    today = date.today()
    days_since_sunday = (today.weekday() + 1) % 7
    this_week_sun = today - timedelta(days=days_since_sunday)
    last_week_sun = this_week_sun - timedelta(days=7)

    _PRESET_OPTS = ["自訂", "昨天", "本週", "前一週", "近7天", "近30天", "近90天"]
    _preset_url  = st.query_params.get("preset", "本週")
    if _preset_url not in _PRESET_OPTS:
        _preset_url = "本週"

    def _on_preset_change():
        p = st.session_state.preset_sel
        st.query_params["preset"] = p
        if p == "自訂":
            return
        # 直接算出新日期並寫入 session_state，讓 date_input 立即更新
        if p == "昨天":
            ns, ne = today - timedelta(days=1), today - timedelta(days=1)
        elif p == "本週":
            ns, ne = this_week_sun, min(this_week_sun + timedelta(days=6), max_date)
        elif p == "前一週":
            ns, ne = last_week_sun, this_week_sun - timedelta(days=1)
        elif p == "近7天":
            ns, ne = max_date - timedelta(days=6), max_date
        elif p == "近30天":
            ns, ne = max_date - timedelta(days=29), max_date
        else:  # 近90天
            ns, ne = max_date - timedelta(days=89), max_date
        st.session_state["date_start"] = ns
        st.session_state["date_end"]   = ne
        for k in ["start", "end"]:
            if k in st.query_params:
                del st.query_params[k]

    preset = st.selectbox("快速選擇日期", _PRESET_OPTS,
                          index=_PRESET_OPTS.index(_preset_url),
                          key="preset_sel",
                          on_change=_on_preset_change)

    if preset == "昨天":
        default_start = today - timedelta(days=1)
        default_end = today - timedelta(days=1)
    elif preset == "本週":
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

    # 從 URL 還原日期（重新整理時使用）
    try:
        default_start = date.fromisoformat(st.query_params["start"])
    except (KeyError, ValueError):
        pass
    try:
        default_end = date.fromisoformat(st.query_params["end"])
    except (KeyError, ValueError):
        pass

    def _on_date_change():
        st.query_params["start"]  = str(st.session_state.date_start)
        st.query_params["end"]    = str(st.session_state.date_end)
        st.query_params["preset"] = "自訂"

    start_date = st.date_input("下單日期（起）", value=default_start,
                               min_value=min_date, max_value=max_date,
                               key="date_start", on_change=_on_date_change)
    end_date   = st.date_input("下單日期（迄）", value=default_end,
                               min_value=min_date, max_value=max_date,
                               key="date_end", on_change=_on_date_change)

    # 前期區間：週期型 preset 比「上一週同期」（往前 7 天），其餘往前推相同天數
    _n = (end_date - start_date).days + 1
    if preset in ("本週", "前一週"):
        _prev_start = start_date - timedelta(days=7)
        _prev_end   = end_date   - timedelta(days=7)
    else:
        _prev_end   = start_date - timedelta(days=1)
        _prev_start = _prev_end  - timedelta(days=_n - 1)
    st.caption(f"比較前期：{_prev_start.strftime('%m/%d')} ～ "
               f"{_prev_end.strftime('%m/%d')}（共 {_n} 天）")

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

if df.empty and page != "📶 WAU":
    st.warning("目前篩選條件下無資料，請調整篩選範圍。")
    st.stop()

# ── 前期資料（_prev_start / _prev_end 已於側邊欄依 preset 計算）──────
df_prev = dp.filter_df(
    df_all, _prev_start, _prev_end, None, selected_statuses,
    affiliate_ids=selected_affiliates if selected_affiliates else None
)

# ── KPI helper ───────────────────────────────────────────
def _fmt_money(v: float) -> str:
    """金額顯示：億級用英文縮寫（M/B）避免 st.metric 過長被截斷，較小金額維持完整。"""
    a = abs(v)
    if a >= 1e9:
        return f"NT${v / 1e9:,.2f}B"
    if a >= 1e8:
        return f"NT${v / 1e6:,.0f}M"
    return f"NT${v:,.0f}"


def kpi(col, label: str, current: float, prev: float, fmt: str = "money"):
    """st.metric with delta vs previous period."""
    if fmt == "money":
        val_str  = _fmt_money(current)
        prev_str = _fmt_money(prev)
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
_MAX_LABEL = 16


def hbar(df: pd.DataFrame, x: str, y: str, title: str, **kwargs) -> "go.Figure":
    """水平長條圖。標籤超過 _MAX_LABEL 字時截斷並加 …，完整名稱放 hover。"""
    df = df.copy()
    full_col = f"_{y}_full"
    df[full_col] = df[y].astype(str)
    df[y] = df[full_col].apply(
        lambda s: s[:_MAX_LABEL] + "…" if len(s) > _MAX_LABEL else s
    )
    n = len(df)
    # 依截斷後最長標籤動態計算 margin（中文約 14px/字）
    max_len = df[y].str.len().max() if n > 0 else _MAX_LABEL
    left_margin = max_len * 14 + 30

    fig = px.bar(df, x=x, y=y, orientation="h", title=title,
                 labels={y: ""}, hover_data={full_col: True, y: False},
                 **kwargs)
    fig.update_traces(hovertemplate="%{customdata[0]}<br>%{x:,.0f}<extra></extra>")
    fig.update_yaxes(autorange="reversed", automargin=False, tickfont_size=12)
    fig.update_layout(
        height=max(360, n * 34 + 80),
        margin=dict(l=left_margin, r=20, t=40, b=40),
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
        # 若有 type_col（如高鐵的 bnb_type）且類型超過 1 種，才畫類型佔比圓餅
        if type_col and type_col in sub_df.columns:
            type_rev = (sub_df.groupby(type_col)
                              .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
                              .reset_index())
            if len(type_rev) > 1:
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
            fig_c.update_xaxes(type="category", categoryorder="category ascending")
            st.plotly_chart(fig_c, use_container_width=True)
        else:
            # eSIM 等沒有出發日期的，改顯示裝置平台
            plat = (sub_df.groupby("platform")["order_id"].count()
                          .reset_index(name="訂單數"))
            fig_plat = px.pie(plat, names="platform", values="訂單數",
                              title=f"{label} 下單裝置", hole=0.4)
            st.plotly_chart(fig_plat, use_container_width=True)


def render_rank_tables(sub: pd.DataFrame, sub_prev: pd.DataFrame,
                       with_city: bool = True, region_fn=None):
    """商品「訂單數排行」與「成長數排行」前10名表格（與住宿頁一致）。
    region_fn 提供時，依商品名萃取「地區」並多顯示一欄。"""
    if sub.empty:
        return
    if sub_prev is None:
        sub_prev = pd.DataFrame(columns=sub.columns)
    sub = sub.copy()
    if region_fn is not None:
        sub["_region"] = sub["bnb_name"].apply(region_fn)

    group_cols = (["bnb_id", "bnb_name"]
                  + (["_region"] if region_fn is not None else [])
                  + (["bnb_city"] if with_city else []))
    rename = {"bnb_id": "BNB ID", "bnb_name": "商品名稱",
              "bnb_city": "所在城市", "_region": "地區"}
    region_cols = ["地區"] if region_fn is not None else []
    city_cols = ["所在城市"] if with_city else []

    rank_cur = (sub.groupby(group_cols)
                   .agg(訂單數=("order_id", "count"), GMV=("twd_amount", "sum"))
                   .reset_index()
                   .rename(columns=rename))
    rank_prev = (sub_prev.groupby("bnb_id")["order_id"].count()
                         .reset_index(name="前期訂單數")
                         .rename(columns={"bnb_id": "BNB ID"}))
    rank_full = rank_cur.merge(rank_prev, on="BNB ID", how="left").fillna({"前期訂單數": 0})
    rank_full["前期訂單數"] = rank_full["前期訂單數"].astype(int)
    rank_full["成長數"] = rank_full["訂單數"] - rank_full["前期訂單數"]
    rank_full["GMV"] = rank_full["GMV"].apply(lambda v: f"NT${v:,.0f}")

    st.subheader("① 訂單數排行（前10）")
    tbl1 = (rank_full[["BNB ID", "商品名稱", *region_cols, *city_cols, "訂單數", "GMV"]]
            .sort_values("訂單數", ascending=False)
            .head(10)
            .reset_index(drop=True))
    tbl1.index += 1
    st.dataframe(tbl1, use_container_width=True)

    st.subheader("② 成長數排行（前10）")
    tbl2 = (rank_full[["BNB ID", "商品名稱", *region_cols, *city_cols,
                       "訂單數", "前期訂單數", "成長數", "GMV"]]
            .sort_values("成長數", ascending=False)
            .head(10)
            .reset_index(drop=True))
    tbl2.index += 1
    st.dataframe(
        tbl2.style.map(
            lambda v: "color: green; font-weight: bold" if v > 0
                      else ("color: red; font-weight: bold" if v < 0 else ""),
            subset=["成長數"]
        ).format({"成長數": "{:+d}"}),
        use_container_width=True
    )


def render_cruise_rank(sub: pd.DataFrame, sub_prev: pd.DataFrame,
                       ship_fn, key: str):
    """郵輪航次排行：上方可依「船（號）」篩選，再出訂單數/成長數排行表。"""
    if sub.empty:
        return
    sub = sub.copy()
    sub["船"] = sub["bnb_name"].apply(ship_fn)
    prev = sub_prev.copy() if sub_prev is not None else pd.DataFrame(columns=sub.columns)
    if not prev.empty:
        prev["船"] = prev["bnb_name"].apply(ship_fn)

    ships = sorted(sub["船"].dropna().unique().tolist())
    sel = st.multiselect("篩選船（號）", ships, key=key,
                         placeholder="不選 = 顯示全部船")
    if sel:
        sub = sub[sub["船"].isin(sel)]
        if not prev.empty:
            prev = prev[prev["船"].isin(sel)]
    render_rank_tables(sub, prev, with_city=False)


# 各船統整表欄寬：數值欄窄、主要影響加寬，避免文字被截斷
_SHIP_TBL_COLCFG = {
    "品牌":   st.column_config.Column(width=90),
    "船":     st.column_config.Column(width=130),
    "本期":   st.column_config.Column(width=70),
    "前期":   st.column_config.Column(width=70),
    "差異":   st.column_config.Column(width=70),
    "主要影響": st.column_config.Column(width=460),
}


def _diff_color(v):
    if v > 0:   return "color: green; font-weight: bold"
    elif v < 0: return "color: red; font-weight: bold"
    return ""


def render_dest_heat(cur_sub: pd.DataFrame, prev_sub: pd.DataFrame,
                     empty_msg: str, topn: int = 15):
    """航線目的地熱度：本期 vs 前期（依提及訂單數）。"""
    cur = (dp.cruise_destination_heat(cur_sub, top=999)[["目的地", "訂單數"]]
           .rename(columns={"訂單數": "本期"}))
    prev = (dp.cruise_destination_heat(prev_sub, top=999)[["目的地", "訂單數"]]
            .rename(columns={"訂單數": "前期"}))
    m = cur.merge(prev, on="目的地", how="outer").fillna(0)
    m["本期"] = m["本期"].astype(int)
    m["前期"] = m["前期"].astype(int)
    m["差異"] = m["本期"] - m["前期"]
    m = m.sort_values("本期", ascending=False).head(topn).reset_index(drop=True)
    if m.empty or m["本期"].sum() == 0:
        st.info(empty_msg)
        return
    st.dataframe(
        m.style.map(_diff_color, subset=["差異"]).format({"差異": "{:+d}"}),
        use_container_width=True, hide_index=True)


def render_lead_time(sub: pd.DataFrame):
    """預訂前置天數分布（出發前多久下單）。"""
    lead = (sub["check_in"] - sub["order_date"]).dt.days.dropna()
    lead = lead[lead >= 0]
    if lead.empty:
        st.info("此範圍內無足夠資料計算前置天數。")
        return
    labels = ["0-30天", "31-60天", "61-90天", "91-120天", "121-180天", "180天以上"]
    lt = (pd.cut(lead, bins=[-1, 30, 60, 90, 120, 180, 99999], labels=labels)
            .value_counts().reindex(labels).reset_index())
    lt.columns = ["前置天數", "訂單數"]
    fig = px.bar(lt, x="前置天數", y="訂單數", title="預訂前置天數分布")
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"中位數 {lead.median():.0f} 天、平均 {lead.mean():.0f} 天"
               f"（約提前 {lead.median()/30:.1f} 個月下單）。")


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
    _xfmt = "%Y-%m" if trend_freq == "M" else "%Y-%m-%d"
    trend["日期"] = trend["日期"].dt.strftime(_xfmt)
    fig3 = px.line(trend, x="日期", y="營收", title="營收趨勢", markers=True)
    fig3.update_xaxes(type="category")  # 純日期、不顯示時間刻度
    st.plotly_chart(fig3, use_container_width=True)

    # ── GMV K 線圖 ───────────────────────────────────────────
    st.subheader("📈 GMV K 線圖")
    kc1, kc2 = st.columns([1, 2])
    with kc1:
        k_freq = st.radio("K 線週期", ["W", "M"],
                          format_func=lambda x: {"W": "週", "M": "月"}[x],
                          index=0, horizontal=True, key="kline_freq")
    with kc2:
        ma_periods = st.multiselect("均線 MA（單位＝K線週期）",
                                    [5, 10, 20, 60], default=[5, 10, 20],
                                    key="kline_ma")
    _unit = {"W": "週", "M": "月"}[k_freq]
    ohlc = dp.gmv_ohlc(df, freq=k_freq)
    if len(ohlc) < 2:
        st.info("此區間資料不足，至少需涵蓋 2 個週期才能畫圖。")
    else:
        # x 軸用純日期字串（避免出現 00:00、06:00 等時間刻度）
        _xk = ohlc["日期"].dt.strftime("%Y-%m" if k_freq == "M" else "%Y-%m-%d")
        fig_k = go.Figure(go.Candlestick(
            x=_xk,
            open=ohlc["open"], high=ohlc["high"],
            low=ohlc["low"], close=ohlc["close"],
            increasing_line_color="#d62728", decreasing_line_color="#2ca02c",
            name="GMV",
        ))
        _title = f"GMV K 線（每根＝一{_unit}，開高低收＝該期間每日 GMV）"

        # 均線：對收盤（日線即當日 GMV）做 N 期移動平均
        _ma_colors = ["#ff9900", "#1f77b4", "#9467bd", "#17becf"]
        for i, p in enumerate(sorted(ma_periods)):
            if len(ohlc) >= p:
                fig_k.add_trace(go.Scatter(
                    x=_xk, y=ohlc["close"].rolling(p).mean(),
                    mode="lines", name=f"MA{p}",
                    line=dict(width=1.5, color=_ma_colors[i % len(_ma_colors)]),
                ))
        fig_k.update_layout(
            title=_title,
            yaxis_title="GMV (NT$)",
            xaxis_rangeslider_visible=False,
            height=420,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        fig_k.update_xaxes(type="category")  # 純日期、不顯示時間刻度
        st.plotly_chart(fig_k, use_container_width=True)
        st.caption(f"開盤=期間首日 GMV、收盤=末日 GMV、最高/最低=期間內單日 GMV 最大/最小。"
                   f"均線為收盤的移動平均（MA5＝近 5 {_unit}）。紅漲綠跌（台股慣例）。")

    st.subheader("各產品線明細")
    prev_pl = (df_prev.groupby("product_line")
                      .agg(前期訂單數=("order_id", "count"), 前期營收=("twd_amount", "sum"))
                      .reset_index()
                      .rename(columns={"product_line": "product_line"}))
    detail = pl_df.merge(prev_pl, on="product_line", how="left").fillna({"前期訂單數": 0, "前期營收": 0})
    detail["前期訂單數"] = detail["前期訂單數"].astype(int)
    detail["訂單數差異"] = detail["訂單數"] - detail["前期訂單數"]
    detail["營收差異"]   = detail["營收"]   - detail["前期營收"]
    detail = detail[["product_line", "訂單數", "前期訂單數", "訂單數差異", "營收", "前期營收", "營收差異"]]
    detail = detail.rename(columns={"product_line": "產品線"})

    def _cdiff(val):
        if val > 0:   return "color: green; font-weight: bold"
        elif val < 0: return "color: red; font-weight: bold"
        return ""

    st.dataframe(
        detail.style
              .map(_cdiff, subset=["訂單數差異", "營收差異"])
              .format({
                  "訂單數差異": "{:+,.0f}",
                  "營收差異":   "NT${:+,.0f}",
                  "營收":       "NT${:,.0f}",
                  "前期營收":   "NT${:,.0f}",
              }),
        use_container_width=True, hide_index=True
    )

    # ── 轉換前 10 名（依營收）──────────────────────────────
    st.subheader("轉換前 10 名（依營收）")
    top10 = (df.groupby(["bnb_name", "product_line"])
               .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
               .reset_index())
    top10["平均客單價"] = (top10["營收"] / top10["訂單數"]).fillna(0)
    top10 = (top10.sort_values("營收", ascending=False)
                  .head(10)
                  .reset_index(drop=True)
                  .rename(columns={"bnb_name": "商品名稱", "product_line": "產品線"}))
    top10.index += 1
    st.dataframe(
        top10[["商品名稱", "產品線", "訂單數", "營收", "平均客單價"]].style.format({
            "營收":     "NT${:,.0f}",
            "平均客單價": "NT${:,.0f}",
        }),
        use_container_width=True
    )

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
                cur_aov  = homeport_df["twd_amount"].mean() if len(homeport_df) else 0
                prev_aov = hp["twd_amount"].mean() if len(hp) else 0
                kpi(h3, "AOV", cur_aov, prev_aov)

                # ── 品牌營收（依出發天數分色堆疊）────────────
                BRAND_COLORS = {"麗星郵輪": "#1f77b4", "MSC": "#ff7f0e", "歌詩達": "#2ca02c"}
                homeport_b = homeport_df.copy()
                homeport_b["品牌"] = homeport_b["bnb_name"].apply(dp._cruise_brand)
                homeport_b["船"]   = homeport_b["bnb_name"].apply(dp._homeport_ship)
                homeport_b["天數"] = (homeport_b["nights"] + 1).astype(str) + " 天"
                brand_days = (homeport_b.groupby(["品牌", "天數"])
                                        .agg(營收=("twd_amount", "sum"))
                                        .reset_index())
                fig_brand = px.bar(brand_days, x="品牌", y="營收", color="天數",
                                   barmode="stack", title="品牌營收（依出發天數分色）",
                                   labels={"天數": "出發天數"})
                st.plotly_chart(fig_brand, use_container_width=True)

                # ── 出發月份 × 船 ──────────────────────────
                homeport_ci = homeport_df.copy()
                homeport_ci["check_in_month"] = homeport_ci["check_in"].dt.to_period("M").astype(str)
                homeport_ci["品牌"] = homeport_ci["bnb_name"].apply(dp._cruise_brand)
                homeport_ci["船"]   = homeport_ci["bnb_name"].apply(dp._homeport_ship)
                ci_home = (homeport_ci.groupby(["check_in_month", "品牌"])
                                      .agg(訂單數=("order_id", "count"))
                                      .reset_index())
                fig3 = px.bar(ci_home, x="check_in_month", y="訂單數", color="品牌",
                              barmode="stack", title="出發月份 × 船",
                              labels={"check_in_month": "出發月份"},
                              color_discrete_map=BRAND_COLORS)
                fig3.update_xaxes(type="category", categoryorder="category ascending")
                st.plotly_chart(fig3, use_container_width=True)

                # ── 各船統整 ──────────────────────────────
                hp_prev = cruise_prev[cruise_prev["cruise_type"] == "母港出發"].copy()
                hp_prev["品牌"] = hp_prev["bnb_name"].apply(dp._cruise_brand)
                hp_prev["船"]   = hp_prev["bnb_name"].apply(dp._homeport_ship)

                def color_diff(val):
                    if val > 0:   return "color: green; font-weight: bold"
                    elif val < 0: return "color: red; font-weight: bold"
                    return ""

                # 計算 days_wide / mon_wide（供主因欄使用）
                cur_mon  = homeport_ci.copy(); cur_mon["期別"] = "本期"
                prev_mon = hp_prev.copy()
                prev_mon["check_in_month"] = prev_mon["check_in"].dt.to_period("M").astype(str)
                prev_mon["期別"] = "前期"

                homeport_b2 = homeport_b.copy()
                hp_prev_days = hp_prev.copy()
                hp_prev_days["天數"] = (hp_prev_days["nights"] + 1).astype(str) + " 天"
                days_cur_g  = homeport_b2.groupby(["品牌","船","天數"])["order_id"].count().reset_index(name="本期")
                days_prev_g = hp_prev_days.groupby(["品牌","船","天數"])["order_id"].count().reset_index(name="前期")
                days_wide   = (days_cur_g.merge(days_prev_g, on=["品牌","船","天數"], how="outer")
                                         .fillna(0).astype({"本期":int,"前期":int}))
                days_wide["差異"] = days_wide["本期"] - days_wide["前期"]
                days_wide["abs差"] = days_wide["差異"].abs()

                mon_cur_g  = cur_mon.groupby(["品牌","船","check_in_month"])["order_id"].count().reset_index(name="本期")
                mon_prev_g = prev_mon.groupby(["品牌","船","check_in_month"])["order_id"].count().reset_index(name="前期")
                mon_wide   = (mon_cur_g.merge(mon_prev_g, on=["品牌","船","check_in_month"], how="outer")
                                       .fillna(0).astype({"本期":int,"前期":int})
                                       .rename(columns={"check_in_month":"出發月份"}))
                mon_wide["差異"] = mon_wide["本期"] - mon_wide["前期"]
                mon_wide["abs差"] = mon_wide["差異"].abs()

                def _score_df(d):
                    d = d.copy()
                    d["成長率"] = d.apply(
                        lambda r: (r["差異"] / r["前期"] * 100) if r["前期"] > 0 else (
                            999 if r["差異"] > 0 else -999), axis=1)
                    d["abs成長率"] = d["成長率"].abs()
                    d["score"] = d["abs差"] * d["abs成長率"].pow(0.5)
                    return d

                def brand_main_reason(brand, ship):
                    parts = []
                    for wide, dim in [(days_wide, "天數"), (mon_wide, "出發月份")]:
                        sub = _score_df(wide[(wide["品牌"] == brand) & (wide["船"] == ship)])
                        cands = sub[sub["abs差"] >= 3]
                        if cands.empty: continue
                        best = cands.loc[cands["score"].idxmax()]
                        arrow = "▲" if best["差異"] > 0 else "▼"
                        rate = f"{abs(best['成長率']):.0f}%" if best["前期"] > 0 else "新增"
                        parts.append(f"{dim}：{best[dim]} {arrow}{int(abs(best['差異']))}單（{rate}）")
                    return " / ".join(parts) if parts else "–"

                # 訂單數本期 vs 前期（依品牌+船）
                ord_cur  = homeport_ci.groupby(["品牌","船"])["order_id"].count().rename("本期")
                ord_prev = hp_prev.groupby(["品牌","船"])["order_id"].count().rename("前期")
                ord_tbl  = pd.concat([ord_cur, ord_prev], axis=1).fillna(0).astype(int)
                ord_tbl["差異"] = ord_tbl["本期"] - ord_tbl["前期"]
                ord_tbl = (ord_tbl.reset_index()
                                  .sort_values(["品牌","本期"], ascending=[True, False]))
                ord_tbl["主要影響"] = ord_tbl.apply(
                    lambda r: brand_main_reason(r["品牌"], r["船"]), axis=1)
                st.dataframe(
                    ord_tbl.style.map(color_diff, subset=["差異"])
                                 .format({"差異": "{:+d}"}),
                    use_container_width=True, hide_index=True,
                    column_config=_SHIP_TBL_COLCFG
                )

                # ── 依天數分（本期/前期/差異，可依船篩選）──────────
                st.markdown("**依出發天數分**")
                day_ships = sorted(days_wide["船"].dropna().unique().tolist())
                sel_days_ship = st.multiselect("篩選船（號）", day_ships,
                                               key="hp_days_ship",
                                               placeholder="不選 = 顯示全部船")
                dw = days_wide if not sel_days_ship else days_wide[days_wide["船"].isin(sel_days_ship)]
                day_tbl = dw.groupby("天數")[["本期", "前期"]].sum().reset_index()
                day_tbl["差異"] = day_tbl["本期"] - day_tbl["前期"]
                day_tbl["_n"] = day_tbl["天數"].str.extract(r"(\d+)").astype(int)
                day_tbl = (day_tbl.sort_values("_n")
                                  .drop(columns="_n")
                                  .reset_index(drop=True))
                st.dataframe(
                    day_tbl.style.map(color_diff, subset=["差異"])
                                 .format({"差異": "{:+d}"}),
                    use_container_width=True, hide_index=True
                )

                st.divider()
                render_cruise_rank(homeport_df, hp, dp._homeport_ship, "hp_rank_ship")

                st.divider()
                st.subheader("🔍 航線目的地熱度")
                render_dest_heat(homeport_df, hp, "此範圍內無母港出發目的地。")

                st.subheader("⏱️ 預訂前置天數（出發前多久下單）")
                render_lead_time(homeport_df)

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
                fly_ci["船"]   = fly_ci["bnb_name"].apply(dp._cruise_ship)
                ci_fly = (fly_ci.groupby(["check_in_month", "品牌"])
                                .agg(訂單數=("order_id", "count"))
                                .reset_index())
                fig3 = px.bar(ci_fly, x="check_in_month", y="訂單數", color="品牌",
                              barmode="stack", title="出發月份 × 船",
                              labels={"check_in_month": "出發月份"})
                fig3.update_xaxes(type="category", categoryorder="category ascending")
                st.plotly_chart(fig3, use_container_width=True)

                # ── 各船統整 ──────────────────────────────
                fp_b = fp.copy()
                fp_b["品牌"] = fp_b["bnb_name"].apply(dp._cruise_brand)
                fp_b["船"]   = fp_b["bnb_name"].apply(dp._cruise_ship)
                fp_b["check_in_month"] = fp_b["check_in"].dt.to_period("M").astype(str)

                def fly_color_diff(val):
                    if val > 0:   return "color: green; font-weight: bold"
                    elif val < 0: return "color: red; font-weight: bold"
                    return ""

                # 晚數 / 出發月份 兩維度（供主因欄使用，依品牌+船細分）
                fly_ci_d = fly_ci.copy()
                fly_ci_d["晚數"] = fly_ci_d["nights"].astype(str) + " 晚"
                fp_b["晚數"]     = fp_b["nights"].astype(str) + " 晚"
                f_days_cur  = fly_ci_d.groupby(["品牌","船","晚數"])["order_id"].count().reset_index(name="本期")
                f_days_prev = fp_b.groupby(["品牌","船","晚數"])["order_id"].count().reset_index(name="前期")
                f_days_wide = (f_days_cur.merge(f_days_prev, on=["品牌","船","晚數"], how="outer")
                                         .fillna(0).astype({"本期":int,"前期":int}))
                f_days_wide["差異"] = f_days_wide["本期"] - f_days_wide["前期"]
                f_days_wide["abs差"] = f_days_wide["差異"].abs()

                f_mon_cur  = fly_ci.groupby(["品牌","船","check_in_month"])["order_id"].count().reset_index(name="本期")
                f_mon_prev = fp_b.groupby(["品牌","船","check_in_month"])["order_id"].count().reset_index(name="前期")
                f_mon_wide = (f_mon_cur.merge(f_mon_prev, on=["品牌","船","check_in_month"], how="outer")
                                       .fillna(0).astype({"本期":int,"前期":int})
                                       .rename(columns={"check_in_month":"出發月份"}))
                f_mon_wide["差異"] = f_mon_wide["本期"] - f_mon_wide["前期"]
                f_mon_wide["abs差"] = f_mon_wide["差異"].abs()

                def fly_score_df(d):
                    d = d.copy()
                    d["成長率"] = d.apply(
                        lambda r: (r["差異"] / r["前期"] * 100) if r["前期"] > 0 else (
                            999 if r["差異"] > 0 else -999), axis=1)
                    d["abs成長率"] = d["成長率"].abs()
                    d["score"] = d["abs差"] * d["abs成長率"].pow(0.5)
                    return d

                def fly_main_reason(brand, ship):
                    parts = []
                    for wide, dim in [(f_days_wide, "晚數"), (f_mon_wide, "出發月份")]:
                        sub = fly_score_df(wide[(wide["品牌"] == brand) & (wide["船"] == ship)])
                        cands = sub[sub["abs差"] >= 3]
                        if cands.empty: continue
                        best = cands.loc[cands["score"].idxmax()]
                        arrow = "▲" if best["差異"] > 0 else "▼"
                        rate = f"{abs(best['成長率']):.0f}%" if best["前期"] > 0 else "新增"
                        parts.append(f"{dim}：{best[dim]} {arrow}{int(abs(best['差異']))}單（{rate}）")
                    return " / ".join(parts) if parts else "–"

                # 訂單數本期 vs 前期（依品牌+船）
                f_ord_cur  = fly_ci.groupby(["品牌","船"])["order_id"].count().rename("本期")
                f_ord_prev = fp_b.groupby(["品牌","船"])["order_id"].count().rename("前期")
                f_ord_tbl  = pd.concat([f_ord_cur, f_ord_prev], axis=1).fillna(0).astype(int)
                f_ord_tbl["差異"] = f_ord_tbl["本期"] - f_ord_tbl["前期"]
                f_ord_tbl = (f_ord_tbl.reset_index()
                                      .sort_values(["品牌","本期"], ascending=[True, False]))
                f_ord_tbl["主要影響"] = f_ord_tbl.apply(
                    lambda r: fly_main_reason(r["品牌"], r["船"]), axis=1)
                st.dataframe(
                    f_ord_tbl.style.map(fly_color_diff, subset=["差異"])
                                   .format({"差異": "{:+d}"}),
                    use_container_width=True, hide_index=True,
                    column_config=_SHIP_TBL_COLCFG
                )

                st.divider()
                render_cruise_rank(fly_df, fp, dp._cruise_ship, "fly_rank_ship")

                st.divider()
                st.subheader("🔍 航線目的地熱度")
                render_dest_heat(fly_df, fp, "此範圍內無飛航郵輪目的地。")

                st.subheader("⏱️ 預訂前置天數（出發前多久下單）")
                render_lead_time(fly_df)

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
            region_df = dp.git_country_distribution(df)
            region_df["佔比"] = (region_df["營收"] / region_df["營收"].sum() * 100).round(1).astype(str) + "%"
            fig = px.treemap(region_df, path=["地區"], values="營收",
                             title="GIT 地區分布（依營收）",
                             custom_data=["佔比", "訂單數"])
            fig.update_traces(
                texttemplate="<b>%{label}</b><br>%{customdata[0]}<br>NT$%{value:,.0f}<br>%{customdata[1]} 單",
                textfont_size=14)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            ci_df = dp.checkin_monthly(df, "GIT")
            fig2 = px.bar(ci_df, x="check_in_month", y="訂單數",
                          title="GIT 出發月份分佈",
                          labels={"check_in_month": "出發月份"})
            fig2.update_xaxes(type="category", categoryorder="category ascending")
            st.plotly_chart(fig2, use_container_width=True)

        st.divider()
        _git_regions = sorted(git_df["bnb_name"].apply(dp._git_region).unique().tolist())
        sel_region = st.multiselect("地區篩選", _git_regions,
                                    placeholder="不選 = 全部地區", key="git_rank_region")
        git_r, git_pr = git_df, git_prev
        if sel_region:
            git_r  = git_df[git_df["bnb_name"].apply(dp._git_region).isin(sel_region)]
            git_pr = git_prev[git_prev["bnb_name"].apply(dp._git_region).isin(sel_region)]
        render_rank_tables(git_r, git_pr, with_city=False, region_fn=dp._git_region)

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
                if pl == "TW":
                    # 台灣：用縣市地圖呈現（顏色越深營收越高）
                    geo_df = dp.tw_city_geo(df)
                    fig = px.choropleth(
                        geo_df, geojson=load_tw_geojson(), locations="縣市",
                        featureidkey="properties.COUNTYNAME",
                        color="營收", color_continuous_scale="Blues",
                        hover_data={"訂單數": True, "營收": ":,.0f"},
                        title="台灣住宿 各縣市營收分布",
                    )
                    fig.update_geos(fitbounds="locations", visible=False)
                    fig.update_layout(height=460, margin=dict(l=0, r=0, t=40, b=0))
                else:
                    city_df = dp.accommodation_region_distribution(df, pl)
                    fig = hbar(city_df, x="營收", y="bnb_city",
                               title=f"{label} 城市排行（前20）")
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                ci_df = dp.checkin_monthly(df, pl)
                fig2 = px.bar(ci_df, x="check_in_month", y="訂單數",
                              title=f"{label} 入住月份分佈",
                              labels={"check_in_month": "入住月份"})
                fig2.update_xaxes(type="category", categoryorder="category ascending")
                st.plotly_chart(fig2, use_container_width=True)

            if pl == "TW":
                st.subheader("住宿類型分佈")
                type_df = (sub.groupby("bnb_type")
                              .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
                              .reset_index()
                              .sort_values("營收", ascending=False))
                tc1, tc2 = st.columns(2)
                with tc1:
                    fig_t = px.bar(type_df, x="bnb_type", y="訂單數", color="bnb_type",
                                   title="住宿類型（訂單數）", text_auto=True)
                    fig_t.update_layout(showlegend=False)
                    st.plotly_chart(fig_t, use_container_width=True)
                with tc2:
                    fig_t2 = px.bar(type_df, x="bnb_type", y="營收", color="bnb_type",
                                    title="住宿類型（營收）", text_auto=".2s")
                    fig_t2.update_layout(showlegend=False)
                    st.plotly_chart(fig_t2, use_container_width=True)

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

            # ── 產品排行 ──────────────────────────────────
            st.divider()
            render_rank_tables(sub, sub_prev, with_city=True)

# ════════════════════════════════════════════════════════
# SEB
# ════════════════════════════════════════════════════════
elif page == "🏃 SEB":
    seb_df   = df[df["product_line"] == "SEB"]
    seb_prev = df_prev[df_prev["product_line"] == "SEB"]
    render_simple_tab(seb_df, "SEB", prev_df=seb_prev)
    if not seb_df.empty:
        st.divider()
        render_rank_tables(seb_df, seb_prev, with_city=False)

# ════════════════════════════════════════════════════════
# 高鐵
# ════════════════════════════════════════════════════════
elif page == "🚄 高鐵":
    thsr_df   = df[df["product_line"] == "高鐵"]
    thsr_prev = df_prev[df_prev["product_line"] == "高鐵"]
    render_simple_tab(thsr_df, "高鐵", type_col="bnb_type", prev_df=thsr_prev)
    if not thsr_df.empty:
        st.divider()
        render_rank_tables(thsr_df, thsr_prev, with_city=False)

# ════════════════════════════════════════════════════════
# eSIM
# ════════════════════════════════════════════════════════
elif page == "📱 eSIM":
    esim_df   = df[df["product_line"] == "eSIM"]
    esim_prev = df_prev[df_prev["product_line"] == "eSIM"]
    render_simple_tab(esim_df, "eSIM", has_checkin=False, prev_df=esim_prev)
    if not esim_df.empty:
        st.divider()
        render_rank_tables(esim_df, esim_prev, with_city=False)

# ════════════════════════════════════════════════════════
# Day Tour
# ════════════════════════════════════════════════════════
elif page == "🗺️ Day Tour":
    daytour_df   = df[df["product_line"] == "Day Tour"]
    daytour_prev = df_prev[df_prev["product_line"] == "Day Tour"]
    if daytour_df.empty:
        st.info("此篩選範圍內無 Day Tour 訂單。")
    else:
        render_simple_tab(daytour_df, "Day Tour", type_col="bnb_type",
                          prev_df=daytour_prev)
        st.divider()
        render_rank_tables(daytour_df, daytour_prev, with_city=False)

# ════════════════════════════════════════════════════════
# 行銷管道
# ════════════════════════════════════════════════════════
elif page == "📣 行銷管道":
    ch_df = dp.marketing_channel(df)

    # ── 管道別 本期 vs 前期（訂單數 / GMV / AOV）──────────────
    st.subheader("管道別 本期 vs 前期")
    cur_s  = dp.channel_summary(df).rename(columns={
        "訂單數": "訂單數", "GMV": "GMV", "AOV": "AOV"})
    prev_s = dp.channel_summary(df_prev).rename(columns={
        "訂單數": "前期訂單數", "GMV": "前期GMV", "AOV": "前期AOV"})
    cmp = cur_s.merge(prev_s, on="channel", how="left").fillna(0)
    cmp["訂單差"] = cmp["訂單數"] - cmp["前期訂單數"].astype(int)
    cmp["GMV差"]  = cmp["GMV"]   - cmp["前期GMV"]
    cmp["AOV差"]  = cmp["AOV"]   - cmp["前期AOV"]
    cmp = cmp.sort_values("GMV", ascending=False).reset_index(drop=True)
    cmp = cmp[["channel",
               "訂單數", "前期訂單數", "訂單差",
               "GMV", "前期GMV", "GMV差",
               "AOV", "前期AOV", "AOV差"]].rename(columns={"channel": "管道"})

    def _cdiff(val):
        if val > 0:   return "color: green; font-weight: bold"
        elif val < 0: return "color: red; font-weight: bold"
        return ""

    st.dataframe(
        cmp.style
           .map(_cdiff, subset=["訂單差", "GMV差", "AOV差"])
           .format({
               "前期訂單數": "{:,.0f}",
               "訂單差":     "{:+,.0f}",
               "GMV":        "NT${:,.0f}",
               "前期GMV":    "NT${:,.0f}",
               "GMV差":      "NT${:+,.0f}",
               "AOV":        "NT${:,.0f}",
               "前期AOV":    "NT${:,.0f}",
               "AOV差":      "NT${:+,.0f}",
           }),
        use_container_width=True, hide_index=True
    )

    st.subheader("管道明細（各產品線營收）")
    pivot = (ch_df.pivot_table(index="channel", columns="product_line",
                               values="營收", aggfunc="sum", fill_value=0)
                  .reset_index())
    st.dataframe(pivot, use_container_width=True)

# ════════════════════════════════════════════════════════
# 訂單查詢
# ════════════════════════════════════════════════════════
elif page == "🔍 訂單查詢":
    st.caption("查詢結果會套用側邊欄的日期、訂單狀態、行銷管道篩選。")

    q1, q2 = st.columns([2, 1])
    with q1:
        kw = st.text_input("關鍵字（訂單編號 / 商品名稱 / 城市）",
                           placeholder="輸入關鍵字，可留空只用下方篩選")
    with q2:
        pl_opts = sorted(df["product_line"].dropna().unique().tolist())
        sel_pl = st.multiselect("產品線", pl_opts, placeholder="不選 = 全部")

    res = df.copy()
    if sel_pl:
        res = res[res["product_line"].isin(sel_pl)]
    if kw and kw.strip():
        k = kw.strip().lower()
        mask = (
            res["order_id"].astype(str).str.lower().str.contains(k, na=False)
            | res["bnb_name"].astype(str).str.lower().str.contains(k, na=False)
            | res["bnb_city"].astype(str).str.lower().str.contains(k, na=False)
        )
        res = res[mask]

    st.markdown(f"**符合 {len(res):,} 筆**，營收合計 NT${res['twd_amount'].sum():,.0f}")

    _cols = ["order_id", "order_date", "product_line", "bnb_name", "bnb_city",
             "booking_status", "affiliate_id", "check_in", "check_out",
             "nights", "twd_amount"]
    _rename = {
        "order_id": "訂單編號", "order_date": "下單日期", "product_line": "產品線",
        "bnb_name": "商品名稱", "bnb_city": "城市", "booking_status": "狀態",
        "affiliate_id": "行銷管道", "check_in": "入住/出發", "check_out": "退房/結束",
        "nights": "晚數", "twd_amount": "金額",
    }
    show = (res[_cols]
            .sort_values("order_date", ascending=False)
            .rename(columns=_rename))

    if show.empty:
        st.info("查無符合條件的訂單，請調整關鍵字或篩選。")
    else:
        st.dataframe(
            show.style.format({
                "下單日期": lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) else "",
                "入住/出發": lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) else "",
                "退房/結束": lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) else "",
                "金額": "NT${:,.0f}",
            }),
            use_container_width=True, hide_index=True
        )
        csv = show.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ 下載 CSV", csv,
                           file_name="訂單查詢結果.csv", mime="text/csv")

# ════════════════════════════════════════════════════════
# WAU
# ════════════════════════════════════════════════════════
elif page == "📶 WAU":
    st.caption("GA4 全站每週活躍使用者（WAU）趨勢。此頁**不受側邊欄篩選影響**，使用下方獨立區間。")
    win = st.selectbox("顯示區間", ["近12週", "近26週", "近52週", "全部"], index=0)

    wau = dp.load_wau()
    if wau.empty:
        st.info("目前讀不到 GA4 WAU 資料（請確認來源試算表可存取）。")
    else:
        wau = wau.sort_values("週起始日")
        _n = {"近12週": 12, "近26週": 26, "近52週": 52}.get(win)
        if _n:
            wau = wau.tail(_n)
        wau = wau.reset_index(drop=True)
        wau["週"] = wau["週起始日"].dt.strftime("%Y-%m-%d")
        wau["週增減%"] = (wau["WAU"].pct_change() * 100).round(1)

        # 最新週 KPI（含與前一週比較）
        last = wau.iloc[-1]
        prev_wau = int(wau.iloc[-2]["WAU"]) if len(wau) >= 2 else 0
        d = int(last["WAU"]) - prev_wau
        c1, c2 = st.columns(2)
        c1.metric(f"最新週 WAU（{last['週']}）", f"{int(last['WAU']):,}",
                  delta=f"{d:+,}（前一週 {prev_wau:,}）" if prev_wau else None)
        c2.metric("區間平均 WAU", f"{int(wau['WAU'].mean()):,}")

        fig = px.line(wau, x="週", y="WAU", markers=True, title="每週 WAU 趨勢")
        fig.update_xaxes(type="category")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("WAU 為 GA4 全站每週活躍使用者（週日為一週開始）；最新一週可能未完整。")

        tbl = wau[["週", "WAU", "週增減%"]].iloc[::-1].reset_index(drop=True)
        st.dataframe(tbl, use_container_width=True, hide_index=True)

        # 各管道 WAU 趨勢（直接/未知量太大，單獨拆出避免壓平其他線）
        st.subheader("各管道 WAU 趨勢")
        ga4 = dp.load_ga4_channel()
        if ga4.empty:
            st.info("目前讀不到 GA4 管道資料。")
        else:
            keep = set(wau["週起始日"])  # 與上方相同區間
            ga4w = ga4[ga4["週起始日"].isin(keep)].copy()
            ga4w["週"] = ga4w["週起始日"].dt.strftime("%Y-%m-%d")
            others = ga4w[ga4w["管道"] != "直接/未知"]
            direct = ga4w[ga4w["管道"] == "直接/未知"]
            gc1, gc2 = st.columns([3, 2])
            with gc1:
                fig_c = px.line(others.sort_values("週起始日"), x="週", y="使用者",
                                color="管道", markers=True, title="各管道（不含直接/未知）",
                                category_orders={"管道": [c for c in dp.CHANNEL_BUCKETS
                                                         if c != "直接/未知"]})
                fig_c.update_xaxes(type="category")
                st.plotly_chart(fig_c, use_container_width=True)
            with gc2:
                fig_d = px.line(direct.sort_values("週起始日"), x="週", y="使用者",
                                markers=True, title="直接/未知")
                fig_d.update_xaxes(type="category")
                fig_d.update_traces(line_color="#999")
                st.plotly_chart(fig_d, use_container_width=True)

# ════════════════════════════════════════════════════════
# 自動洞察
# ════════════════════════════════════════════════════════
elif page == "💡 自動洞察":
    st.subheader("📊 自動業績洞察")
    st.caption("根據目前篩選條件自動計算，點按鈕重新產生。")

    if st.button("產生洞察報告", type="primary"):
        with st.spinner("分析中..."):
            insight = ai.generate_insights(df, df_prev, start_date, end_date)
            st.session_state["insight_text"] = insight

    if "insight_text" in st.session_state:
        # 跳脫 $，避免 NT$ 金額被當成 LaTeX 數學式
        st.markdown(st.session_state["insight_text"].replace("$", "\\$"))
