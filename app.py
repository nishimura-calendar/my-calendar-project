import streamlit as st
import practice_0 as p0
import base64
import re
from googleapiclient.discovery import build
from google.oauth2 import service_account

# 時程表のスプレッドシートID
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service():
    """Google Sheets API 認証"""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

def stop_with_pdf(error_text):
    """エラーを表示し、PDFを画面に出してプログラムを停止する[cite: 2, 4]"""
    st.error(error_text)
    try:
        # PDFをBase64エンコードして埋め込むことで、確実に表示させる[cite: 4]
        with open("temp.pdf", "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        
        pdf_display = f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf">'
        st.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"PDFのプレビュー表示に失敗しました: {e}")
    
    # 以降の処理をすべて停止[cite: 2, 4]
    st.stop()

st.set_page_config(layout="wide", page_title="シフト管理システム")

# 1. 時程表の事前読込[cite: 2]
if 'time_dic' not in st.session_state:
    try:
        service = get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表の読み込みに失敗しました: {e}")
        st.stop()

st.title("シフト表データ抽出")

# 2. PDFアップロード[cite: 2, 3]
uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type="pdf")

if uploaded_file:
    # 重要：解析前にファイルを保存（エラー表示用）[cite: 3, 4]
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())

    # ファイル名から年月抽出[cite: 2]
    fname = uploaded_file.name
    match_y = re.search(r'(\d{4})', fname)
    match_m = re.search(r'(\d{1,2})', fname)
    
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    # (A) 年月が不明な場合の入力[cite: 2]
    if y is None or m is None:
        st.warning("ファイル名から年月を特定できません。入力してください。")
        col1, col2 = st.columns(2)
        with col1:
            y = st.number_input("年", value=2026, step=1)
        with col2:
            m = st.number_input("月", min_value=1, max_value=12, step=1)
        is_ready = st.button("ファイル確認")
    else:
        is_ready = True

    if is_ready:
        # 3. 第一関門：算出値(①)とPDF抽出値(②)の比較[cite: 2]
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        
        if res is None:
            # 不一致なら理由を表示してPDFを出して停止[cite: 2]
            stop_with_pdf(f"第一関門不一致: {msg}")

        # 4. 第２関門：location完全一致判定[cite: 2]
        location = res['location']
        if location not in st.session_state.time_dic:
            stop_with_pdf(f"【{location}】は時程表の勤務地には設定されていません。")
        
        # 5. 第３関門：スタッフ選択（ドロップダウン）[cite: 2]
        st.success(f"勤務地「{location}」の照合に成功しました。")
        st.write("---")
        st.subheader("スタッフ選択")
        
        staff_options = ["該当なし"] + res['staff_list']
        target_staff = st.selectbox("カレンダーを作成するスタッフを選択してください", options=staff_options)
        
        if target_staff != "該当なし":
            df = res['df']
            if target_staff in df[0].values:
                idx = df[df[0] == target_staff].index[0]
                
                # データの抽出（本人＋資格、他スタッフ）[cite: 2]
                my_daily_shift = df.iloc[idx : idx+2, 1:]
                other_daily_shift = df.drop([idx, idx+1]).iloc[2:, 1:]
                
                # 結果表示[cite: 2]
                st.write("---")
                st.subheader(f"表示結果: {target_staff}")
                
                st.write("#### 本人シフト (my_daily_shift)")
                st.dataframe(my_daily_shift, hide_index=True)
                
                st.write("#### 他スタッフ状況 (other_daily_shift)")
                st.dataframe(other_daily_shift, hide_index=True)
                
                st.write("#### 拠点時程表 (time_schedule)")
                st.dataframe(st.session_state.time_dic[location], hide_index=True)
            else:
                stop_with_pdf(f"target_staff【{target_staff}】が見つかりません。")
