import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid
import time

# --- 設定 & 定数 ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_NAME = "TravelAuditDB"

# カラーパレット
COLOR_RED = "#FF4B4B"
COLOR_BLUE = "#4B4BFF"
COLOR_GREEN = "#4BFF4B"
COLOR_CYAN = "#008B8B"
COLOR_GOLD = "#FFD700"
COLOR_MAGENTA = "#FF00FF"
COLOR_TOMATO = "#ff6347"
COLOR_GREY = "#7f8c8d"

CATEGORY_COLOR_MAP = {
    "食事": COLOR_RED,
    "宿泊": COLOR_BLUE,
    "交通": COLOR_GREEN,
    "娯楽/体験": COLOR_CYAN,
    "雑費": COLOR_GOLD
}

# --- ヘルパー関数 ---

def execute_with_retry(func, *args, max_retries=3, **kwargs):
    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            if i == max_retries - 1:
                st.error(f"Google APIエラー (Wait & Retry Failed): {e}")
                st.stop()
            time.sleep(1 + i)
        except Exception as e:
            st.error(f"予期せぬエラー: {e}")
            st.stop()

@st.cache_resource(ttl=600)
def connect_db():
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SPREADSHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"データベース接続失敗: {e}")
        st.stop()

def get_worksheet_object(sheet_name):
    sheet = connect_db()
    try:
        return sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"ワークシート '{sheet_name}' が見つかりません。")
        st.stop()

# --- データ操作 (CRUD) ---

@st.cache_data(ttl=300)
def load_cached_data(sheet_name):
    ws = get_worksheet_object(sheet_name)
    try:
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except gspread.exceptions.APIError:
        time.sleep(2)
        data = ws.get_all_records()
        return pd.DataFrame(data)

def clear_all_caches():
    load_cached_data.clear()

def add_trip(name, start, end, budget, detail):
    ws = get_worksheet_object("trips")
    t_id = str(uuid.uuid4())[:8]
    new_row = [t_id, name, str(start), str(end), "Planning", budget, detail]
    execute_with_retry(ws.append_row, new_row)
    clear_all_caches()
    st.toast(f"プロジェクト '{name}' を作成しました。")
    time.sleep(1)
    st.rerun()

def update_trip_info(trip_id, name, start, end, budget, status, detail):
    ws = get_worksheet_object("trips")
    try:
        cell = ws.find(trip_id, in_column=1)
        row_num = cell.row
        ws.update_cell(row_num, 2, name)
        ws.update_cell(row_num, 3, str(start))
        ws.update_cell(row_num, 4, str(end))
        ws.update_cell(row_num, 5, status)
        ws.update_cell(row_num, 6, budget)
        ws.update_cell(row_num, 7, detail)
        clear_all_caches()
        st.success(f"旅行 '{name}' の情報を更新しました。")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"更新エラー: {e}")

def add_expense(trip_id, category, item, amount, sat, detail, exp_date, is_waste):
    ws = get_worksheet_object("expenses")
    e_id = str(uuid.uuid4())
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_str = str(exp_date) if exp_date else datetime.now().strftime("%Y-%m-%d")
    waste_str = "TRUE" if is_waste else "FALSE"
    
    new_row = [e_id, trip_id, ts, category, item, amount, sat, detail, date_str, waste_str]
    execute_with_retry(ws.append_row, new_row)
    clear_all_caches()
    st.toast("支出を監査ログに記録しました。")
    time.sleep(1)
    st.rerun()

def update_expense(entry_id, category, item, amount, sat, detail, exp_date, is_waste):
    ws = get_worksheet_object("expenses")
    try:
        cell = ws.find(entry_id, in_column=1)
        row_num = cell.row
        date_str = str(exp_date)
        waste_str = "TRUE" if is_waste else "FALSE"
        
        ws.update_cell(row_num, 4, category)
        ws.update_cell(row_num, 5, item)
        ws.update_cell(row_num, 6, amount)
        ws.update_cell(row_num, 7, sat)
        ws.update_cell(row_num, 8, detail)
        ws.update_cell(row_num, 9, date_str)
        ws.update_cell(row_num, 10, waste_str)
        
        clear_all_caches()
        st.success("データの修正が完了しました。")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"更新エラー: {e}")

def delete_row_simple(worksheet_name, id_col_val, id_col_index=1):
    ws = get_worksheet_object(worksheet_name)
    try:
        cell = ws.find(id_col_val, in_column=id_col_index)
        if hasattr(ws, 'delete_rows'): ws.delete_rows(cell.row)
        else: ws.delete_row(cell.row)
        clear_all_caches()
        st.success("削除完了")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"削除エラー: {e}")

def delete_trip_cascade(trip_id, trip_name):
    ws_exp = get_worksheet_object("expenses")
    ws_trip = get_worksheet_object("trips")
    status_box = st.empty()
    status_box.info("⚠️ 関連データの削除処理を開始します...")
    time.sleep(2)
    try:
        all_expenses = ws_exp.get_all_records()
        if all_expenses:
            df = pd.DataFrame(all_expenses)
            if 'trip_id' in df.columns:
                remaining_df = df[df['trip_id'] != trip_id]
                ws_exp.clear()
                header = ["entry_id", "trip_id", "timestamp", "category", "item_name", "amount", "satisfaction", "detail", "expense_date", "is_waste"]
                ws_exp.append_row(header)
                if not remaining_df.empty:
                    for col in header:
                        if col not in remaining_df.columns: remaining_df[col] = ""
                    data_to_write = remaining_df[header].values.tolist()
                    ws_exp.append_rows(data_to_write)
        
        cell = ws_trip.find(trip_id, in_column=1)
        if hasattr(ws_trip, 'delete_rows'): ws_trip.delete_rows(cell.row)
        else: ws_trip.delete_row(cell.row)
        clear_all_caches()
        status_box.success(f"旅行「{trip_name}」と全関連データの完全消去が完了しました。")
        time.sleep(2)
        st.rerun()
    except Exception as e:
        st.error(f"完全削除中にエラーが発生しました: {e}")
