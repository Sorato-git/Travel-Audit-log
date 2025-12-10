import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import pandas as pd
import utils

def highlight_audit_rows(row):
    is_waste = str(row.get('is_waste', '')).upper() == 'TRUE'
    try: sat = int(row.get('satisfaction', 0))
    except: sat = 0
    if is_waste: return ['background-color: #FFD700; color: black'] * len(row)
    elif sat == 0: return ['background-color: #7f8c8d; color: white'] * len(row)
    elif sat <= 3: return ['background-color: #ff6347; color: white'] * len(row)
    return [''] * len(row)

def render():
    st.header("データ監査・分析")
    df_trips = utils.load_cached_data("trips")
    
    if not df_trips.empty:
        trip_options = df_trips.set_index('trip_id')['trip_name'].to_dict()
        filter_opts = ["ALL"] + list(trip_options.keys())
        target_trip = st.selectbox("フィルタ", filter_opts, format_func=lambda x: str(trip_options.get(x, "全プロジェクト")))
        
        df_ex = utils.load_cached_data("expenses")
        
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
                
                with col_g1:
                    ratio = (total_spent / budget) * 100
                    bar_color = utils.COLOR_RED if total_spent > budget else utils.COLOR_GREEN
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
                            chart_color_map[label_name] = utils.CATEGORY_COLOR_MAP.get(cat_name, "#808080")

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
            st.download_button(label="CSVエクスポート", data=csv, file_name=f'travel_audit_{datetime.now().strftime("%Y%m%d")}.csv', mime='text/csv')

            display_cols = ['expense_date', 'category', 'item_name', 'amount', 'satisfaction', 'is_waste', 'detail', 'entry_id']
            valid_cols = [c for c in display_cols if c in df_ex.columns]
            sorted_df = df_ex[valid_cols].sort_values(by='expense_date', ascending=False)
            st.dataframe(sorted_df.style.apply(highlight_audit_rows, axis=1), use_container_width=True, hide_index=True)
        else:
            st.info("支出データなし")