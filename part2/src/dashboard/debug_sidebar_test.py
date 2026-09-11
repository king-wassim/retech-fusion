import streamlit as st

st.set_page_config(page_title="Debug Sidebar Test", layout="wide", initial_sidebar_state="expanded")

st.sidebar.markdown("""
## SIDEBAR DEBUG

Si ce panneau s'affiche, la fonctionnalité `st.sidebar` fonctionne.
""")

st.markdown("# Debug: Main content")
st.write("Si la sidebar est visible ici, le problème vient probablement du CSS ou du rendu de `app.py`.")
