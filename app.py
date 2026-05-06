import streamlit as st
import practice_0 as p0
import re
import fitz
from googleapiclient.discovery import build
from google.oauth2 import service_account

SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

# --- 省略（get_service, display_pdf_as_image は前回同様） ---

st.set_page_config(layout="wide")

# 1. 時程表の事前読込
if 'time_dic' not in st.session_state:
    try:
        service = p0.get_service() # practice_0側に認証を持たせる構成
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}"); st.stop()

# 2. PDFアップロード
uploaded_file = st.file_uploader("PDFシフト表を選択してください", type="pdf")

if uploaded_file:
    # ★ ファイル名を青いボックスの中に「全表示」します
    st.info(f"📄 処理対象ファイル:\n{uploaded_file.name}")
    
    pdf_bytes = uploaded_file.getvalue()
    with open("temp.pdf", "wb") as f: f.write(pdf_bytes)

    # 年月抽出・解析（中略：前回同様のロジック）
    # ... (y, m の特定処理) ...

    if is_ready:
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        if res is None:
            st.error(msg); p0.display_pdf_as_image("temp.pdf"); st.stop()

        location = res['location']
        
        # スタッフ選択（ここでのリストから T1 が消えます）
        st.success(f"勤務地「{location}」を照合しました。")
        target_staff = st.selectbox("スタッフを選択してください", options=["該当なし"] + res['staff_list'])
        
        # --- 以下、データ表示処理 ---
