import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date
import uuid
import time
import plotly.graph_objects as go
import plotly.express as px

# --- 1. 設定 & 接続 (堅牢化) ---
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

CATEGORY_COLOR_MAP = {
    "食事": COLOR_RED,
    "宿泊": COLOR_BLUE,
    "交通": COLOR_GREEN,
    "娯楽/体験": COLOR_CYAN,
    "雑費": COLOR_GOLD
}

st.set_page_config(page_title="Travel Audit Log", layout="wide")

# リトライロジック
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

# DB接続のキャッシュ
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

# ワークシート取得ヘルパー
def get_worksheet_object(sheet_name):
    sheet = connect_db()
    try:
        return sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"ワークシート '{sheet_name}' が見つかりません。")
        st.stop()

# --- 2. データ読み込み (Data Cache) ---

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
    """書き込みを行った後にキャッシュを破棄する"""
    load_cached_data.clear()

# --- 3. 書き込みロジック (キャッシュ破棄付き) ---

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
        if hasattr(ws, 'delete_rows'):
            ws.delete_rows(cell.row)
        else:
            ws.delete_row(cell.row)
        
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
    try:
        all_expenses = ws_exp.get_all_records()
        
        if all_expenses:
            df = pd.DataFrame(all_expenses)
            if 'trip_id' in df.columns:
                remaining_df = df[df['trip_id'] != trip_id]
                
                # シートクリア & 再構築
                ws_exp.clear()
                header = ["entry_id", "trip_id", "timestamp", "category", "item_name", "amount", "satisfaction", "detail", "expense_date", "is_waste"]
                ws_exp.append_row(header)
                
                if not remaining_df.empty:
                    for col in header:
                        if col not in remaining_df.columns:
                            remaining_df[col] = ""
                    data_to_write = remaining_df[header].values.tolist()
                    ws_exp.append_rows(data_to_write)
        
        cell = ws_trip.find(trip_id, in_column=1)
        if hasattr(ws_trip, 'delete_rows'):
            ws_trip.delete_rows(cell.row)
        else:
            ws_trip.delete_row(cell.row)
            
        clear_all_caches()
        status_box.success(f"旅行「{trip_name}」と全関連データの完全消去が完了しました。")
        time.sleep(2)
        st.rerun()
    except Exception as e:
        st.error(f"完全削除中にエラーが発生しました: {e}")

# --- スタイリング関数 ---
def highlight_audit_rows(row):
    is_waste = str(row.get('is_waste', '')).upper() == 'TRUE'
    try:
        sat = int(row.get('satisfaction', 10))
    except:
        sat = 10
        
    if is_waste:
        return ['background-color: #FFD700; color: black'] * len(row)
    elif sat == 0:
        return ['background-color: #7f8c8d; color: white'] * len(row)
    elif sat <= 3:
        return ['background-color: #ff6347; color: white'] * len(row)
    return [''] * len(row)

# --- 3. UI構築 ---

st.title("Travel Audit Log")

menu = ["支出記録 (Entry)", "台帳閲覧 (Audit)", "管理・修正 (Admin)"]
choice = st.sidebar.radio("Menu", menu)

# --- A. 支出記録 ---
if choice == "支出記録 (Entry)":
    st.header("支出データの入力")
    df_trips = load_cached_data("trips")
    
    if df_trips.empty:
        st.warning("旅行プロジェクトがありません。")
    else:
        active_trips = df_trips[df_trips['status'].isin(['Active', 'Planning'])]
        if active_trips.empty:
            st.warning("進行中(Active)または計画中(Planning)の旅行がありません。")
        else:
            trip_options = active_trips.set_index('trip_id')['trip_name'].to_dict()
            # str()キャスト: selectboxのエラー防止
            selected_trip_id = st.selectbox("対象旅行", list(trip_options.keys()), format_func=lambda x: str(trip_options[x]))

            with st.form("expense_form"):
                exp_date = st.date_input("支出日 (未記入時は本日)", value=datetime.today())
                item = st.text_input("品目・店名")
                col1, col2 = st.columns(2)
                amount = col1.number_input("金額", min_value=0, step=100)
                category = col2.selectbox("カテゴリ", ["食事", "宿泊", "交通", "娯楽/体験", "雑費"])
                
                st.markdown("---")
                
                # --- 未来日付 or 手動未評価ロジック ---
                today = date.today()
                is_future = exp_date > today
                
                # 手動チェックボックス (未来日付ならデフォルトON)
                is_pending = st.checkbox("未評価 (Pending) として記録 - 後で採点する", value=is_future)
                
                if is_pending:
                    sat = 0
                    st.caption("※ 満足度は 0 (未評価) として記録されます。")
                else:
                    sat = st.slider("満足度 (ROI監査)", 1, 10, 5)
                
                is_waste = st.checkbox("浪費 (Avoidable Waste)")
                detail = st.text_area("詳細・備考", height=80)
                
                if st.form_submit_button("記録実行"):
                    if item and amount >= 0:
                        add_expense(selected_trip_id, category, item, amount, sat, detail, exp_date, is_waste)
                    else:
                        st.error("入力不備があります。")

# --- B. 台帳閲覧 ---
elif choice == "台帳閲覧 (Audit)":
    st.header("データ監査・分析")
    df_trips = load_cached_data("trips")
    
    if not df_trips.empty:
        trip_options = df_trips.set_index('trip_id')['trip_name'].to_dict()
        filter_opts = ["ALL"] + list(trip_options.keys())
        target_trip = st.selectbox("フィルタ", filter_opts, format_func=lambda x: str(trip_options.get(x, "全プロジェクト")))
        
        df_ex = load_cached_data("expenses")
        
        if not df_ex.empty:
            if 'expense_date' not in df_ex.columns: df_ex['expense_date'] = ""
            if 'is_waste' not in df_ex.columns: df_ex['is_waste'] = "FALSE"
            
            for idx, row in df_ex.iterrows():
                if str(row['expense_date']).strip() == "":
                    ts_val = str(row.get('timestamp', ''))
                    if ts_val:
                        try: df_ex.at[idx, 'expense_date'] = ts_val.split(" ")[0]
                        except: pass

            if target_trip != "ALL":
                df_ex = df_ex[df_ex['trip_id'] == target_trip]
                
                st.markdown("### 📊 支出分析")
                
                budget_row = df_trips[df_trips['trip_id'] == target_trip]
                budget_val = budget_row['total_budget'].iloc[0]
                budget = int(budget_val) if not budget_row.empty and budget_val else 1
                total_spent = int(df_ex['amount'].sum())
                
                waste_df = df_ex[df_ex['is_waste'].astype(str).str.upper() == "TRUE"]
                total_waste = int(waste_df['amount'].sum())
                
                kpi1, kpi2, kpi3 = st.columns(3)
                kpi1.metric("総支出", f"¥{total_spent:,}")
                kpi2.metric("予算残", f"¥{budget - total_spent:,}")
                kpi3.metric("総浪費額 (Waste)", f"¥{total_waste:,}", delta=-total_waste, delta_color="inverse")
                
                col_g1, col_g2 = st.columns(2)
                
                # 1. 予算消化バー
                with col_g1:
                    ratio = (total_spent / budget) * 100
                    bar_color = COLOR_RED if total_spent > budget else COLOR_GREEN
                    fig_budget = go.Figure()
                    fig_budget.add_trace(go.Bar(
                        x=[total_spent], y=[""], orientation='h', marker=dict(color=bar_color),
                        text=[f"{int(ratio)}%"], textposition='inside', insidetextanchor='middle',
                        textfont=dict(size=60, color='white', family="Arial Black")
                    ))
                    max_x = max(budget, total_spent) * 1.05
                    fig_budget.update_layout(
                        title="予算消化状況", xaxis=dict(range=[0, max_x], title=f"{total_spent:,}円 / {budget:,}円", tickfont=dict(size=14), title_font=dict(size=18)),
                        yaxis=dict(showticklabels=False), height=200, margin=dict(l=20, r=20, t=40, b=40)
                    )
                    fig_budget.add_vline(x=budget, line_width=3, line_dash="dash", line_color="white", annotation_text="Budget")
                    st.plotly_chart(fig_budget, use_container_width=True)

                # 2. カテゴリ別ドーナツ
                with col_g2:
                    if total_spent > 0:
                        cat_sum = df_ex.groupby('category')['amount'].sum().reset_index()
                        fixed_order = ["食事", "宿泊", "交通", "娯楽/体験", "雑費"]
                        cat_sum['category'] = pd.Categorical(cat_sum['category'], categories=fixed_order, ordered=True)
                        cat_sum = cat_sum.sort_values('category')
                        
                        cat_sum['percent'] = (cat_sum['amount'] / total_spent) * 100
                        cat_sum['label'] = cat_sum.apply(lambda x: f"{x['category']} ({x['percent']:.1f}%)", axis=1)
                        
                        chart_color_map = {}
                        for _, row in cat_sum.iterrows():
                            cat_name = str(row['category'])
                            label_name = row['label']
                            chart_color_map[label_name] = CATEGORY_COLOR_MAP.get(cat_name, "#808080")

                        fig_cat = px.pie(
                            cat_sum, values='amount', names='label', hole=0.6,
                            color='label', color_discrete_map=chart_color_map
                        )
                        fig_cat.update_traces(textinfo='none', sort=False, direction='clockwise')
                        fig_cat.update_layout(
                            title="カテゴリ別内訳", annotations=[dict(text=f"¥{total_spent:,}", x=0.5, y=0.5, font_size=24, showarrow=False, font_weight="bold")],
                            height=250, margin=dict(l=20, r=20, t=40, b=20), showlegend=True, legend=dict(font=dict(size=14))
                        )
                        st.plotly_chart(fig_cat, use_container_width=True)

            st.markdown("### 📝 支出明細")
            csv = df_ex.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="CSVエクスポート", data=csv,
                file_name=f'travel_audit_{datetime.now().strftime("%Y%m%d")}.csv', mime='text/csv'
            )

            display_cols = ['expense_date', 'category', 'item_name', 'amount', 'satisfaction', 'is_waste', 'detail', 'entry_id']
            valid_cols = [c for c in display_cols if c in df_ex.columns]
            sorted_df = df_ex[valid_cols].sort_values(by='expense_date', ascending=False)
            
            st.dataframe(
                sorted_df.style.apply(highlight_audit_rows, axis=1),
                use_container_width=True, hide_index=True
            )
        else:
            st.info("支出データなし")

# --- C. 管理・修正 ---
elif choice == "管理・修正 (Admin)":
    st.header("プロジェクト管理センター")
    tab1, tab2, tab3, tab4 = st.tabs(["新規旅行登録", "データ修正(Edit)", "旅行修正(Trips)", "データ削除"])
    
    with tab1:
        with st.form("new_trip_form"):
            t_name = st.text_input("旅行名")
            t_budget = st.number_input("総予算", min_value=0, step=10000)
            c1, c2 = st.columns(2)
            t_start = c1.date_input("開始日")
            t_end = c2.date_input("終了日")
            t_detail = st.text_area("詳細・メモ")
            if st.form_submit_button("登録"):
                add_trip(t_name, t_start, t_end, t_budget, t_detail)

    with tab2:
        st.subheader("既存データの修正")
        df_trips = load_cached_data("trips")
        df_ex = load_cached_data("expenses")
        if not df_trips.empty and not df_ex.empty:
            t_dict = df_trips.set_index('trip_id')['trip_name'].to_dict()
            sel_t_id = st.selectbox("修正対象の旅行", list(t_dict.keys()), format_func=lambda x: str(t_dict[x]), key="edit_trip_sel")
            trip_expenses = df_ex[df_ex['trip_id'] == sel_t_id].copy()
            
            if not trip_expenses.empty:
                if 'expense_date' not in trip_expenses.columns:
                     trip_expenses['expense_date'] = trip_expenses['timestamp'].astype(str).str.split(" ").str[0]
                
                # 型変換 (TypeError対策)
                trip_expenses['expense_date'] = trip_expenses['expense_date'].astype(str)
                trip_expenses['item_name'] = trip_expenses['item_name'].fillna('').astype(str)
                trip_expenses['amount'] = trip_expenses['amount'].fillna(0).astype(str)
                
                trip_expenses['label'] = trip_expenses['expense_date'] + " - " + trip_expenses['item_name'] + " (¥" + trip_expenses['amount'] + ")"
                
                exp_dict = trip_expenses.set_index('entry_id')['label'].to_dict()
                sel_exp_id = st.selectbox("修正項目", list(exp_dict.keys()), format_func=lambda x: exp_dict[x])
                target_row = trip_expenses[trip_expenses['entry_id'] == sel_exp_id].iloc[0]
                
                st.markdown("---")
                with st.form("edit_form"):
                    try: curr_date = datetime.strptime(str(target_row['expense_date']), "%Y-%m-%d").date()
                    except: curr_date = datetime.today()
                    new_date = st.date_input("支出日", value=curr_date)
                    new_item = st.text_input("品目・店名", value=target_row['item_name'])
                    c1, c2 = st.columns(2)
                    new_amount = c1.number_input("金額", min_value=0, value=int(float(target_row['amount'])), step=100)
                    curr_cat = target_row['category']
                    cat_opts = ["食事", "宿泊", "交通", "娯楽/体験", "雑費"]
                    cat_idx = cat_opts.index(curr_cat) if curr_cat in cat_opts else 0
                    new_cat = c2.selectbox("カテゴリ", cat_opts, index=cat_idx)
                    
                    st.markdown("---")
                    
                    # 満足度ロジック
                    curr_sat = int(float(target_row['satisfaction']))
                    
                    # 現在が0(未評価)かどうか
                    is_currently_pending = (curr_sat == 0)
                    new_is_pending = st.checkbox("未評価 (Pending) に設定する", value=is_currently_pending)
                    
                    if new_is_pending:
                        new_sat = 0
                        st.caption("※ 0 (未評価) として保存されます。")
                    else:
                        # 未評価から切り替える場合はデフォルト5、そうでなければ現在の値
                        default_sat = 5 if is_currently_pending else curr_sat
                        new_sat = st.slider("満足度", 1, 10, default_sat)

                    curr_waste_val = str(target_row.get('is_waste', 'FALSE')).upper() == 'TRUE'
                    new_waste = st.checkbox("浪費 (Avoidable Waste)", value=curr_waste_val)
                    new_detail = st.text_area("詳細", value=target_row['detail'])
                    
                    if st.form_submit_button("修正保存"):
                        update_expense(sel_exp_id, new_cat, new_item, new_amount, new_sat, new_detail, new_date, new_waste)
            else: st.info("データがありません")

    with tab3:
        st.subheader("旅行情報の修正")
        df_trips = load_cached_data("trips")
        if not df_trips.empty:
            if 'detail' not in df_trips.columns: df_trips['detail'] = ""
            t_dict = df_trips.set_index('trip_id').T.to_dict()
            sel_t_id = st.selectbox("修正する旅行を選択", list(t_dict.keys()), format_func=lambda x: f"{t_dict[x]['trip_name']} ({t_dict[x]['status']})", key="mod_trip_sel")
            curr_data = t_dict[sel_t_id]
            with st.form("mod_trip_form"):
                m_name = st.text_input("旅行名", value=curr_data['trip_name'])
                m_budget = st.number_input("総予算", min_value=0, step=10000, value=int(str(curr_data['total_budget']).replace(',','')) if curr_data['total_budget'] else 0)
                c1, c2 = st.columns(2)
                try: d_start = datetime.strptime(str(curr_data['start_date']), "%Y-%m-%d").date()
                except: d_start = datetime.today()
                try: d_end = datetime.strptime(str(curr_data['end_date']), "%Y-%m-%d").date()
                except: d_end = datetime.today()
                m_start = c1.date_input("開始日", value=d_start)
                m_end = c2.date_input("終了日", value=d_end)
                st_opts = ["Planning", "Active", "Completed", "Cancelled"]
                curr_st = curr_data['status']
                st_idx = st_opts.index(curr_st) if curr_st in st_opts else 0
                m_status = st.selectbox("ステータス", st_opts, index=st_idx)
                m_detail = st.text_area("詳細・メモ", value=str(curr_data['detail']))
                if st.form_submit_button("旅行情報を更新"):
                    update_trip_info(sel_t_id, m_name, m_start, m_end, m_budget, m_status, m_detail)

    with tab4:
        st.subheader("データ削除")
        del_type = st.radio("削除対象", ["支出データ (1件)", "旅行プロジェクト (全体)"], horizontal=True)
        if del_type == "支出データ (1件)":
            expense_id = st.text_input("削除する entry_id")
            if st.button("支出削除実行"):
                if expense_id: delete_row_simple("expenses", expense_id, id_col_index=1)
        elif del_type == "旅行プロジェクト (全体)":
            df_trips = load_cached_data("trips")
            if not df_trips.empty:
                t_dict = df_trips.set_index('trip_id')['trip_name'].to_dict()
                del_trip_id = st.selectbox("削除する旅行", list(t_dict.keys()), format_func=lambda x: str(t_dict[x]), key="del_trip_sel")
                target_name = t_dict[del_trip_id]
                st.warning(f"警告: 「{target_name}」を削除します。")
                confirm_name = st.text_input(f"確認のため「{target_name}」と入力してください")
                if st.button("プロジェクト完全抹消"):
                    if confirm_name == target_name: delete_trip_cascade(del_trip_id, target_name)
                    else: st.error("名前不一致")
