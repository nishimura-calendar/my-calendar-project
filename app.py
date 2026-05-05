import streamlit as st
import practice_0 as p0
import base64
import re
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

def display_pdf_v2(file_bytes):
    """
    ブラウザ互換性を極限まで高めたPDF表示
    """
    base64_pdf = base64.b64encode(file_bytes).decode('utf-8')
    
    # PDFを埋め込むHTML（object, embed, iframeの3段構え）
    pdf_html = f"""
        <div style="text-align: center;">
            <object data="data:application/pdf;base64,{base64_pdf}" type="application/pdf" width="100%" height="800px">
                <embed src="data:application/pdf;base64,{base64_pdf}" type="application/pdf" width="100%" height="800px" />
                <p>ブラウザがPDFの表示をサポートしていないようです。
                <a href="data:application/pdf;base64,{base64_pdf}" download="shift_table.pdf">こちらからダウンロード</a>して確認してください。</p>
            </object>
        </div>
    """
    st.markdown(pdf_html, unsafe_allow_html=True)

def stop_with_pdf_v2(error_text, file_bytes):
    """
    エラー表示後、PDFを表示して完全に停止する[cite: 2, 4]
    """
    st.error(error_text)
    # 表示が不安定な場合を考慮し、展開・折り畳みUIの中にPDFを配置
    with st.expander("アップロードしたPDFを確認する", expanded=True):
        display_pdf_v2(file_bytes)
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
    # 読み取りポインタ問題を回避
    pdf_bytes = uploaded_file.getvalue()
    with open("temp.pdf", "wb") as f:
        f.write(pdf_bytes)

    # 年月抽出
    fname = uploaded_file.name
    match_y, match_m = re.search(r'(\d{4})', fname), re.search(r'(\d{1,2})', fname)
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    if y is None or m is None:
        st.warning("ファイル名から年月を特定できません。入力してください。")
        y = st.number_input("年", value=2026); m = st.number_input("月", min_value=1, max_value=12)
        is_ready = st.button("ファイル確認")
    else: is_ready = True

    if is_ready:
        # 第一関門：算出(①)と抽出(②)の比較[cite: 2]
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        
        if res is None:
            # 第一関門不一致：理由を表示してPDFを表示[cite: 2, 4]
            stop_with_pdf_v2(f"第一関門不一致: {msg}", pdf_bytes)

        # 第二関門：location照合[cite: 2]
        location = res['location']
        if location not in st.session_state.time_dic:
            stop_with_pdf_v2(f"【{location}】は時程表に登録されていません。", pdf_bytes)
        
        # 第三関門：スタッフ選択
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
                stop_with_pdf_v2(f"【{target_staff}】が見つかりません。", pdf_bytes)
