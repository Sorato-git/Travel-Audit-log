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
COLOR_RED = "#FF4B4B"    # 食事
COLOR_BLUE = "#4B4BFF"   # 宿泊
COLOR_GREEN = "#4BFF4B"  # 交通
COLOR_CYAN = "#008B8B"   # 娯楽/体験 (ユーザー指定色)
COLOR_GOLD = "#FFD700"   # 雑費
COLOR_MAGENTA = "#FF00FF" # その他予備

# カテゴリごとの色固定マッピング
CATEGORY_COLOR_MAP = {
    "食事": COLOR_RED,
    "宿泊": COLOR_BLUE,
    "交通": COLOR_GREEN,
    "娯楽/体験": COLOR_CYAN,
    "雑費": COLOR_GOLD
}

st.set_page_config(page_title="Travel Audit Log", layout="wide")

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

def add_trip(name, start, end, budget, detail):
    t_id = str(uuid.uuid4())[:8]
    # Status初期値: Planning
    # 列順序: trip_id, trip_name, start_date, end_date, status, total_budget, detail
    new_row = [t_id, name, str(start), str(end), "Planning", budget, detail]
    worksheet_trips.append_row(new_row)
    st.toast(f"プロジェクト '{name}' を作成しました。")
    time.sleep(1)
    st.rerun()

def update_trip_info(trip_id, name, start, end, budget, status, detail):
    """旅行自体の情報を更新"""
    try:
        cell = worksheet_trips.find(trip_id, in_column=1)
        row_num = cell.row
        
        # セル更新 (A=1, B=2, C=3, D=4, E=5, F=6, G=7)
        worksheet_trips.update_cell(row_num, 2, name)
        worksheet_trips.update_cell(row_num, 3, str(start))
        worksheet_trips.update_cell(row_num, 4, str(end))
        worksheet_trips.update_cell(row_num, 5, status)
        worksheet_trips.update_cell(row_num, 6, budget)
        worksheet_trips.update_cell(row_num, 7, detail) # detail (Col G)
        
        st.success(f"旅行 '{name}' の情報を更新しました。")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"更新エラー: {e}")

def add_expense(trip_id, category, item, amount, sat, detail, exp_date):
    e_id = str(uuid.uuid4())
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 日付が未入力(None)なら今日の日付、あれば文字列化
    date_str = str(exp_date) if exp_date else datetime.now().strftime("%Y-%m-%d")
    
    # 列順序: entry_id, trip_id, timestamp, category, item_name, amount, satisfaction, detail, expense_date
    new_row = [e_id, trip_id, ts, category, item, amount, sat, detail, date_str]
    worksheet_expenses.append_row(new_row)
    st.toast("支出を監査ログに記録しました。")
    time.sleep(1)
    st.rerun()

def update_expense(entry_id, category, item, amount, sat, detail, exp_date):
    try:
        cell = worksheet_expenses.find(entry_id, in_column=1)
        row_num = cell.row
        date_str = str(exp_date)
        
        # セル更新
        worksheet_expenses.update_cell(row_num, 4, category)
        worksheet_expenses.update_cell(row_num, 5, item)
        worksheet_expenses.update_cell(row_num, 6, amount)
        worksheet_expenses.update_cell(row_num, 7, sat)
        worksheet_expenses.update_cell(row_num, 8, detail)
        worksheet_expenses.update_cell(row_num, 9, date_str) # expense_date (Col I)
        
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
                # ヘッダーに expense_date を追加
                header = ["entry_id", "trip_id", "timestamp", "category", "item_name", "amount", "satisfaction", "detail", "expense_date"]
                worksheet_expenses.append_row(header)
                if not remaining_df.empty:
                    # カラム不足時の補完
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



# --- 3. UI構築 ---

st.title("Travel Audit Log")

menu = ["支出記録 (Entry)", "台帳閲覧 (Audit)", "管理・修正 (Admin)"]
choice = st.sidebar.radio("Menu", menu)

# --- A. 支出記録 ---
if choice == "支出記録 (Entry)":
    st.header("支出データの入力")
    df_trips = load_data(worksheet_trips)
    
    if df_trips.empty:
        st.warning("旅行プロジェクトがありません。")
    else:
        # Planning または Active な旅行を表示
        active_trips = df_trips[df_trips['status'].isin(['Active', 'Planning'])]
        if active_trips.empty:
            st.warning("進行中(Active)または計画中(Planning)の旅行がありません。")
        else:
            trip_options = active_trips.set_index('trip_id')['trip_name'].to_dict()
            selected_trip_id = st.selectbox("対象旅行", list(trip_options.keys()), format_func=lambda x: trip_options[x])

            with st.form("expense_form"):
                # 支出日: デフォルトは今日
                exp_date = st.date_input("支出日 (未記入時は本日)", value=datetime.today())
                
                item = st.text_input("品目・店名")
                col1, col2 = st.columns(2)
                amount = col1.number_input("金額 ", min_value=0, step=100)
                category = col2.selectbox("カテゴリ", ["食事", "宿泊", "交通", "娯楽/体験", "雑費"])
                
                st.markdown("---")
                sat = st.slider("満足度 (ROI監査)", 1, 10, 5)
                detail = st.text_area("詳細・備考", height=80)
                
                if st.form_submit_button("記録実行"):
                    if item and amount >= 0:
                        add_expense(selected_trip_id, category, item, amount, sat, detail, exp_date)
                    else:
                        st.error("入力不備があります。")

# --- B. 台帳閲覧 ---
elif choice == "台帳閲覧 (Audit)":
    st.header("データ監査・分析")
    df_trips = load_data(worksheet_trips)
    
    if not df_trips.empty:
        trip_options = df_trips.set_index('trip_id')['trip_name'].to_dict()
        filter_opts = ["ALL"] + list(trip_options.keys())
        target_trip = st.selectbox("フィルタ", filter_opts, format_func=lambda x: trip_options.get(x, "全プロジェクト"))
        
        df_ex = load_data(worksheet_expenses)
        
        if not df_ex.empty:
            # データ整形: expense_dateがない古いデータは timestamp から日付を抽出して補完
            if 'expense_date' not in df_ex.columns:
                 df_ex['expense_date'] = ""
            
            # 空文字の行を timestamp の日付で埋める
            for idx, row in df_ex.iterrows():
                if str(row['expense_date']).strip() == "":
                    ts_val = str(row.get('timestamp', ''))
                    if ts_val:
                        try:
                            df_ex.at[idx, 'expense_date'] = ts_val.split(" ")[0]
                        except:
                            pass

            if target_trip != "ALL":
                df_ex = df_ex[df_ex['trip_id'] == target_trip]
                
                # --- グラフエリア (Plotly) ---
                st.markdown("### 📊 支出分析")
                
                budget_row = df_trips[df_trips['trip_id'] == target_trip]
                budget_val = budget_row['total_budget'].iloc[0]
                budget = int(budget_val) if not budget_row.empty and budget_val else 1
                total_spent = int(df_ex['amount'].sum())
                
                col_g1, col_g2 = st.columns(2)
                
                # 1. 予算消化バー 
                with col_g1:
                    ratio = (total_spent / budget) * 100
                    # 予算オーバーなら赤、以内なら緑
                    bar_color = COLOR_RED if total_spent > budget else COLOR_GREEN
                    
                    fig_budget = go.Figure()
                    
                    fig_budget.add_trace(go.Bar(
                        x=[total_spent],
                        y=[""],
                        orientation='h',
                        marker=dict(color=bar_color),
                        text=[f"{int(ratio)}%"], # パーセント表示
                        textposition='inside',   # バーの内側に表示
                        insidetextanchor='middle', # 中央揃え
                        textfont=dict(size=60, color='white', family="Arial Black") # 巨大フォント
                    ))
                    
                    # 軸設定 (予算を超えたら自動拡張、そうでなければ予算まで)
                    max_x = max(budget, total_spent) * 1.05
                    
                    fig_budget.update_layout(
                        title="予算消化状況",
                        xaxis=dict(
                            range=[0, max_x], 
                            title=f"{total_spent:,}円 / {budget:,}円", # X軸タイトルに金額
                            tickfont=dict(size=14),
                            title_font=dict(size=18)
                        ),
                        yaxis=dict(showticklabels=False),
                        height=200,
                        margin=dict(l=20, r=20, t=40, b=40)
                    )
                    # 予算ライン (点線)
                    fig_budget.add_vline(x=budget, line_width=3, line_dash="dash", line_color="white", annotation_text="Budget")
                    
                    st.plotly_chart(fig_budget, use_container_width=True)

# 2. カテゴリ別ドーナツ (固定順序: 食事->宿泊->交通->娯楽->雑費)
                with col_g2:
                    if total_spent > 0:
                        cat_sum = df_ex.groupby('category')['amount'].sum().reset_index()
                        
                        # --- 順序強制ロジック ---
                        # 指定された順序リスト
                        fixed_order = ["食事", "宿泊", "交通", "娯楽/体験", "雑費"]
                        
                        # カテゴリをCategorical型に変換してソート順を強制する
                        cat_sum['category'] = pd.Categorical(
                            cat_sum['category'], 
                            categories=fixed_order, 
                            ordered=True
                        )
                        cat_sum = cat_sum.sort_values('category')
                        # -----------------------

                        # 凡例用にラベルを加工
                        cat_sum['percent'] = (cat_sum['amount'] / total_spent) * 100
                        cat_sum['label'] = cat_sum.apply(lambda x: f"{x['category']} ({x['percent']:.1f}%)", axis=1)
                        
                        # 色マッピング作成
                        chart_color_map = {}
                        for _, row in cat_sum.iterrows():
                            cat_name = str(row['category']) # Categorical型から文字列に戻す
                            label_name = row['label']
                            chart_color_map[label_name] = CATEGORY_COLOR_MAP.get(cat_name, "#808080")

                        fig_cat = px.pie(
                            cat_sum, 
                            values='amount', 
                            names='label', 
                            hole=0.6,
                            color='label',
                            color_discrete_map=chart_color_map
                        )
                        
                        # 中央に合計金額、テキスト非表示
                        # sort=False にすることでDataFrameの並び順(fixed_order)を維持する
                        fig_cat.update_traces(textinfo='none', sort=False, direction='clockwise')
                        
                        fig_cat.update_layout(
                            title="カテゴリ別内訳",
                            annotations=[dict(text=f"¥{total_spent:,}", x=0.5, y=0.5, font_size=24, showarrow=False, font_weight="bold")],
                            height=250,
                            margin=dict(l=20, r=20, t=40, b=20),
                            showlegend=True,
                            legend=dict(font=dict(size=14))
                        )
                        
                        st.plotly_chart(fig_cat, use_container_width=True)
                    else:
                        st.info("データなし")

            # --- 明細リスト ---
            st.markdown("### 📝 支出明細")
            display_cols = ['expense_date', 'category', 'item_name', 'amount', 'satisfaction', 'detail', 'entry_id']
            # カラム存在確認
            valid_cols = [c for c in display_cols if c in df_ex.columns]
            
            # expense_date でソートして表示
            st.dataframe(
                df_ex[valid_cols].sort_values(by='expense_date', ascending=False),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("支出データなし")

# --- C. 管理・修正 ---
elif choice == "管理・修正 (Admin)":
    st.header("プロジェクト管理センター")
    
    tab1, tab2, tab3, tab4 = st.tabs(["新規旅行登録", "データ修正(Edit)", "ステータス変更", "データ削除"])
    
    with tab1:
        with st.form("new_trip_form"):
            st.subheader("新規プロジェクト作成")
            t_name = st.text_input("旅行名")
            t_budget = st.number_input("総予算 (JPY)", min_value=0, step=10000)
            c1, c2 = st.columns(2)
            t_start = c1.date_input("開始日")
            t_end = c2.date_input("終了日")
            t_detail = st.text_area("旅行の詳細・メモ (任意)")
            
            if st.form_submit_button("登録"):
                if t_name:
                    add_trip(t_name, t_start, t_end, t_budget, t_detail)
                else:
                    st.error("旅行名は必須です。")

    with tab2:
        st.subheader("既存データの修正")
        df_trips = load_data(worksheet_trips)
        df_ex = load_data(worksheet_expenses)
        
        if not df_trips.empty and not df_ex.empty:
            t_dict = df_trips.set_index('trip_id')['trip_name'].to_dict()
            sel_t_id = st.selectbox("修正対象の旅行", list(t_dict.keys()), format_func=lambda x: t_dict[x], key="edit_trip_sel")
            
            trip_expenses = df_ex[df_ex['trip_id'] == sel_t_id].copy()
            
            if not trip_expenses.empty:
                # expense_date列確保
                if 'expense_date' not in trip_expenses.columns:
                     trip_expenses['expense_date'] = trip_expenses['timestamp'].astype(str).str.split(" ").str[0]
                
                # ラベル作成
                trip_expenses['label'] = trip_expenses['expense_date'].astype(str) + " - " + trip_expenses['item_name'] + " (¥" + trip_expenses['amount'].astype(str) + ")"
                exp_dict = trip_expenses.set_index('entry_id')['label'].to_dict()
                
                sel_exp_id = st.selectbox("修正項目", list(exp_dict.keys()), format_func=lambda x: exp_dict[x])
                target_row = trip_expenses[trip_expenses['entry_id'] == sel_exp_id].iloc[0]
                
                st.markdown("---")
                with st.form("edit_form"):
                    # 日付復元
                    try:
                        curr_date = datetime.strptime(str(target_row['expense_date']), "%Y-%m-%d").date()
                    except:
                        curr_date = datetime.today()

                    new_date = st.date_input("支出日", value=curr_date)
                    new_item = st.text_input("品目・店名", value=target_row['item_name'])
                    c1, c2 = st.columns(2)
                    new_amount = c1.number_input("金額", min_value=0, value=int(target_row['amount']), step=100)
                    
                    curr_cat = target_row['category']
                    cat_opts = ["食事", "宿泊", "交通", "娯楽/体験", "雑費"]
                    cat_idx = cat_opts.index(curr_cat) if curr_cat in cat_opts else 0
                    new_cat = c2.selectbox("カテゴリ", cat_opts, index=cat_idx)
                    
                    st.caption("満足度再評価")
                    new_sat = st.slider("満足度", 1, 10, int(target_row['satisfaction']))
                    new_detail = st.text_area("詳細", value=target_row['detail'])
                    
                    if st.form_submit_button("修正保存"):
                        update_expense(sel_exp_id, new_cat, new_item, new_amount, new_sat, new_detail, new_date)
            else:
                st.info("データがありません")

    with tab3:
        st.subheader("旅行情報の修正")
        df_trips = load_data(worksheet_trips)
        
        if not df_trips.empty:
            # G列(detail)が無い場合のガード
            if 'detail' not in df_trips.columns:
                df_trips['detail'] = ""

            t_dict = df_trips.set_index('trip_id').T.to_dict()
            # 選択肢表示
            sel_t_id = st.selectbox("修正する旅行を選択", list(t_dict.keys()), format_func=lambda x: f"{t_dict[x]['trip_name']} ({t_dict[x]['status']})", key="mod_trip_sel")
            
            # 現在値の取得
            curr_data = t_dict[sel_t_id]
            
            with st.form("mod_trip_form"):
                m_name = st.text_input("旅行名", value=curr_data['trip_name'])
                m_budget = st.number_input("総予算", min_value=0, step=10000, value=int(str(curr_data['total_budget']).replace(',','')) if curr_data['total_budget'] else 0)
                
                c1, c2 = st.columns(2)
                try:
                    d_start = datetime.strptime(str(curr_data['start_date']), "%Y-%m-%d").date()
                    d_end = datetime.strptime(str(curr_data['end_date']), "%Y-%m-%d").date()
                except:
                    d_start = datetime.today()
                    d_end = datetime.today()
                
                m_start = c1.date_input("開始日", value=d_start)
                m_end = c2.date_input("終了日", value=d_end)
                
                # ステータス選択
                st_opts = ["Planning", "Active", "Completed", "Cancelled"]
                curr_st = curr_data['status']
                st_idx = st_opts.index(curr_st) if curr_st in st_opts else 0
                m_status = st.selectbox("ステータス", st_opts, index=st_idx)
                
                m_detail = st.text_area("詳細・メモ", value=str(curr_data['detail']))
                
                if st.form_submit_button("旅行情報を更新"):
                    update_trip_info(sel_t_id, m_name, m_start, m_end, m_budget, m_status, m_detail)
        else:
            st.info("旅行データがありません。")

    with tab4:
        st.subheader("データ削除")
        del_type = st.radio("削除対象", ["支出データ (1件)", "旅行プロジェクト (全体)"], horizontal=True)
        
        if del_type == "支出データ (1件)":
            expense_id = st.text_input("削除する entry_id")
            if st.button("支出削除実行"):
                if expense_id:
                    delete_row_simple(worksheet_expenses, expense_id, id_col_index=1)
                
        elif del_type == "旅行プロジェクト (全体)":
            df_trips = load_data(worksheet_trips)
            if not df_trips.empty:
                t_dict = df_trips.set_index('trip_id')['trip_name'].to_dict()
                del_trip_id = st.selectbox("削除する旅行", list(t_dict.keys()), format_func=lambda x: t_dict[x], key="del_trip_sel")
                target_name = t_dict[del_trip_id]
                
                st.warning(f"警告: 「{target_name}」を削除します。")
                confirm_name = st.text_input(f"確認のため「{target_name}」と入力してください")
                
                if st.button("プロジェクト完全抹消"):
                    if confirm_name == target_name:
                        delete_trip_cascade(del_trip_id, target_name)
                    else:
                        st.error("名前不一致")

