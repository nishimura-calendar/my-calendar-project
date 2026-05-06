import streamlit as st
import practice_0 as p0
import re
import fitz
from googleapiclient.discovery import build
from google.oauth2 import service_account

SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def display_pdf_as_image(pdf_path):
    """PDFを画像化して表示[cite: 4]"""
    doc = fitz.open(pdf_path)
    img_bytes = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
    st.image(img_bytes, caption="アップロードされたPDFの確認", use_container_width=True)
    doc.close()

def stop_with_pdf(error_text, pdf_path):
    """エラー停止[cite: 9]"""
    st.error(error_text)
    display_pdf_as_image(pdf_path)
    st.stop()

st.set_page_config(layout="wide")

# 1. 時程表読込
if 'time_dic' not in st.session_state:
    try:
        # GCP認証と読込（既存の認証関数を想定）
        # st.session_state.time_dic = p0.load_master_from_sheets(...) 
        pass 
    except: st.stop()

# 2. PDFアップロード
uploaded_file = st.file_uploader("PDFシフト表を選択してください", type="pdf")

if uploaded_file:
    # ★ アップロードされたファイル名を常に表示
    st.markdown(f"### 📄 読込中のファイル: `{uploaded_file.name}`")
    
    pdf_bytes = uploaded_file.getvalue()
    with open("temp.pdf", "wb") as f: f.write(pdf_bytes)

    # 年月抽出
    fname = uploaded_file.name
    match_y, match_m = re.search(r'(\d{4})', fname), re.search(r'(\d{1,2})', fname)
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    if y is None or m is None:
        st.warning("年月を入力してください。")
        y = st.number_input("年", value=2026); m = st.number_input("月", min_value=1, max_value=12)
        is_ready = st.button("ファイル確認")
    else: is_ready = True

    if is_ready:
        # 第一関門
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        if res is None: stop_with_pdf(msg, "temp.pdf")

        # 第2関門：location照合[cite: 9]
        location = res['location']
        if location not in st.session_state.time_dic:
            stop_with_pdf(f"【{location}】は時程表の勤務地には設定されていません。確認が必要です。", "temp.pdf")
        
        # 第3関門：スタッフ選択[cite: 9]
        st.success(f"勤務地「{location}」の照合に成功しました。")
        target_staff = st.selectbox("シフトカレンダーを作成するスタッフを選んで下さい。", 
                                   options=["該当なし"] + res['staff_list'])
        
        if target_staff != "該当なし":
            df = res['df']
            if target_staff in df[0].values:
                idx = df[df[0] == target_staff].index[0]
                
                # 指定の範囲でデータ抽出[cite: 9]
                my_daily_shift = df.iloc[idx : idx+2, 0:]
                other_daily_shift = df.drop([idx, idx+1]).iloc[2:, 0:]
                
                st.write(f"### {target_staff} の抽出データ")
                st.write("#### my_daily_shift")
                st.dataframe(my_daily_shift, hide_index=True)
                st.write("#### other_daily_shift")
                st.dataframe(other_daily_shift, hide_index=True)
                st.write("#### time_schedule")
                st.dataframe(st.session_state.time_dic[location], hide_index=True)
            else:
                stop_with_pdf("target_staffが見つかりません。確認して下さい。", "temp.pdf")
