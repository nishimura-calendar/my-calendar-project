import streamlit as st
import practice_0 as p0
import fitz  # PyMuPDF
import re
import tempfile
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account

# スプレッドシートID
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service():
    """GCP認証を行いGoogle Sheets APIサービスをビルド"""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

def display_pdf_as_image(pdf_path):
    """PDFファイルを画面に表示する（確認プレビュー用）"""
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("png")
        st.image(img_bytes, caption="アップロードされたPDFシフト表", use_container_width=True)
        doc.close()
    except Exception as e:
        st.warning(f"PDFの表示に失敗しました: {e}")


# --- Streamlit 画面表示構成 ---
st.set_page_config(page_title="シフトカレンダーシステム", layout="wide")
st.title("📅 シフトカレンダー（第一関門）")

# [1] 時程表読込
if "time_master" not in st.session_state:
    try:
        service = get_service()
        # 内部での読み込みのみ（成功メッセージは表示しない）
        st.session_state.time_master = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}")
        st.stop()

# [2] pdfシフト表ファイル読込
# <1>．pdfシフト表ファイルをアップロード
uploaded_file = st.file_uploader("PDFシフト予定表ファイルをアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # 読み込み用の一時ファイルを作成
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_path = tmp_file.name

    # ① pdfシフト表ファイル名から年月を取得。
    filename = uploaded_file.name
    match_year_month = re.search(r'(\d{4})[-_/年\s](\d{1,2})', filename)
    
    # 構文エラーの起きない安全な初期化
    y = 0
    m = 0

    if match_year_month:
        # ① ファイル名から年月が取得できる場合は、②を自動で飛ばして③へ直行
        y = int(match_year_month.group(1))
        m = int(match_year_month.group(2))
        st.info(f"📂 ファイル名から年月を取得しました: **{y}年{m}月**")
    else:
        # ① ファイル名から年月が取得できない場合は②を実行
        # ② 取得できない場合はユーザーに入力して貰う。
        st.warning("⚠️ ファイル名から年月を取得できませんでした。")
        st.markdown("### 「このファイルを使用しますか？ファイルの年月を入力してください。」")
        
        # pdfファイルを表示。
        display_pdf_as_image(tmp_path)
        
        # 入力フォームを表示。
        col1, col2 = st.columns(2)
        with col1:
            y = st.number_input("年（西暦4桁）を入力してください", min_value=2020, max_value=2040, value=2026, key="input_year")
        with col2:
            m = st.number_input("月（1〜12）を入力してください", min_value=1, max_value=12, value=1, key="input_month")

    # ③、④、⑤、⑥（検証と判定処理）
    if y > 0 and m > 0:
        # 第1関門の検証処理を実行
        success, result_msg = p0.check_first_gate(tmp_path, y, m)

        if success:
            # ⑤ A=Bならそのまま通過（成功のログテキストは出さず、安全な通過サインのみ）
            st.success("🤝 第一関門を通過しました。")
        else:
            # ⑥ A≠Bなら理由、及びpdfシフト表を表示してプログラム停止する
            st.error(f"❌ 【第一関門不一致】プログラムを停止しました。\n\n理由:\n{result_msg}")
            # ②でまだPDFを表示していない場合（ファイル名から自動取得した際にエラーになった場合）のみここでPDFを表示
            if match_year_month:
                display_pdf_as_image(tmp_path)
            st.stop()

    # 一時ファイルの削除
    try:
        os.unlink(tmp_path)
    except:
        pass
