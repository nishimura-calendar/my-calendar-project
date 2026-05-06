import streamlit as st
import practice_0 as p0
import re
import fitz
from googleapiclient.discovery import build
from google.oauth2 import service_account

SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service():
    """GCP認証[cite: 8]"""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

def display_pdf_as_image(pdf_path):
    """PDFを画像化して表示[cite: 8]"""
    doc = fitz.open(pdf_path)
    img_bytes = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
    st.image(img_bytes, caption="アップロードされたPDFの確認", use_container_width=True)
    doc.close()

st.set_page_config(layout="wide")

# 1. 時程表の事前読込
if 'time_dic' not in st.session_state:
    try:
        service = get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
        st.toast("時程表を読み込みました")
    except Exception as e:
        st.error(f"時程表読込失敗: {e}")
        st.stop()

# 2. PDFアップロード
uploaded_file = st.file_uploader("PDFシフト表を選択してください", type="pdf")

if uploaded_file:
    # ファイル名を全表示（大きく表示）
    st.info(f"📁 選択中のファイル: {uploaded_file.name}")
    
    pdf_bytes = uploaded_file.getvalue()
    with open("temp.pdf", "wb") as f:
        f.write(pdf_bytes)

    # 年月抽出[cite: 8]
    fname = uploaded_file.name
    match_y, match_m = re.search(r'(\d{4})', fname), re.search(r'(\d{1,2})', fname)
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    if y is None or m is None:
        st.warning("ファイル名から年月を読み取れませんでした。")
        y = st.number_input("年", value=2026)
        m = st.number_input("月", min_value=1, max_value=12)
        is_ready = st.button("ファイル確認")
    else: 
        is_ready = True

    if is_ready:
        # PDF解析
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        if res is None:
            st.error(msg)
            display_pdf_as_image("temp.pdf")
            st.stop()

        location = res['location']
        if location not in st.session_state.time_dic:
            st.error(f"【{location}】は時程表に未登録です。")
            display_pdf_as_image("temp.pdf")
            st.stop()
        
        # スタッフ選択[cite: 5, 8]
        st.success(f"勤務地「{location}」を照合しました。")
        target_staff = st.selectbox("スタッフを選択してください", options=["該当なし"] + res['staff_list'])
        
        if target_staff != "該当なし":
            df = res['df']
            idx = df[df[0] == target_staff].index[0]
            
            # データ表示[cite: 5]
            st.write(f"### {target_staff} のシフトデータ")
            st.write("#### my_daily_shift")
            st.dataframe(df.iloc[idx : idx+2, 0:], hide_index=True)
            st.write("#### other_daily_shift")
            st.dataframe(df.drop([idx, idx+1]).iloc[2:, 0:], hide_index=True)
            st.write("#### time_schedule")
            st.dataframe(st.session_state.time_dic[location], hide_index=True)
