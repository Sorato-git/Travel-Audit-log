import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid

# --- 1. 設定 & 接続 ---
import json

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_NAME = "TravelAuditDB"

# ページ設定
st.set_page_config(page_title="Travel Auditor", layout="centered")

@st.cache_resource
def connect_db():
    try:
        # Streamlit CloudのSecretsが存在するか確認
        if "gcp_service_account" in st.secrets:
            # クラウド環境: Secretsから辞書として読み込む
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        else:
            # ローカル環境: JSONファイルから読み込む
            creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", SCOPE)
            
        client = gspread.authorize(creds)
        sheet = client.open(SPREADSHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"DB接続エラー: {e}")
        st.stop()

sheet = connect_db()
worksheet_trips = sheet.worksheet("trips")
worksheet_expenses = sheet.worksheet("expenses")

# --- 2. 関数定義 ---

def load_data(worksheet):
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

def add_trip(name, start, end):
    t_id = str(uuid.uuid4())[:8] # 短縮ID
    new_row = [t_id, name, str(start), str(end), "Active"]
    worksheet_trips.append_row(new_row)
    st.success(f"旅行 '{name}' を登録しました。")

def add_expense(trip_id, category, item, amount, sat, detail):
    e_id = str(uuid.uuid4())
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # ヘッダー順: entry_id, trip_id, timestamp, category, item_name, amount, satisfaction, detail
    new_row = [e_id, trip_id, ts, category, item, amount, sat, detail]
    worksheet_expenses.append_row(new_row)
    st.success("支出を記録しました。")

# --- 3. UI構築 ---

st.title("Travel Audit Log")

# サイドバーナビゲーション
menu = ["支出記録 (Entry)", "旅行登録 (New Trip)", "台帳閲覧 (Audit)"]
choice = st.sidebar.radio("Menu", menu)

# --- A. 旅行登録 ---
if choice == "旅行登録 (New Trip)":
    st.header("新規プロジェクト作成")
    with st.form("trip_form"):
        t_name = st.text_input("旅行名 (例: 2024冬 北海道)")
        col1, col2 = st.columns(2)
        t_start = col1.date_input("開始日")
        t_end = col2.date_input("終了日")
        submitted = st.form_submit_button("登録実行")
        
        if submitted and t_name:
            add_trip(t_name, t_start, t_end)

# --- B. 支出記録 ---
elif choice == "支出記録 (Entry)":
    st.header("支出データの入力")
    
    # 旅行リストの取得（ドロップダウン用）
    df_trips = load_data(worksheet_trips)
    if df_trips.empty:
        st.warning("まずは「旅行登録」から旅行を作成してください。")
    else:
        # Activeな旅行のみを表示するのが理想だが、一旦全て表示
        trip_options = df_trips.set_index('trip_id')['trip_name'].to_dict()
        selected_trip_id = st.selectbox("対象旅行を選択", list(trip_options.keys()), format_func=lambda x: trip_options[x])

        with st.form("expense_form"):
            # 入力フィールド
            item = st.text_input("品目・店名 (Item Name)")
            
            col1, col2 = st.columns(2)
            amount = col1.number_input("金額 (JPY)", min_value=0, step=100)
            category = col2.selectbox("カテゴリ", ["食事", "宿泊", "交通", "娯楽/体験", "雑費/その他"])
            
            st.markdown("---")
            st.caption("満足度評価 (監査)")
            sat = st.slider("満足度 (1:最低 - 10:最高)", 1, 10, 5)
            detail = st.text_area("詳細・備考 (なぜその評価か？)", height=100)
            
            submitted = st.form_submit_button("記録・監査完了")
            
            if submitted:
                if item and amount > 0:
                    add_expense(selected_trip_id, category, item, amount, sat, detail)
                else:
                    st.error("品目と金額は必須です。")

# --- C. 台帳閲覧 ---
elif choice == "台帳閲覧 (Audit)":
    st.header("データ監査")
    
    df_trips = load_data(worksheet_trips)
    if df_trips.empty:
        st.info("データがありません。")
    else:
        # 旅行選択フィルタ
        trip_options = df_trips.set_index('trip_id')['trip_name'].to_dict()
        # 全体表示オプションも追加
        filter_opts = ["ALL"] + list(trip_options.keys())
        target_trip = st.selectbox("監査対象を選択", filter_opts, format_func=lambda x: trip_options.get(x, "全データ表示"))
        
        df_ex = load_data(worksheet_expenses)
        
        if not df_ex.empty:
            if target_trip != "ALL":
                df_ex = df_ex[df_ex['trip_id'] == target_trip]
            
            # 必要なカラムだけ整理して表示
            display_cols = ['timestamp', 'category', 'item_name', 'amount', 'satisfaction', 'detail']
            
            # スマホで見やすいように、重要な情報を先に
            st.dataframe(
                df_ex[display_cols].sort_values(by='timestamp', ascending=False),
                use_container_width=True,
                hide_index=True
            )
            
            # 簡易集計 (分析ではなく、現状把握としての合計)
            total_cost = df_ex['amount'].sum()
            st.metric("表示範囲の支出合計", f"¥{total_cost:,}")
        else:
            st.info("支出データがまだありません。")