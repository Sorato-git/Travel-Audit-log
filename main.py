import streamlit as st
import tabs.entry
import tabs.audit
import tabs.admin

# ページ設定
st.set_page_config(page_title="Travel Audit Log", layout="wide")

st.title("Travel Audit Log")

menu = ["支出記録 (Entry)", "台帳閲覧 (Audit)", "管理・修正 (Admin)"]
choice = st.sidebar.radio("Menu", menu)

if choice == "支出記録 (Entry)":
    tabs.entry.render()
elif choice == "台帳閲覧 (Audit)":
    tabs.audit.render()
elif choice == "管理・修正 (Admin)":
    tabs.admin.render()
