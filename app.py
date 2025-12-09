import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid
import time
import plotly.graph_objects as go
import plotly.express as px

# --- 1. 設定 & 接続 ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SPREADSHEET_NAME = "TravelAuditDB"

# カラーパレット定義
COLOR_RED = "#FF4B4B"
COLOR_GREEN = "#4BFF4B"
COLOR_BLUE = "#4B4BFF"

st.set_page_config(page_title="Travel Auditor v4", layout="wide") # グラフ用にWideモード推奨

@st.cache_resource
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
    new_row = [t_id, name, str(start), str(end), "Active", budget]
    worksheet_trips.append_row(new_row)
    st.toast(f"プロジェクト '{name}' を開始しました。")
    time.sleep(1)
    st.rerun()

def add_expense(trip_id, category, item, amount, sat, detail):
    e_id = str(uuid.uuid4())
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_row = [e_id, trip_id, ts, category, item, amount, sat, detail]
    worksheet_expenses.append_row(new_row)
    st.toast("支出を監査ログに記録しました。")
    time.sleep(1)
    st.rerun()

def update_expense(entry_id, category, item, amount, sat, detail):
    """既存の支出データを特定して上書き更新する"""
    try:
        # entry_id で行を検索 (A列=1列目と仮定)
        cell = worksheet_expenses.find(entry_id, in_column=1)
        row_num = cell.row
        
        # 列順序: entry_id(1), trip_id(2), timestamp(3), category(4), item_name(5), amount(6), satisfaction(7), detail(8)
        # 一括更新はできないのでセルごとに更新（または範囲更新）
        # 安全のためセル単位で更新
        worksheet_expenses.update_cell(row_num, 4, category)
        worksheet_expenses.update_cell(row_num, 5, item)
        worksheet_expenses.update_cell(row_num, 6, amount)
        worksheet_expenses.update_cell(row_num, 7, sat)
        worksheet_expenses.update_cell(row_num, 8, detail)
        
        st.success("データの修正が完了しました。")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"更新エラー: {e}")

def delete_row_simple(worksheet, id_col_val, id_col_index=1):
    try:
        cell = worksheet.find(id_col_val, in_column=id_col_index)
        if hasattr(worksheet, 'delete_rows'):
            worksheet.delete_rows(cell.row)
        else:
            worksheet.delete_row(cell.row)
        st.success("削除完了")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"削除エラー: {e}")

def delete_trip_cascade(trip_id, trip_name):
    status_box = st.empty()
    status_box.info("⚠️ 関連データの削除処理を開始します...")
    try:
        all_expenses = worksheet_expenses.get_all_records()
        if all_expenses:
            df = pd.DataFrame(all_expenses)
            if 'trip_id' in df.columns:
                remaining_df = df[df['trip_id'] != trip_id]
                worksheet_expenses.clear()
                header = ["entry_id", "trip_id", "timestamp", "category", "item_name", "amount", "satisfaction", "detail"]
                worksheet_expenses.append_row(header)
                if not remaining_df.empty:
                    for col in header:
                        if col not in remaining_df.columns:
                            remaining_df[col] = ""
                    data_to_write = remaining_df[header].values.tolist()
                    worksheet_expenses.append_rows(data_to_write)
        
        cell = worksheet_trips.find(trip_id, in_column=1)
        if hasattr(worksheet_trips, 'delete_rows'):
            worksheet_trips.delete_rows(cell.row)
        else:
            worksheet_trips.delete_row(cell.row)
            
        status_box.success(f"旅行「{trip_name}」と全関連データの完全消去が完了しました。")
        time.sleep(2)
        st.rerun()
    except Exception as e:
        st.error(f"完全削除中にエラーが発生しました: {e}")

def update_trip_status(trip_id, new_status):
    try:
        cell = worksheet_trips.find(trip_id, in_column=1)
        worksheet_trips.update_cell(cell.row, 5, new_status)
        st.toast(f"ステータス更新: {new_status}")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"更新エラー: {e}")

# --- 3. UI構築 ---

st.title("🛡️ Travel Audit v4")

menu = ["支出記録 (Entry)", "台帳閲覧 (Audit)", "管理・修正 (Admin)"]
choice = st.sidebar.radio("Menu", menu)

# --- A. 支出記録 ---
if choice == "支出記録 (Entry)":
    st.header("支出データの入力")
    df_trips = load_data(worksheet_trips)
    if df_trips.empty:
        st.warning("旅行プロジェクトがありません。")
    else:
        active_trips = df_trips[df_trips['status'] == 'Active']
        if active_trips.empty:
            st.warning("進行中(Active)の旅行がありません。")
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

# --- B. 台帳閲覧 ---
elif choice == "台帳閲覧 (Audit)":
    st.header("データ監査・分析")
    df_trips = load_data(worksheet_trips)
    
    if not df_trips.empty:
        # フィルタリング
        trip_options = df_trips.set_index('trip_id')['trip_name'].to_dict()
        filter_opts = ["ALL"] + list(trip_options.keys())
        target_trip = st.selectbox("フィルタ", filter_opts, format_func=lambda x: trip_options.get(x, "全プロジェクト"))
        
        df_ex = load_data(worksheet_expenses)
        
        if not df_ex.empty:
            if target_trip != "ALL":
                df_ex = df_ex[df_ex['trip_id'] == target_trip]
                
                # --- グラフエリア (Plotly) ---
                st.markdown("### 📊 支出分析")
                
                # データ準備
                budget_row = df_trips[df_trips['trip_id'] == target_trip]
                budget = int(budget_row['total_budget'].iloc[0]) if not budget_row.empty and budget_row['total_budget'].iloc[0] else 0
                total_spent = int(df_ex['amount'].sum())
                
                col_g1, col_g2 = st.columns(2)
                
                # 1. 予算対比棒グラフ
                with col_g1:
                    # バーの色決定: 予算内なら青、超過なら赤
                    bar_color = COLOR_BLUE if total_spent <= budget else COLOR_RED
                    
                    fig_budget = go.Figure()
                    fig_budget.add_trace(go.Bar(
                        y=['支出'],
                        x=[total_spent],
                        orientation='h',
                        marker=dict(color=bar_color),
                        name='支出実績'
                    ))
                    # 予算ライン
                    fig_budget.add_vline(x=budget, line_width=3, line_dash="dash", line_color=COLOR_GREEN, annotation_text="Budget")
                    
                    fig_budget.update_layout(
                        title=f"予算消化状況 (予算: ¥{budget:,})",
                        xaxis_title="金額 (JPY)",
                        height=250,
                        margin=dict(l=20, r=20, t=40, b=20)
                    )
                    st.plotly_chart(fig_budget, use_container_width=True)

                # 2. カテゴリ別ドーナツグラフ
                with col_g2:
                    if total_spent > 0:
                        cat_sum = df_ex.groupby('category')['amount'].sum().reset_index()
                        
                        # カスタムカラーシーケンス
                        custom_colors = [COLOR_BLUE, COLOR_GREEN, "#FFD700", "#FF00FF", "#00FFFF"]
                        
                        fig_cat = px.pie(
                            cat_sum, 
                            values='amount', 
                            names='category', 
                            hole=0.4,
                            color_discrete_sequence=custom_colors
                        )
                        fig_cat.update_layout(
                            title="カテゴリ別支出構成",
                            height=250,
                            margin=dict(l=20, r=20, t=40, b=20)
                        )
                        st.plotly_chart(fig_cat, use_container_width=True)
                    else:
                        st.info("データ不足のためグラフを表示できません")

            # --- 明細リスト表示 ---
            st.markdown("### 📝 支出明細")
            display_cols = ['timestamp', 'category', 'item_name', 'amount', 'satisfaction', 'detail', 'entry_id']
            valid_cols = [c for c in display_cols if c in df_ex.columns]
            
            st.dataframe(
                df_ex[valid_cols].sort_values(by='timestamp', ascending=False),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("支出データなし")

# --- C. 管理・修正 ---
elif choice == "管理・修正 (Admin)":
    st.header("プロジェクト管理センター")
    
    tab1, tab2, tab3, tab4 = st.tabs(["新規旅行登録", "データ修正(Edit)", "ステータス変更", "データ削除"])
    
    # 1. 新規登録
    with tab1:
        with st.form("new_trip_form"):
            t_name = st.text_input("旅行名")
            t_budget = st.number_input("総予算 (JPY)", min_value=0, step=10000)
            c1, c2 = st.columns(2)
            t_start = c1.date_input("開始日")
            t_end = c2.date_input("終了日")
            if st.form_submit_button("登録"):
                add_trip(t_name, t_start, t_end, t_budget)

    # 2. データ修正 (New!)
    with tab2:
        st.subheader("既存データの修正")
        df_trips = load_data(worksheet_trips)
        df_ex = load_data(worksheet_expenses)
        
        if not df_trips.empty and not df_ex.empty:
            # 旅行選択
            t_dict = df_trips.set_index('trip_id')['trip_name'].to_dict()
            sel_t_id = st.selectbox("修正対象の旅行", list(t_dict.keys()), format_func=lambda x: t_dict[x], key="edit_trip_sel")
            
            # その旅行の支出のみ抽出
            trip_expenses = df_ex[df_ex['trip_id'] == sel_t_id]
            
            if not trip_expenses.empty:
                # 選択肢作成: "日付 - 店名 (金額)"
                trip_expenses['label'] = trip_expenses['timestamp'].astype(str) + " - " + trip_expenses['item_name'] + " (¥" + trip_expenses['amount'].astype(str) + ")"
                exp_dict = trip_expenses.set_index('entry_id')['label'].to_dict()
                
                sel_exp_id = st.selectbox("修正する項目を選択", list(exp_dict.keys()), format_func=lambda x: exp_dict[x])
                
                # 選択されたデータの現況を取得
                target_row = trip_expenses[trip_expenses['entry_id'] == sel_exp_id].iloc[0]
                
                st.markdown("---")
                with st.form("edit_form"):
                    new_item = st.text_input("品目・店名", value=target_row['item_name'])
                    c1, c2 = st.columns(2)
                    new_amount = c1.number_input("金額", min_value=0, value=int(target_row['amount']), step=100)
                    new_cat = c2.selectbox("カテゴリ", ["食事", "宿泊", "交通", "娯楽/体験", "雑費"], index=["食事", "宿泊", "交通", "娯楽/体験", "雑費"].index(target_row['category']) if target_row['category'] in ["食事", "宿泊", "交通", "娯楽/体験", "雑費"] else 0)
                    
                    st.caption("満足度再評価")
                    new_sat = st.slider("満足度", 1, 10, int(target_row['satisfaction']))
                    new_detail = st.text_area("詳細", value=target_row['detail'])
                    
                    if st.form_submit_button("修正内容を保存"):
                        update_expense(sel_exp_id, new_cat, new_item, new_amount, new_sat, new_detail)
            else:
                st.info("修正可能なデータがありません。")
        else:
            st.info("データがありません。")

    # 3. ステータス変更
    with tab3:
        df_trips = load_data(worksheet_trips)
        if not df_trips.empty:
            t_dict = df_trips.set_index('trip_id')[['trip_name', 'status']].T.to_dict()
            target_t_id = st.selectbox("旅行", list(t_dict.keys()), format_func=lambda x: f"{t_dict[x]['trip_name']} ({t_dict[x]['status']})", key="status_sel")
            new_status = st.radio("状態", ["Active", "Completed", "Cancelled"], horizontal=True)
            if st.button("更新実行"):
                update_trip_status(target_t_id, new_status)

    # 4. データ削除
    with tab4:
        st.subheader("危険区域: データ削除")
        del_type = st.radio("削除対象", ["支出データ (1件)", "旅行プロジェクト (全体)"], horizontal=True)
        
        if del_type == "支出データ (1件)":
            expense_id = st.text_input("削除する entry_id")
            st.caption("※台帳閲覧タブで entry_id を確認してください")
            if st.button("支出削除実行"):
                if expense_id:
                    delete_row_simple(worksheet_expenses, expense_id, id_col_index=1)
                
        elif del_type == "旅行プロジェクト (全体)":
            df_trips = load_data(worksheet_trips)
            if not df_trips.empty:
                t_dict = df_trips.set_index('trip_id')['trip_name'].to_dict()
                del_trip_id = st.selectbox("削除する旅行", list(t_dict.keys()), format_func=lambda x: t_dict[x], key="del_trip_sel")
                target_name = t_dict[del_trip_id]
                
                st.markdown(f"""
                <div style="background-color: #3f0e0e; color: #ffcccc; padding: 10px; border-radius: 5px; border: 1px solid #ff4b4b; margin-bottom: 10px;">
                    <strong>⚠️ 警告:</strong> 旅行「{target_name}」および<strong>紐付く全ての支出データ</strong>を削除します。<br>
                    この操作は取り消せません。
                </div>
                """, unsafe_allow_html=True)
                
                confirm_name = st.text_input(f"確認のため「{target_name}」と入力してください")
                
                if st.button("プロジェクト完全抹消"):
                    if confirm_name == target_name:
                        delete_trip_cascade(del_trip_id, target_name)
                    else:
                        st.error("名前が一致しません。")
