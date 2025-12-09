import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid
import time

# --- 1. 設定 & 接続 ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_NAME = "TravelAuditDB"

st.set_page_config(page_title="Travel Auditor v2", layout="centered")

@st.cache_resource
def connect_db():
    try:
        # SecretsまたはローカルJSONから接続
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        else:
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

# --- 2. ロジック関数 ---

def load_data(worksheet):
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

def add_trip(name, start, end, budget):
    t_id = str(uuid.uuid4())[:8]
    # 列順序: trip_id, trip_name, start_date, end_date, status, total_budget
    new_row = [t_id, name, str(start), str(end), "Active", budget]
    worksheet_trips.append_row(new_row)
    st.toast(f"プロジェクト '{name}' を開始しました。")
    time.sleep(1)
    st.rerun()

def add_expense(trip_id, category, item, amount, sat, detail):
    e_id = str(uuid.uuid4())
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 列順序: entry_id, trip_id, timestamp, category, item_name, amount, satisfaction, detail
    new_row = [e_id, trip_id, ts, category, item, amount, sat, detail]
    worksheet_expenses.append_row(new_row)
    st.toast("支出を監査ログに記録しました。")
    time.sleep(1)
    st.rerun()

def delete_row(worksheet, id_col_val, id_col_index=1):
    try:
        cell = worksheet.find(id_col_val, in_column=id_col_index)
        worksheet.delete_rows(cell.row)
        st.success("削除完了")
        time.sleep(1)
        st.rerun()
    except gspread.exceptions.CellNotFound:
        st.error("データが見つかりませんでした。")

def update_trip_status(trip_id, new_status):
    try:
        cell = worksheet_trips.find(trip_id, in_column=1) # A列(trip_id)を検索
        # statusはE列(5番目)にあると仮定
        worksheet_trips.update_cell(cell.row, 5, new_status)
        st.toast(f"ステータスを {new_status} に更新しました。")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"更新エラー: {e}")

# --- 3. UI構築 ---

st.title("🛡️ Travel Audit v2")

# メニュー構成
menu = ["支出記録 (Entry)", "台帳閲覧 (Audit)", "管理・修正 (Admin)"]
choice = st.sidebar.radio("Menu", menu)

# --- A. 支出記録 (Entry) ---
if choice == "支出記録 (Entry)":
    st.header("支出データの入力")
    
    df_trips = load_data(worksheet_trips)
    if df_trips.empty:
        st.warning("有効な旅行プロジェクトがありません。「管理・修正」から作成してください。")
    else:
        # Activeな旅行のみフィルタリング
        active_trips = df_trips[df_trips['status'] == 'Active']
        
        if active_trips.empty:
            st.warning("現在進行中(Active)の旅行がありません。")
        else:
            trip_options = active_trips.set_index('trip_id')['trip_name'].to_dict()
            selected_trip_id = st.selectbox("対象旅行", list(trip_options.keys()), format_func=lambda x: trip_options[x])

            with st.form("expense_form"):
                item = st.text_input("品目・店名")
                col1, col2 = st.columns(2)
                amount = col1.number_input("金額 (JPY)", min_value=0, step=100)
                category = col2.selectbox("カテゴリ", ["食事", "宿泊", "交通", "娯楽/体験", "雑費"])
                
                st.markdown("---")
                sat = st.slider("満足度 (ROI監査)", 1, 10, 5)
                detail = st.text_area("詳細・備考", height=80)
                
                if st.form_submit_button("記録実行"):
                    if item and amount >= 0:
                        add_expense(selected_trip_id, category, item, amount, sat, detail)
                    else:
                        st.error("入力不備があります。")

# --- B. 台帳閲覧 (Audit) ---
elif choice == "台帳閲覧 (Audit)":
    st.header("データ監査・分析")
    
    df_trips = load_data(worksheet_trips)
    if not df_trips.empty:
        trip_options = df_trips.set_index('trip_id')['trip_name'].to_dict()
        filter_opts = ["ALL"] + list(trip_options.keys())
        target_trip = st.selectbox("フィルタ", filter_opts, format_func=lambda x: trip_options.get(x, "全プロジェクト"))
        
        df_ex = load_data(worksheet_expenses)
        if not df_ex.empty:
            # フィルタリング
            if target_trip != "ALL":
                df_ex = df_ex[df_ex['trip_id'] == target_trip]
                # 予算情報の表示
                budget = df_trips[df_trips['trip_id'] == target_trip]['total_budget'].iloc[0]
                status = df_trips[df_trips['trip_id'] == target_trip]['status'].iloc[0]
                
                total_spent = df_ex['amount'].sum()
                if budget:
                    remaining = int(budget) - total_spent
                    prog = min(total_spent / int(budget), 1.0)
                    st.progress(prog, text=f"予算消化率: {int(prog*100)}%")
                    st.caption(f"予算: ¥{budget:,} | 支出: ¥{total_spent:,} | 残金: ¥{remaining:,} | Status: {status}")
            
            # データ表示
            display_cols = ['timestamp', 'category', 'item_name', 'amount', 'satisfaction', 'detail', 'entry_id']
            # 不要な列が含まれている場合のガード
            display_cols = [c for c in display_cols if c in df_ex.columns]
            
            st.dataframe(
                df_ex[display_cols].sort_values(by='timestamp', ascending=False),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("支出データなし")

# --- C. 管理・修正 (Admin) ---
elif choice == "管理・修正 (Admin)":
    st.header("プロジェクト管理センター")
    
    tab1, tab2, tab3 = st.tabs(["新規旅行登録", "ステータス変更", "データ削除"])
    
    # 1. 新規登録
    with tab1:
        with st.form("new_trip_form"):
            st.subheader("新規プロジェクト")
            t_name = st.text_input("旅行名")
            t_budget = st.number_input("総予算 (JPY)", min_value=0, step=10000)
            c1, c2 = st.columns(2)
            t_start = c1.date_input("開始日")
            t_end = c2.date_input("終了日")
            if st.form_submit_button("登録"):
                add_trip(t_name, t_start, t_end, t_budget)

    # 2. ステータス変更
    with tab2:
        st.subheader("旅行ステータス管理")
        df_trips = load_data(worksheet_trips)
        if not df_trips.empty:
            t_dict = df_trips.set_index('trip_id')[['trip_name', 'status']].T.to_dict()
            target_t_id = st.selectbox("旅行を選択", list(t_dict.keys()), format_func=lambda x: f"{t_dict[x]['trip_name']} ({t_dict[x]['status']})")
            
            new_status = st.radio("状態変更", ["Active", "Completed", "Cancelled"], horizontal=True)
            if st.button("ステータス更新"):
                update_trip_status(target_t_id, new_status)

    # 3. 削除機能
    with tab3:
        st.subheader("危険区域: データ削除")
        st.warning("削除は取り消せません。慎重に操作してください。")
        
        del_type = st.radio("削除対象", ["支出データ (1件)", "旅行プロジェクト (全体)"], horizontal=True)
        
        if del_type == "支出データ (1件)":
            expense_id = st.text_input("削除する entry_id を入力")
            st.caption("※台帳閲覧タブで entry_id を確認し、コピーしてください")
            if st.button("支出削除実行"):
                delete_row(worksheet_expenses, expense_id, id_col_index=1)
                
        elif del_type == "旅行プロジェクト (全体)":
            df_trips = load_data(worksheet_trips)
            if not df_trips.empty:
                del_trip_id = st.selectbox("削除する旅行", df_trips['trip_id'].tolist(), format_func=lambda x: df_trips[df_trips['trip_id'] == x]['trip_name'].values[0])
                if st.button("旅行削除実行"):
                    delete_row(worksheet_trips, del_trip_id, id_col_index=1)
