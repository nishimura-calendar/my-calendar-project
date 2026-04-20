import shutil
import streamlit as st

# Ghostscriptの実行ファイルを探す
gs_path = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")

if gs_path:
    st.success(f"Ghostscriptが見つかりました: {gs_path}")
else:
    st.error("Ghostscriptが見つかりません。packages.txtを確認してください。")
