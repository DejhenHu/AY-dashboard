import pandas as pd


def generate_insights(df: pd.DataFrame, df_prev: pd.DataFrame = None) -> str:
    sections = []
    df = df.copy()
    if df_prev is None:
        df_prev = pd.DataFrame(columns=df.columns)

    # ── 整體趨勢（本期 vs 前期，與全站一致）──────────────────
    trend_lines = []
    rev_now  = df["twd_amount"].sum()
    rev_prev = df_prev["twd_amount"].sum()
    if rev_prev > 0:
        chg = (rev_now - rev_prev) / rev_prev * 100
        arrow = "↑" if chg > 0 else "↓"
        trend_lines.append(
            f"- 本期營收 NT${rev_now:,.0f}，較前期 {arrow} {abs(chg):.1f}%"
            f"（前期 NT${rev_prev:,.0f}）")
    else:
        trend_lines.append(f"- 本期營收 NT${rev_now:,.0f}")

    ord_now  = len(df)
    ord_prev = len(df_prev)
    if ord_prev > 0:
        chg2 = (ord_now - ord_prev) / ord_prev * 100
        arrow2 = "↑" if chg2 > 0 else "↓"
        trend_lines.append(
            f"- 本期訂單數 {ord_now:,} 筆，較前期 {arrow2} {abs(chg2):.1f}%"
            f"（前期 {ord_prev:,} 筆）")
    else:
        trend_lines.append(f"- 本期訂單數 {ord_now:,} 筆")

    if trend_lines:
        sections.append("### 📈 本期概況\n" + "\n".join(trend_lines))

    # ── 各產品線表現 ──────────────────────────────────────
    pl_df = (df.groupby("product_line")
               .agg(營收=("twd_amount", "sum"), 訂單數=("order_id", "count"))
               .sort_values("營收", ascending=False))
    total_rev = pl_df["營收"].sum()

    pl_lines = []
    for pl, row in pl_df.iterrows():
        pct = row["營收"] / total_rev * 100 if total_rev else 0
        pl_lines.append(f"- **{pl}**：NT${row['營收']:,.0f}（{pct:.1f}%），{int(row['訂單數'])} 單")

    if pl_lines:
        sections.append("### 💰 各產品線業績\n" + "\n".join(pl_lines))

    # ── 郵輪洞察 ─────────────────────────────────────────
    cruise = df[df["product_line"] == "Cruise"]
    if len(cruise):
        cruise_lines = []

        type_df = cruise.groupby("cruise_type")["twd_amount"].sum()
        for ct, rev in type_df.sort_values(ascending=False).items():
            pct = rev / type_df.sum() * 100
            cruise_lines.append(f"- {ct}：NT${rev:,.0f}（{pct:.1f}%）")

        avg_nights = cruise["nights"].mean()
        cruise_lines.append(f"- 平均出遊晚數：{avg_nights:.1f} 晚")

        future = cruise[cruise["check_in"] > pd.Timestamp.today()]
        if len(future):
            peak_month = (future.groupby(future["check_in"].dt.to_period("M"))["order_id"]
                                .count().idxmax())
            cruise_lines.append(f"- 未來出發最熱月份：{peak_month}")

        sections.append("### 🚢 郵輪洞察\n" + "\n".join(cruise_lines))

    # ── 住宿洞察 ─────────────────────────────────────────
    accom_lines = []
    for pl, label in [("TW", "台灣"), ("JP", "日本"), ("KR", "韓國")]:
        sub = df[df["product_line"] == pl]
        if len(sub):
            top_city = sub.groupby("bnb_city")["twd_amount"].sum().idxmax()
            rev = sub["twd_amount"].sum()
            accom_lines.append(f"- **{label}**：NT${rev:,.0f}，熱門城市 {top_city}")
    if accom_lines:
        sections.append("### 🏠 住宿洞察\n" + "\n".join(accom_lines))

    # ── 行銷管道 ─────────────────────────────────────────
    ch = df.copy()
    ch["channel"] = ch["affiliate_id"].apply(
        lambda x: x if str(x).strip() not in ("", "-", "0", "nan") else "直接/未知"
    )
    top_ch = (ch.groupby("channel")["twd_amount"].sum()
                .sort_values(ascending=False).head(5))
    ch_lines = [f"- **{ch_name}**：NT${rev:,.0f}" for ch_name, rev in top_ch.items()]
    if ch_lines:
        sections.append("### 📣 前5大行銷管道\n" + "\n".join(ch_lines))

    # ── 注意事項 ─────────────────────────────────────────
    flags = []
    canceled = df[df["booking_status"] == "canceled"]
    if len(df):
        cancel_rate = len(canceled) / len(df) * 100
        if cancel_rate > 15:
            flags.append(f"⚠️ 取消率偏高：{cancel_rate:.1f}%（超過 15% 警戒線）")

    low_pl = pl_df[pl_df["訂單數"] < 10]
    for pl in low_pl.index:
        flags.append(f"⚠️ **{pl}** 訂單量極少（{int(low_pl.loc[pl, '訂單數'])} 單），可能需要關注")

    if flags:
        sections.append("### ⚠️ 注意事項\n" + "\n".join(flags))

    return "\n\n".join(sections) if sections else "目前資料不足以產生洞察，請調整日期範圍。"
