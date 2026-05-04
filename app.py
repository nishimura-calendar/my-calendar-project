import streamlit as st
import practice_0 as p0
import base64
import re
from googleapiclient.discovery import build
from google.oauth2 import service_account

# スプレッドシートID
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service():
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return build('sheets', 'v4', credentials=creds)

st.set_page_config(layout="wide")

# 1. 時程表読込 [source: 2]
if 'time_dic' not in st.session_state:
    try:
        service = get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込エラー: {e}")

# 2. PDFアップロード [source: 2]
uploaded_file = st.file_uploader("PDFファイルをアップロード", type="pdf")

if uploaded_file:
    # ファイル名から年月抽出 [source: 2]
    match_y = re.search(r'(\d{4})', uploaded_file.name)
    match_m = re.search(r'(\d{1,2})', uploaded_file.name)
    
    if match_y and match_m:
        y, m = int(match_y.group(1)), int(match_m.group(1))
        is_ready = True
    else:
        # 抽出できなければ入力を促す [source: 2]
        st.warning("ファイル名から年月を特定できません。")
        y = st.number_input("年", value=2024)
        m = st.number_input("月", min_value=1, max_value=12)
        is_ready = st.button("ファイル確認")

    if is_ready:
        # 第一関門 [source: 2]
        with open("temp.pdf", "wb") as f: f.write(uploaded_file.getbuffer())
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        
        if res is None:
            st.error(f"第一関門失敗: {msg}")
            # PDFを表示してプログラム停止 [source: 2]
            with open("temp.pdf", "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800">', unsafe_allow_html=True)
            st.stop()
            
        # 第二関門 [source: 2]
        loc = res['location']
        if loc not in st.session_state.time_dic:
            st.error(f"{loc} は時程表の勤務地には設定されていません。確認が必要です。")
            with open("temp.pdf", "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            st.markdown(f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800">', unsafe_allow_html=True)
            st.stop()
            
        # 第三関門 [source: 2]
        st.write("### シフトカレンダーを作成するスタッフを選んで下さい。")
        target_staff = st.selectbox("スタッフ一覧（矢印キーで移動、Enterで確定）", ["該当なし"] + res['staff_list'])
        
        if target_staff != "該当なし":
            df = res['df']
            try:
                # target_staff検索
                idx = df[df[0] == target_staff].index[0]
                my_daily_shift = df.iloc[idx : idx+2, :]
                other_daily_shift = df.drop([idx, idx+1]).iloc[2:, :]
                
                # 表示 [source: 2]
                st.subheader(f"📅 {target_staff} のシフト情報")
                st.write("個人シフト (my_daily_shift)")
                st.dataframe(my_daily_shift, hide_index=True)
                
                st.write("他スタッフ (other_daily_shift)")
                st.dataframe(other_daily_shift, hide_index=True)
                
                st.write(f"時程表: {loc} (time_schedule)")
                st.dataframe(st.session_state.time_dic[loc], hide_index=True)
            except:
                st.error("target_staffが見つかりません。確認して下さい。")
                st.stop()
