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

def display_pdf(file_bytes):
    """PDFをBase64でHTML埋め込み表示する"""
    base64_pdf = base64.b64encode(file_bytes).decode('utf-8')
    # iframeよりも互換性の高いobject/embedタグを使用
    pdf_display = f"""
        <object data="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf">
            <embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf">
        </object>
    """
    st.markdown(pdf_display, unsafe_allow_html=True)

def stop_with_pdf(error_text, file_bytes):
    """エラーを表示し、PDFを画面に出してプログラムを停止する[cite: 2, 4]"""
    st.error(error_text)
    display_pdf(file_bytes)
    st.stop()

st.set_page_config(layout="wide", page_title="シフト抽出システム")

# 1. 時程表の事前読込[cite: 2]
if 'time_dic' not in st.session_state:
    try:
        service = get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}")
        st.stop()

# 2. PDFアップロード[cite: 2, 3]
uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type="pdf")

if uploaded_file:
    # 重要：ファイルを一度変数に読み込み、ポインタ問題を回避する
    pdf_bytes = uploaded_file.getvalue()
    
    # 後の解析のために一時保存
    with open("temp.pdf", "wb") as f:
        f.write(pdf_bytes)

    # ファイル名から年月抽出[cite: 2]
    fname = uploaded_file.name
    match_y = re.search(r'(\d{4})', fname)
    match_m = re.search(r'(\d{1,2})', fname)
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    # 年月入力が必要な場合[cite: 2]
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
            # 不一致なら理由を表示してPDFを出して停止[cite: 2, 4]
            stop_with_pdf(f"第一関門不一致: {msg}", pdf_bytes)

        # 4. 第二関門：location照合[cite: 2]
        location = res['location']
        if location not in st.session_state.time_dic:
            stop_with_pdf(f"【{location}】は時程表に登録されていません。", pdf_bytes)
        
        # 5. 第三関門：スタッフ選択[cite: 2]
        st.success(f"勤務地「{location}」の照合に成功しました。")
        target_staff = st.selectbox("スタッフ選択", options=["該当なし"] + res['staff_list'])
        
        if target_staff != "該当なし":
            df = res['df']
            if target_staff in df[0].values:
                idx = df[df[0] == target_staff].index[0]
                st.write(f"#### 【{target_staff}】の抽出データ")
                st.dataframe(df.iloc[idx : idx+2, 1:], hide_index=True)
                st.write("#### 拠点時程表")
                st.dataframe(st.session_state.time_dic[location], hide_index=True)
            else:
                stop_with_pdf(f"【{target_staff}】が見つかりません。", pdf_bytes)
