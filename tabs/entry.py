import streamlit as st
from datetime import datetime, date
import utils

def render():
    st.header("支出データの入力")
    df_trips = utils.load_cached_data("trips")
    
    if df_trips.empty:
        st.warning("旅行プロジェクトがありません。")
    else:
        active_trips = df_trips[df_trips['status'].isin(['Active', 'Planning'])]
        if active_trips.empty:
            st.warning("進行中(Active)または計画中(Planning)の旅行がありません。")
        else:
            col_top1, col_top2 = st.columns(2)
            with col_top1:
                trip_options = active_trips.set_index('trip_id')['trip_name'].to_dict()
                selected_trip_id = st.selectbox("対象旅行", list(trip_options.keys()), format_func=lambda x: str(trip_options[x]))
            with col_top2:
                exp_date = st.date_input("支出日 (未記入時は本日)", value=datetime.today())

            today = date.today()
            is_future = exp_date > today
            
            if is_future:
                st.info(f"📅 **未来の日付 ({exp_date}) です。** 自動的に「未評価 (Pending)」として記録されます。")

            with st.form("expense_form"):
                item = st.text_input("品目・店名")
                col1, col2 = st.columns(2)
                amount = col1.number_input("金額", min_value=0, step=100)
                category = col2.selectbox("カテゴリ", ["食事", "宿泊", "交通", "娯楽/体験", "雑費"])
                
                st.markdown("---")
                is_pending = st.checkbox("未評価 (Pending) として記録 - 後で採点する", value=is_future)
                
                if is_pending:
                    sat = 0
                    st.caption("※ 満足度は **0 (未評価)** として記録されます。")
                else:
                    sat = st.slider("満足度 (ROI監査)", 1, 10, 5)
                
                is_waste = st.checkbox("浪費 (Avoidable Waste)")
                detail = st.text_area("詳細・備考", height=80)
                
                if st.form_submit_button("記録実行"):
                    if item and amount >= 0:
                        utils.add_expense(selected_trip_id, category, item, amount, sat, detail, exp_date, is_waste)
                    else:
                        st.error("入力不備があります。")