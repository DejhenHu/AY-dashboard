# AsiaYo 業績儀表板

## 部署前準備

### 步驟一：取得 Google Service Account 金鑰

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 建立一個新專案（或選擇現有專案）
3. 啟用 **Google Sheets API**（搜尋 "Sheets API" → 啟用）
4. 建立服務帳戶：IAM → 服務帳戶 → 建立服務帳戶（任意名稱）
5. 在服務帳戶下建立金鑰：金鑰 → 新增金鑰 → JSON → 下載
6. **把 Google Sheet 分享給這個服務帳戶的 email**（只需「檢視者」權限）

### 步驟二：填入 secrets.toml

開啟 `.streamlit/secrets.toml`，把下載的 JSON 金鑰內容對應填入。

### 步驟三：取得 Claude API Key

前往 [Anthropic Console](https://console.anthropic.com/) 取得 API key，填入 `secrets.toml`。

### 步驟四：本機測試

```bash
cd asiaYo-dashboard
pip install -r requirements.txt
streamlit run app.py
```

### 步驟五：部署到 Streamlit Cloud

1. 把整個資料夾推上 GitHub（**確認 `.gitignore` 有擋住 secrets.toml**）
2. 前往 [share.streamlit.io](https://share.streamlit.io) → New app → 選擇你的 repo
3. 在 Streamlit Cloud 的 **Secrets** 設定頁貼上 `secrets.toml` 的內容
4. 部署完成後分享連結給同事

## Google Sheet 欄位對應

程式預設 Google Sheet 的欄位順序為：

| 欄位 | 名稱 |
|------|------|
| A | order_date |
| B | order_id |
| C | booking_status |
| D | platform |
| E | bnb_city |
| F | bnb_id |
| G | bnb_name |
| H | bnb_type |
| I | check_in |
| J | check_out |
| K | tags |
| L | affiliate_id |
| M | coupon |
| N | column_switch_3 |
| O | guests |
| P | adult |
| Q | child |
| R | nights |
| S | rooms |
| T | twd_amount |

> 如果你的 Google Sheet 第一列的標題名稱不同，請在 `data_processor.py` 的 `load_data()` 函式中調整 `expected_headers` 清單。
