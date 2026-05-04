import streamlit as st
import practice_0 as p0
import base64
import re
from googleapiclient.discovery import build
from google.oauth2 import service_account

SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service():
    """Google Sheets API 認証[cite: 5]"""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return build('sheets', 'v4', credentials=creds)

def stop_with_pdf(error_text):
    """エラー表示とプログラム停止"""
    st.error(error_text)
    try:
        with open("temp.pdf", "rb") as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
        st.markdown(f'<embed src="data:application/pdf;base64,{b64}" width="100%" height="800">', unsafe_allow_html=True)
    except: pass
    st.stop()

st.set_page_config(layout="wide")

# 1. 時程表の事前読込[cite: 5]
if 'time_dic' not in st.session_state:
    try:
        service = get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}")
        st.stop()

# 2. PDFアップロード[cite: 5]
uploaded_file = st.file_uploader("PDFシフト表を選択してください", type="pdf")

if uploaded_file:
    # ファイル名から年月抽出
    fname = uploaded_file.name
    match_y = re.search(r'(\d{4})', fname)
    match_m = re.search(r'(\d{1,2})', fname)
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    # A. 抽出不可の場合の入力ボックス
    if y is None or m is None:
        st.warning("年月を特定できません。入力してください。")
        y = st.number_input("年", value=2026)
        m = st.number_input("月", min_value=1, max_value=12)
        is_ready = st.button("ファイル確認")
    else: is_ready = True

    if is_ready:
        with open("temp.pdf", "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        # 第一関門判定
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        if res is None: stop_with_pdf(f"第一関門失敗: {msg}")

        # 第２関門：location!=key 完全一致判定
        location = res['location']
        if location not in st.session_state.time_dic:
            stop_with_pdf(f"{location} は時程表の勤務地には設定されていません。確認が必要です。")

        # 第３関門：スタッフ選択
        st.write("### シフトカレンダーを作成するスタッフを選んで下さい。")
        target_staff = st.selectbox("氏名一覧", ["該当なし"] + res['staff_list'])
        
        if target_staff != "該当なし":
            df = res['df']
            if target_staff in df[0].values:
                idx = df[df[0] == target_staff].index[0]
                # 本人(氏名+資格)と他人の切り分け
                my_daily_shift = df.iloc[idx : idx+2, 1:]
                other_daily_shift = df.drop([idx, idx+1]).iloc[2:, 1:]
                
                # 結果表示
                st.subheader(f"【{target_staff}】のシフト情報")
                st.write("my_daily_shift")
                st.dataframe(my_daily_shift, hide_index=True)
                st.write("other_daily_shift")
                st.dataframe(other_daily_shift, hide_index=True)
                st.write("time_schedule")
                st.dataframe(st.session_state.time_dic[location], hide_index=True)
            else:
                stop_with_pdf(f"target_staff【{target_staff}】が見つかりません。")
