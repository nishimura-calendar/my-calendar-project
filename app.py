import streamlit as st
import practice_0 as p0
import base64
import re
from googleapiclient.discovery import build
from google.oauth2 import service_account

# スプレッドシートID（時程表）
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service():
    """Google Sheets API 認証[cite: 5]"""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

def display_pdf_and_stop(error_msg, pdf_path="temp.pdf"):
    """エラーメッセージを表示し、PDFをプレビューしてプログラムを停止する[cite: 9]"""
    st.error(error_msg)
    try:
        with open(pdf_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf">'
        st.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"PDFの表示に失敗しました: {e}")
    st.stop()

st.set_page_config(layout="wide", page_title="シフト管理システム")

# ---------------------------------------------------------
# 準備：時程表の読込
# ---------------------------------------------------------
if 'time_dic' not in st.session_state:
    try:
        service = get_service()
        # 勤務地名をキーにした辞書を取得[cite: 5]
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表の読み込みに失敗しました: {e}")
        st.stop()

# ---------------------------------------------------------
# メインフロー
# ---------------------------------------------------------
st.title("シフト表データ抽出")

# 2. pdfファイルをアップロードする[cite: 5]
uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type="pdf")

if uploaded_file:
    # 第一関門：ファイル名から年月抽出[cite: 9]
    fname = uploaded_file.name
    match_y = re.search(r'(\d{4})', fname)
    match_m = re.search(r'(\d{1,2})', fname)
    
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    # A. 抽出できなければ入力を促す[cite: 9]
    if y is None or m is None:
        st.info("ファイル名から年月を特定できません。手動で入力してください。")
        col1, col2 = st.columns(2)
        with col1:
            y = st.number_input("年", value=2026, step=1)
        with col2:
            m = st.number_input("月", min_value=1, max_value=12, step=1)
        is_ready = st.button("ファイル確認")
    else:
        is_ready = True

    if is_ready:
        # PDFを一時保存
        with open("temp.pdf", "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        # 3. 第一関門：日数・曜日の照合およびデータ抽出[cite: 9]
        # この中で ①算出日数=②PDF日数 の判定を行う
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        
        if res is None:
            # ①!=②なら理由を表示して停止[cite: 9]
            display_pdf_and_stop(f"第一関門失敗: {msg}")

        # 第２関門：location完全一致判定[cite: 9]
        # PDFの[0,0]から自動抽出されたlocationを使用
        location = res['location']
        if location not in st.session_state.time_dic:
            error_text = f"【{location}】は時程表の勤務地には設定されていません。確認が必要です。"
            display_pdf_and_stop(error_text)
        
        # 第３関門：ターゲットスタッフの選択[cite: 9]
        st.success(f"勤務地「{location}」の照合に成功しました。")
        st.write("---")
        st.subheader("第３関門：スタッフ選択")
        st.write("シフトカレンダーを作成するスタッフを選んで下さい。")
        
        staff_options = ["該当なし"] + res['staff_list']
        target_staff = st.selectbox("スタッフ名を選択", options=staff_options)
        
        if target_staff == "該当なし":
            st.info("スタッフを選択してください。")
        else:
            # target_staff検索・抽出処理[cite: 9]
            df = res['df']
            # dfの0列目から氏名を検索
            if target_staff in df[0].values:
                idx = df[df[0] == target_staff].index[0]
                
                # my_daily_shift => target_staff行(1列目〜) + その下段(資格行)[cite: 9]
                my_daily_shift = df.iloc[idx : idx+2, 1:]
                
                # other_daily_shift => target_staff以外の氏名行[cite: 9]
                # 0, 1行目(ヘッダー)と本人2行を除外
                other_daily_shift = df.drop([idx, idx+1]).iloc[2:, 1:]
                
                # 結果表示[cite: 9]
                st.write("---")
                st.subheader(f"表示結果: {target_staff}")
                
                st.write("#### my_daily_shift (本人＋資格)")
                st.dataframe(my_daily_shift, hide_index=True)
                
                st.write("#### other_daily_shift (他スタッフ)")
                st.dataframe(other_daily_shift, hide_index=True)
                
                st.write("#### time_schedule (拠点時程表)")
                st.dataframe(st.session_state.time_dic[location], hide_index=True)
            else:
                # 見つからなければ停止[cite: 9]
                display_pdf_and_stop(f"target_staff【{target_staff}】が見つかりません。確認して下さい。")
