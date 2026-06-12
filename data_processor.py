import re

import pandas as pd
import streamlit as st

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1sXj5DPEN9Jmjs_0HBFPeiMaicXaqE_sZ3Jbk3TPajYs"
    "/export?format=csv&gid=100183531"
)

ACCOMMODATION_TYPES = {
    "Bnb / Apartment", "Economy Hotel", "Hostel",
    "Hotel", "Motel", "Serviced apartment", "Villa"
}

HOMEPORT_CRUISE_KEYWORDS = ["麗星", "star cruises", "探索星號", "msc", "地中海郵輪", "歌詩達", "costa"]

DAY_TOUR_TYPES = {"Attraction Tickets", "Land tour", "Tours & Experiences", "Transportation"}

# 實際欄位名稱（從 Google Sheet 第一列讀到的）→ 程式內部名稱
COLUMN_RENAME = {
    "booking status": "booking_status",
    "bnb city":       "bnb_city",
    "column switch 1": "affiliate_id",
    "column switch 2": "coupon",
    "column switch 3": "column_switch_3",
}


@st.cache_data(ttl=1800)
def load_data() -> pd.DataFrame:
    df = pd.read_csv(SHEET_CSV_URL, dtype=str)
    df.rename(columns=COLUMN_RENAME, inplace=True)
    return _clean(df)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df["check_in"]   = pd.to_datetime(df["check_in"],   errors="coerce")
    df["check_out"]  = pd.to_datetime(df["check_out"],  errors="coerce")

    for col in ["guests", "adult", "child", "nights", "rooms"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # twd_amount 可能有千分位逗號，例如 "2,100"
    df["twd_amount"] = (
        df["twd_amount"].astype(str)
        .str.replace(",", "", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
        .fillna(0)
    )

    # 移除公式填充的空白列
    df = df[df["order_id"].notna() & (df["order_id"].astype(str).str.strip() != "")].copy()

    # 排除「補款專用」類項目（補款非真實新訂單，不計入任何頁面統計）
    df = df[~df["bnb_name"].astype(str).str.contains("補款", na=False)].copy()

    df["tags"]           = df["tags"].astype(str).str.lower()
    df["bnb_name_lower"] = df["bnb_name"].astype(str).str.lower()
    df["product_line"]   = df.apply(_classify, axis=1)
    df["cruise_type"]    = df.apply(_cruise_type, axis=1)
    return df


def _classify(row) -> str:
    bt   = str(row.get("bnb_type", ""))
    cs3  = str(row.get("column_switch_3", ""))
    tags = str(row.get("tags", ""))

    if bt == "Cruise":
        return "Cruise"
    if bt == "Campground" or (bt == "Bnb / Apartment" and "camping" in tags):
        return "Camping"
    if bt in ACCOMMODATION_TYPES:
        if "taiwan" in cs3.lower():
            return "TW"
        if "korea" in cs3.lower():
            return "KR"
        if "japan" in cs3.lower():
            return "JP"
        return "住宿(其他)"
    if bt in ("Sport Activities", "ski"):
        return "SEB"
    if bt in ("THSR Holiday", "THSR Upselling", "THSR Tickets"):
        return "高鐵"
    if bt == "Group tour":
        return "GIT"
    if bt == "eSIM":
        return "eSIM"
    if bt in DAY_TOUR_TYPES:
        return "Day Tour"
    return "其他"


def _cruise_type(row) -> str:
    if row.get("product_line") != "Cruise":
        return ""
    name = str(row.get("bnb_name", "")).lower()
    for kw in HOMEPORT_CRUISE_KEYWORDS:
        if kw.lower() in name:
            return "母港出發"
    return "飛航郵輪"


DIRECT_LABEL = "直接/未知"
_EMPTY_VALUES = {"", "-", "0", "nan"}


def get_affiliate_options(df: pd.DataFrame) -> list:
    """回傳所有 affiliate_id 選項（依頻率排序），空值統一標示為 DIRECT_LABEL。"""
    counts = df["affiliate_id"].value_counts(dropna=False)
    options = []
    for val in counts.index:
        label = DIRECT_LABEL if str(val).strip() in _EMPTY_VALUES else str(val)
        if label not in options:
            options.append(label)
    return options


def filter_df(df: pd.DataFrame, start_date=None, end_date=None,
              product_lines=None, statuses=None,
              affiliate_ids=None) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    if start_date:
        mask &= df["order_date"] >= pd.Timestamp(start_date)
    if end_date:
        mask &= df["order_date"] <= pd.Timestamp(end_date)
    if product_lines:
        mask &= df["product_line"].isin(product_lines)
    if statuses:
        mask &= df["booking_status"].isin(statuses)
    if affiliate_ids is not None:
        # 把顯示標籤轉回實際值來篩選
        if DIRECT_LABEL in affiliate_ids:
            direct_mask = df["affiliate_id"].apply(
                lambda x: str(x).strip() in _EMPTY_VALUES
            )
            real_ids = [a for a in affiliate_ids if a != DIRECT_LABEL]
            mask &= direct_mask | df["affiliate_id"].isin(real_ids)
        else:
            mask &= df["affiliate_id"].isin(affiliate_ids)
    return df[mask].copy()


def revenue_by_product_line(df: pd.DataFrame) -> pd.DataFrame:
    return (df.groupby("product_line")
              .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
              .sort_values("營收", ascending=False)
              .reset_index())


def revenue_trend(df: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    return (df.set_index("order_date")
              .resample(freq)["twd_amount"]
              .sum()
              .reset_index()
              .rename(columns={"order_date": "日期", "twd_amount": "營收"}))


def cruise_checkin_distribution(df: pd.DataFrame) -> pd.DataFrame:
    cruise = df[df["product_line"] == "Cruise"].copy()
    cruise["check_in_month"] = cruise["check_in"].dt.to_period("M").astype(str)
    return (cruise.groupby(["check_in_month", "cruise_type"])
                  .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
                  .reset_index())


def cruise_nights_distribution(df: pd.DataFrame) -> pd.DataFrame:
    cruise = df[df["product_line"] == "Cruise"].copy()
    return (cruise.groupby("nights")
                  .agg(訂單數=("order_id", "count"))
                  .reset_index()
                  .sort_values("nights"))


def _cruise_brand(name: str) -> str:
    n = str(name).lower()
    if "麗星" in n or "star cruises" in n or "探索星號" in n:
        return "麗星郵輪"
    if ("msc" in n or "地中海" in n) and "榮耀" in str(name):
        return "MSC地中海"
    if "msc" in n or "地中海郵輪" in str(name):
        return "MSC地中海"
    if "歌詩達" in n or "costa" in n:
        return "歌詩達"
    if "迪士尼" in n or "disney" in n:
        return "迪士尼"
    if "公主遊輪" in n or "princess" in n:
        return "公主遊輪"
    if "星夢" in n or "genting dream" in n or "雲頂夢" in n:
        return "星夢郵輪"
    if "挪威" in n or "ncl" in n or "norwegian" in n:
        return "挪威郵輪"
    if "皇后" in n or "cunard" in n:
        return "皇后郵輪"
    return "其他郵輪"


_SHIP_RE = re.compile(r"([一-鿿A-Za-z]+號)")


def _cruise_ship(name: str) -> str:
    """從商品名稱萃取船名（XX號），並清理黏在前面的品牌字，讓同船的不同命名能合併。"""
    m = _SHIP_RE.search(str(name))
    if not m:
        return "（無船名）"
    ship = m.group(1)
    # 去掉黏在船名前的品牌字首
    for prefix in ["三井海洋", "公主", "名人"]:
        if ship.startswith(prefix) and len(ship) > len(prefix) + 1:
            ship = ship[len(prefix):]
            break
    # 去掉夾在中間的品牌/連接字
    for w in ["郵輪", "遊輪", "MSC", "地中海"]:
        ship = ship.replace(w, "")
    return ship or "（無船名）"


def cruise_by_brand(df: pd.DataFrame) -> pd.DataFrame:
    cruise = df[df["product_line"] == "Cruise"].copy()
    cruise["品牌"] = cruise["bnb_name"].apply(_cruise_brand)
    return (cruise.groupby(["品牌", "cruise_type"])
                  .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
                  .reset_index())


def git_region_distribution(df: pd.DataFrame) -> pd.DataFrame:
    git = df[df["product_line"] == "GIT"].copy()
    return (git.groupby("bnb_name")
               .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
               .sort_values("營收", ascending=False)
               .reset_index()
               .head(20))


def accommodation_region_distribution(df: pd.DataFrame, product_line: str) -> pd.DataFrame:
    sub = df[df["product_line"] == product_line].copy()
    return (sub.groupby("bnb_city")
               .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
               .sort_values("營收", ascending=False)
               .reset_index()
               .head(20))


def checkin_monthly(df: pd.DataFrame, product_line: str) -> pd.DataFrame:
    sub = df[df["product_line"] == product_line].copy()
    sub["check_in_month"] = sub["check_in"].dt.to_period("M").astype(str)
    return (sub.groupby("check_in_month")
               .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
               .reset_index())


def marketing_channel(df: pd.DataFrame) -> pd.DataFrame:
    ch = df.copy()
    ch["channel"] = ch["affiliate_id"].apply(
        lambda x: x if str(x).strip() not in ("", "-", "0", "nan") else "直接/未知"
    )
    return (ch.groupby(["channel", "product_line"])
              .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
              .reset_index()
              .sort_values("營收", ascending=False))
