import streamlit as st
from datetime import datetime
import utils

def render():
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
                utils.add_trip(t_name, t_start, t_end, t_budget, t_detail)

    with tab2:
        st.subheader("既存データの修正")
        df_trips = utils.load_cached_data("trips")
        df_ex = utils.load_cached_data("expenses")
        if not df_trips.empty and not df_ex.empty:
            t_dict = df_trips.set_index('trip_id')['trip_name'].to_dict()
            sel_t_id = st.selectbox("修正対象の旅行", list(t_dict.keys()), format_func=lambda x: str(t_dict[x]), key="edit_trip_sel")
            trip_expenses = df_ex[df_ex['trip_id'] == sel_t_id].copy()
            
            if not trip_expenses.empty:
                if 'expense_date' not in trip_expenses.columns:
                     trip_expenses['expense_date'] = trip_expenses['timestamp'].astype(str).str.split(" ").str[0]
                
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
                    curr_sat = int(float(target_row['satisfaction']))
                    is_currently_pending = (curr_sat == 0)
                    new_is_pending = st.checkbox("未評価 (Pending) に設定する", value=is_currently_pending)
                    
                    if new_is_pending:
                        new_sat = 0
                        st.caption("※ 0 (未評価) として保存されます。")
                    else:
                        default_sat = 5 if is_currently_pending else curr_sat
                        new_sat = st.slider("満足度", 1, 10, default_sat)

                    curr_waste_val = str(target_row.get('is_waste', 'FALSE')).upper() == 'TRUE'
                    new_waste = st.checkbox("浪費 (Avoidable Waste)", value=curr_waste_val)
                    new_detail = st.text_area("詳細", value=target_row['detail'])
                    
                    if st.form_submit_button("修正保存"):
                        utils.update_expense(sel_exp_id, new_cat, new_item, new_amount, new_sat, new_detail, new_date, new_waste)
            else: st.info("データがありません")

    with tab3:
        st.subheader("旅行情報の修正")
        df_trips = utils.load_cached_data("trips")
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
                    utils.update_trip_info(sel_t_id, m_name, m_start, m_end, m_budget, m_status, m_detail)

    with tab4:
        st.subheader("データ削除")
        del_type = st.radio("削除対象", ["支出データ (1件)", "旅行プロジェクト (全体)"], horizontal=True)
        if del_type == "支出データ (1件)":
            expense_id = st.text_input("削除する entry_id")
            if st.button("支出削除実行"):
                if expense_id: utils.delete_row_simple("expenses", expense_id, id_col_index=1)
        elif del_type == "旅行プロジェクト (全体)":
            df_trips = utils.load_cached_data("trips")
            if not df_trips.empty:
                t_dict = df_trips.set_index('trip_id')['trip_name'].to_dict()
                del_trip_id = st.selectbox("削除する旅行", list(t_dict.keys()), format_func=lambda x: str(t_dict[x]), key="del_trip_sel")
                target_name = t_dict[del_trip_id]
                st.warning(f"警告: 「{target_name}」を削除します。")
                confirm_name = st.text_input(f"確認のため「{target_name}」と入力してください")
                if st.button("プロジェクト完全抹消"):
                    if confirm_name == target_name: utils.delete_trip_cascade(del_trip_id, target_name)
                    else: st.error("名前不一致")