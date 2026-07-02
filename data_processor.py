import re

import pandas as pd
import streamlit as st

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1sXj5DPEN9Jmjs_0HBFPeiMaicXaqE_sZ3Jbk3TPajYs"
    "/export?format=csv&gid=100183531"
)

# GA4 每週活躍使用者(WAU)：A 欄 yearWeek(YYYYWW)、B 欄 activeUsers
WAU_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1DUjbMhGk0ElpYZwqv2b7_5h_UGtZBYSfhg2tMN34SEU"
    "/gviz/tq?tqx=out:csv&gid=1711406010"
)

# GA4 每週各管道使用者：A 欄 yearWeek、B 欄 sessionDefaultChannelGroup、C 欄 activeUsers
GA4_CHANNEL_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1TRKBgqEzGyODbkDrZXTQX2JaC4oQN3YNQn_V_2_yIOQ"
    "/gviz/tq?tqx=out:csv&gid=199567350"
)

# 管道桶顯示順序
CHANNEL_BUCKETS = ["付費廣告", "自然搜尋", "社群/LINE", "推薦/聯盟", "CRM", "直接/未知"]

# GA4 管道分組 → 管道桶
_GA4_CHANNEL_BUCKET = {
    "Paid Search": "付費廣告", "Paid Social": "付費廣告", "Paid Other": "付費廣告",
    "Display": "付費廣告", "Paid Video": "付費廣告", "Cross-network": "付費廣告",
    "Organic Search": "自然搜尋",
    "Organic Social": "社群/LINE", "Organic Video": "社群/LINE",
    "Referral": "推薦/聯盟",
    "Email": "CRM", "SMS": "CRM", "Mobile Push Notifications": "CRM",
    "Direct": "直接/未知", "Unassigned": "直接/未知",
}

ACCOMMODATION_TYPES = {
    "Bnb / Apartment", "Economy Hotel", "Hostel",
    "Hotel", "Motel", "Serviced apartment", "Villa"
}

# ── 郵輪母港 / 飛航 判斷 ──────────────────────────────
# 同一艘船可能從台灣港出發（母港）或從國外登船（飛航），故優先看名稱裡的出發/登船港，
# 名稱沒寫港口時，再用「固定從台灣出發的母港船隊」船名來補判。

# 明確標示國外登船 → 飛航
_FOREIGN_EMBARK_RE = re.compile(
    r"(新加坡|溫哥華|西雅圖|舊金山|史華德|羅馬|那不勒斯|洛杉磯|香港|義大利)[^，。]{0,5}(登船|上船|出發)")
# 明確從台灣港出發：基隆/高雄 + 啟航/出發/登船/上船，或括號內(基隆…)，或「基隆-」移航首站
_TW_DEPART_RE = re.compile(
    r"[（(](基隆|高雄)|(基隆|高雄)\s*(蘇澳)?\s*(啟航|出發|登船|上船)|(基隆|高雄)\s*[-－]")
# 泛用登船（前面排除「贈/送/迎」等贈品用語，避免誤判「贈登船迎賓套裝」）
_GENERIC_EMBARK_RE = re.compile(r"(?<![贈送迎])(登船|上下船|上船)")
# 固定從台灣出發的母港船隊船名（名稱未標港口時用來補判）
_TAIWAN_FLEET_SHIPS = ("探索星號", "榮耀號", "莎倫娜號", "海洋富士號", "富士號")

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


def _yearweek_to_sunday(yw: str) -> "pd.Timestamp":
    """GA4 yearWeek(YYYYWW) → 該週起始日(週日)。GA4 第1週為含 1/1 的那一週。"""
    y, w = int(yw[:4]), int(yw[4:])
    jan1 = pd.Timestamp(year=y, month=1, day=1)
    week01 = jan1 - pd.Timedelta(days=(jan1.dayofweek + 1) % 7)  # 1/1 當週的週日
    return week01 + pd.Timedelta(weeks=w - 1)


@st.cache_data(ttl=1800)
def load_wau() -> pd.DataFrame:
    """讀 GA4 每週活躍使用者；自動抓 A 欄為 6 位數 yearWeek 的列。回傳 週起始日 / WAU。"""
    try:
        raw = pd.read_csv(WAU_CSV_URL, header=None, dtype=str)
    except Exception:
        return pd.DataFrame(columns=["週起始日", "WAU"])
    a = raw[0].astype(str).str.strip()
    mask = a.str.match(r"^\d{6}$")
    wau = pd.DataFrame({
        "yearWeek": a[mask].values,
        "WAU": pd.to_numeric(raw.loc[mask, 1], errors="coerce").values,
    }).dropna()
    if wau.empty:
        return pd.DataFrame(columns=["週起始日", "WAU"])
    wau["WAU"] = wau["WAU"].astype(int)
    wau["週起始日"] = wau["yearWeek"].apply(_yearweek_to_sunday)
    return wau.sort_values("週起始日").reset_index(drop=True)[["週起始日", "WAU"]]


@st.cache_data(ttl=1800)
def load_ga4_channel() -> pd.DataFrame:
    """GA4 各管道每週使用者 → 週起始日 / 管道(桶) / 使用者。"""
    try:
        raw = pd.read_csv(GA4_CHANNEL_CSV_URL, header=None, dtype=str)
    except Exception:
        return pd.DataFrame(columns=["週起始日", "管道", "使用者"])
    a = raw[0].astype(str).str.strip()
    mask = a.str.match(r"^\d{6}$")
    d = pd.DataFrame({
        "yearWeek": a[mask].values,
        "channel": raw.loc[mask, 1].astype(str).values,
        "使用者": pd.to_numeric(raw.loc[mask, 2], errors="coerce").values,
    }).dropna()
    if d.empty:
        return pd.DataFrame(columns=["週起始日", "管道", "使用者"])
    d["使用者"] = d["使用者"].astype(int)
    d["管道"] = d["channel"].map(_GA4_CHANNEL_BUCKET).fillna("直接/未知")
    d["週起始日"] = d["yearWeek"].apply(_yearweek_to_sunday)
    return d.groupby(["週起始日", "管道"])["使用者"].sum().reset_index()


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

    # 排除「補款專用」「更名手續費」等非真實航次/訂單項目，不計入任何頁面統計
    df = df[~df["bnb_name"].astype(str).str.contains("補款|更名手續費", na=False)].copy()

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
    name = str(row.get("bnb_name", ""))
    # 1) 名稱明確標示國外登船 → 飛航（即使母港船隊的船做國外移航也算）
    if _FOREIGN_EMBARK_RE.search(name):
        return "飛航郵輪"
    # 2) 名稱明確從台灣港出發 → 母港
    if _TW_DEPART_RE.search(name):
        return "母港出發"
    # 3) 其他泛用登船字眼（非台灣）→ 飛航
    if _GENERIC_EMBARK_RE.search(name):
        return "飛航郵輪"
    # 4) 移航航次（基隆出發者已在 2 歸母港）：其餘從國外出發 → 飛航
    if "移航" in name:
        return "飛航郵輪"
    # 5) 名稱未標港口：用母港船隊船名補判
    if any(s in name for s in _TAIWAN_FLEET_SHIPS):
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


# resample 頻率對應：
#  M → ME（新版 pandas 月底頻率代碼）
#  W → W-SAT（以週六為週尾，使一週為週日～週六，與儀表板「本週」定義一致）
_RESAMPLE_FREQ = {"M": "ME", "W": "W-SAT"}


def _resample_freq(freq: str) -> str:
    return _RESAMPLE_FREQ.get(freq, freq)


def gmv_ohlc(df: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    """把每日 GMV 依週期(freq)彙整成 K 線用的開高低收：
    開=期間首日GMV、收=末日GMV、高/低=期間內單日GMV最大/最小。"""
    daily = df.groupby(df["order_date"].dt.normalize())["twd_amount"].sum()
    daily.index = pd.DatetimeIndex(daily.index)
    g = daily.resample(_resample_freq(freq))
    out = pd.DataFrame({
        "open":  g.first(),
        "high":  g.max(),
        "low":   g.min(),
        "close": g.last(),
    }).dropna().reset_index()
    return out.rename(columns={out.columns[0]: "日期"})


def revenue_trend(df: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    return (df.set_index("order_date")
              .resample(_resample_freq(freq))["twd_amount"]
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
        return "MSC"
    if "msc" in n or "地中海郵輪" in str(name):
        return "MSC"
    if "歌詩達" in n or "costa" in n:
        return "歌詩達"
    if "迪士尼" in n or "disney" in n:
        return "迪士尼"
    if "公主遊輪" in n or "princess" in n:
        return "公主遊輪"
    if "星夢" in n or "genting dream" in n or "雲頂夢" in n:
        return "星夢郵輪"
    if ("挪威" in n or "ncl" in n or "norwegian" in n
            or "美國之傲" in str(name) or "pride of america" in n):
        return "挪威郵輪"
    if "皇后" in n or "cunard" in n:
        return "皇后郵輪"
    if "三井" in n or "富士" in n:
        return "三井"
    if "名人" in str(name) or "celebrity" in n:
        return "名人郵輪"
    if "皇家加勒比" in str(name) or "royal caribbean" in n:
        return "皇家加勒比"
    return "其他郵輪"


# 母港郵輪船隊固定為這幾艘：品牌關鍵字 → 標準船名
_HOMEPORT_FLEET = [
    (("三井", "富士"),                  "海洋富士號"),
    (("msc", "地中海"),                 "地中海榮耀號"),
    (("歌詩達", "costa"),               "莎倫娜號"),
    (("麗星", "探索", "star cruises"),  "探索星號"),
]


def _homeport_ship(name: str) -> str:
    """母港郵輪：依品牌關鍵字對應到固定船名（雜項命名一併歸位）。"""
    n = str(name).lower()
    suffix = "（移航）" if "移航" in str(name) else ""
    for keywords, ship in _HOMEPORT_FLEET:
        if any(kw in n for kw in keywords):
            return ship + suffix
    # 非母港船隊、但從台灣登船的航次（如挪威太陽號）→ 標示（台灣登船）
    return _cruise_ship(name) + "（台灣登船）"


_SHIP_RE = re.compile(r"([一-鿿A-Za-z]+號)")


# 英文船名（名稱無「號」字）的特例對應
_SHIP_ALIASES = {
    "xcel": "名人極上號",
}


def _cruise_ship(name: str) -> str:
    """從商品名稱萃取船名（XX號），並清理黏在前面的品牌字，讓同船的不同命名能合併。"""
    low = str(name).lower()
    for kw, ship in _SHIP_ALIASES.items():
        if kw in low:
            return ship
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
    ship = ship or "（無船名）"
    if "移航" in str(name):  # 移航航次獨立標示
        ship += "（移航）"
    return ship


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


# GIT 地區：column_switch_3 不可靠（多數錯標 Taiwan），改從商品名萃取目的地。
# 依序比對，先中到者為準（日本拆子地區，其餘以國家/區域）。
_GIT_REGIONS = [
    ("北海道",   ["北海道", "函館", "小樽", "富良野", "美瑛", "知床", "釧路", "二世谷",
                "洞爺湖", "旭川", "札幌", "道東", "定山溪"]),
    ("沖繩",     ["沖繩", "古宇利", "石垣", "宮古", "瀨長", "美之海", "海博館", "萬座毛", "玉泉洞"]),
    ("東北",     ["東北", "銀山溫泉", "奧入瀨", "角館", "猊鼻溪", "藏王", "岩手", "花卷",
                "睡魔", "秋田", "青森", "仙台"]),
    ("北陸",     ["立山黑部", "北陸", "富山", "合掌村", "高山", "兼六園", "白川鄉", "上高地",
                "飛驒", "金澤", "黑部", "犬山", "新潟", "佐渡"]),
    ("九州",     ["九州", "福岡", "由布院", "湯布院", "熊本", "佐賀", "柳川", "高千穗",
                "豪斯登堡", "別府", "鹿兒島", "長崎", "宮崎", "萌熊", "阿蘇"]),
    ("四國",     ["四國", "小豆島", "道後", "大步危", "金刀比羅", "松山", "高知", "德島",
                "香川", "烏龍麵"]),
    ("山陰山陽", ["山陰", "山陽", "出雲", "鳥取", "宮島", "倉敷", "松江", "足立美術館", "玉造"]),
    ("關西",     ["京阪", "關西", "大阪", "京都", "奈良", "神戶", "清水寺", "嵐山", "天橋立",
                "和歌山", "六甲", "宇治", "伊根", "勝尾寺"]),
    ("關東",     ["東京", "橫濱", "箱根", "輕井澤", "富士", "迪士尼", "日光", "鎌倉",
                "河口湖", "靜岡", "御殿場", "忍野"]),
    ("韓國",     ["濟州", "首爾", "韓", "釜山", "江原", "釜蔚", "釜邱"]),
    ("土耳其",   ["土耳其", "卡帕多奇亞", "棉堡", "番紅花城", "安塔利亞", "木馬", "布爾薩"]),
    ("歐洲",     ["奧捷", "捷克", "維也納", "布拉格", "布達佩斯", "匈", "北歐", "挪威", "西葡",
                "巴塞隆納", "義大利", "地中海", "梅爾克", "歐洲", "西班牙", "葡萄牙", "希臘",
                "瑞士", "法國", "荷蘭", "多瑙河", "哈修塔特", "庫倫洛夫", "薩爾斯堡", "龐貝",
                "馬賽", "冰島", "藍湖", "巴黎", "比利時", "英荷", "麗池"]),
    ("越南",     ["越南", "河內", "峴港", "富國島", "下龍灣", "會安", "巴拿山", "胡志明",
                "芽莊", "陸龍灣", "北越"]),
    ("泰國",     ["泰國", "曼谷", "普吉", "清邁", "芭達雅", "華欣", "泰獅", "泰航", "泰北",
                "金三角", "蘭納"]),
    ("新馬",     ["新加坡", "聖淘沙", "新馬", "金沙", "馬來", "吉隆坡", "黑風洞"]),
    ("印尼",     ["峇里", "巴里", "烏布", "印尼", "海神廟"]),
    ("美國",     ["洛杉磯", "聖塔莫尼卡", "棕櫚泉", "美國", "加州", "拉斯維加斯"]),
    ("澳洲",     ["澳洲", "墨爾本", "大洋路", "雪梨", "黃金海岸", "神仙企鵝", "莫瑞頓"]),
    ("杜拜",     ["杜拜", "阿布達比", "哈里發", "酋長"]),
    ("埃及",     ["埃及", "金字塔", "尼羅河", "阿布辛貝"]),
]


def _git_region(name: str) -> str:
    n = str(name)
    for region, keywords in _GIT_REGIONS:
        if any(kw in n for kw in keywords):
            return region
    return "其他"


# 郵輪航線停靠點/目的地關鍵字（供 SEO 內容方向）
_CRUISE_DESTS = [
    "那霸", "石垣", "宮古", "沖繩", "鹿兒島", "釜山", "佐世保", "福岡", "濟州", "熊本",
    "長崎", "麗水", "高知", "大阪", "東京", "橫濱", "靜岡", "神戶", "清水", "京都",
    "廣島", "青森", "新加坡", "普吉", "檳城", "馬六甲", "吉隆坡", "蘇梅", "熱浪島",
    "蘭卡威", "峇里", "龍目", "阿拉斯加", "冰河灣", "溫哥華", "西雅圖", "舊金山",
    "紐西蘭", "加勒比", "地中海", "巴拿馬", "夏威夷", "北海道", "挪威", "丹麥",
    "瑞典", "冰島", "義大利", "西班牙", "法國", "希臘", "土耳其", "越南", "公海",
]


def cruise_destination_heat(df: pd.DataFrame, top: int = 20) -> pd.DataFrame:
    """郵輪航線各目的地的提及訂單數與營收（一筆航次含多個停靠點會分別計入）。"""
    c = df[df["product_line"] == "Cruise"]
    rows = []
    for name, amt in zip(c["bnb_name"].astype(str), c["twd_amount"]):
        # 去掉品牌字「地中海郵輪」，避免 MSC 母港船被誤判成「地中海」目的地
        clean = name.replace("地中海郵輪", "")
        for d in _CRUISE_DESTS:
            if d in clean:
                rows.append((d, amt))
    if not rows:
        return pd.DataFrame(columns=["目的地", "訂單數", "營收"])
    t = pd.DataFrame(rows, columns=["目的地", "營收"])
    return (t.groupby("目的地")
             .agg(訂單數=("營收", "size"), 營收=("營收", "sum"))
             .sort_values("訂單數", ascending=False)
             .reset_index()
             .head(top))


def git_country_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """GIT 依目的地地區（從商品名萃取）的營收與訂單數。"""
    git = df[df["product_line"] == "GIT"].copy()
    git["地區"] = git["bnb_name"].apply(_git_region)
    return (git.groupby("地區")
               .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
               .sort_values("營收", ascending=False)
               .reset_index())


def accommodation_region_distribution(df: pd.DataFrame, product_line: str) -> pd.DataFrame:
    sub = df[df["product_line"] == product_line].copy()
    return (sub.groupby("bnb_city")
               .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
               .sort_values("營收", ascending=False)
               .reset_index()
               .head(20))


# 台灣住宿城市（英文）→ 地圖縣市名（對應 taiwan_counties.geojson 的 COUNTYNAME）
_TW_CITY_ZH = {
    "Taipei City": "台北市", "New Taipei City": "新北市", "Taoyuan City": "桃園縣",
    "Taichung City": "台中市", "Tainan City": "台南市", "Kaohsiung City": "高雄市",
    "Keelung City": "基隆市", "Hsinchu City": "新竹市", "Hsinchu County": "新竹縣",
    "Miaoli County": "苗栗縣", "Changhua County": "彰化縣", "Nantou County": "南投縣",
    "Yunlin County": "雲林縣", "Chiayi City": "嘉義市", "Chiayi County": "嘉義縣",
    "Pingtung County": "屏東縣", "Yilan County": "宜蘭縣", "Hualien County": "花蓮縣",
    "Taitung County": "台東縣", "Penghu County": "澎湖縣", "Kinmen County": "金門縣",
    "Matsu": "連江縣",
}


def tw_city_geo(df: pd.DataFrame) -> pd.DataFrame:
    """台灣住宿各縣市的訂單數、營收（縣市名轉為地圖用中文）。"""
    tw = df[df["product_line"] == "TW"].copy()
    tw["縣市"] = tw["bnb_city"].map(_TW_CITY_ZH)
    tw = tw.dropna(subset=["縣市"])
    return (tw.groupby("縣市")
              .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
              .reset_index())


def checkin_monthly(df: pd.DataFrame, product_line: str) -> pd.DataFrame:
    sub = df[df["product_line"] == product_line].copy()
    sub["check_in_month"] = sub["check_in"].dt.to_period("M").astype(str)
    return (sub.groupby("check_in_month")
               .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
               .reset_index())


def _channel_col(df: pd.DataFrame) -> pd.Series:
    return df["affiliate_id"].apply(
        lambda x: x if str(x).strip() not in ("", "-", "0", "nan") else "直接/未知"
    )


def marketing_channel(df: pd.DataFrame) -> pd.DataFrame:
    ch = df.copy()
    ch["channel"] = _channel_col(ch)
    return (ch.groupby(["channel", "product_line"])
              .agg(訂單數=("order_id", "count"), 營收=("twd_amount", "sum"))
              .reset_index()
              .sort_values("營收", ascending=False))


def channel_summary(df: pd.DataFrame) -> pd.DataFrame:
    """各管道別的訂單數、GMV、AOV（單一期間）。"""
    ch = df.copy()
    ch["channel"] = _channel_col(ch)
    g = (ch.groupby("channel")
           .agg(訂單數=("order_id", "count"), GMV=("twd_amount", "sum"))
           .reset_index())
    g["AOV"] = (g["GMV"] / g["訂單數"]).fillna(0)
    return g
