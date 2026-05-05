import streamlit as st
import practice_0 as p0
import base64
import re
import fitz  # PyMuPDF: PDFを画像に変換するために使用
from googleapiclient.discovery import build
from google.oauth2 import service_account

SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service():
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

def display_pdf_as_image(pdf_path):
    """
    PDFの1ページ目を画像として表示する（確実に表示するための回避策）
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)  # 1ページ目
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 高解像度で画像化
        img_bytes = pix.tobytes("png")
        st.image(img_bytes, caption="アップロードされたPDFのプレビュー", use_container_width=True)
        doc.close()
    except Exception as e:
        st.warning(f"画像の生成に失敗しました。直接PDFを確認してください: {e}")

def stop_with_pdf_final(error_text, pdf_path):
    """
    エラー表示後、PDFを画像として表示して完全に停止する
    """
    st.error(error_text)
    st.write("### アップロードされたファイルの確認")
    display_pdf_as_image(pdf_path)
    
    # 万が一画像も見れない時のためのダウンロードボタン
    with open(pdf_path, "rb") as f:
        st.download_button("PDFファイルをダウンロードして確認", f, file_name="uploaded_shift.pdf")
    st.stop()

st.set_page_config(layout="wide")

# 1. 時程表の事前読込
if 'time_dic' not in st.session_state:
    try:
        service = get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}"); st.stop()

# 2. PDFアップロード
uploaded_file = st.file_uploader("PDFシフト表を選択してください", type="pdf")

if uploaded_file:
    # 解析用の一時ファイル保存
    pdf_bytes = uploaded_file.getvalue()
    with open("temp.pdf", "wb") as f:
        f.write(pdf_bytes)

    # 年月抽出
    fname = uploaded_file.name
    match_y, match_m = re.search(r'(\d{4})', fname), re.search(r'(\d{1,2})', fname)
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    if y is None or m is None:
        st.warning("年月を入力してください。")
        y = st.number_input("年", value=2026); m = st.number_input("月", min_value=1, max_value=12)
        is_ready = st.button("ファイル確認")
    else: 
        is_ready = True

    if is_ready:
        # 第一関門判定
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        
        if res is None:
            # 不一致なら画像としてPDFを表示して停止
            stop_with_pdf_final(f"第一関門不一致: {msg}", "temp.pdf")

        # 第二関門以降...
        location = res['location']
        if location not in st.session_state.time_dic:
            stop_with_pdf_final(f"【{location}】は時程表にありません。", "temp.pdf")
        
        st.success(f"勤務地「{location}」の照合に成功しました。")
        target_staff = st.selectbox("スタッフ選択", options=["該当なし"] + res['staff_list'])
        # ...（以下略）
