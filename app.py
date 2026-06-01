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
    """GCP認証"""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

def display_pdf_as_image(pdf_path):
    """PDFを画像に変換して表示"""
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("png")
        st.image(img_bytes, caption="アップロードされたPDFの確認", use_container_width=True)
        doc.close()
    except Exception as e:
        st.warning(f"PDFプレビューの生成に失敗しました: {e}")

def stop_with_pdf_image_only(error_text, pdf_path):
    """エラー表示と画像表示のみを行い停止"""
    st.error(error_text)
    display_pdf_as_image(pdf_path)
    st.stop()


# --- Streamlit 画面表示構成 ---
st.set_page_config(page_title="シフトカレンダーシステム", layout="wide")
st.title("📅 シフトカレンダーシステム")

# [１]．時程表読込（【変更】画面への文言やエラー以外の案内は何も表示しない）
if "time_dic" not in st.session_state:
    try:
        service = get_service()
        # 読み込み処理のみを実行し、正常終了時のメッセージ表示(st.success等)は行わない
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}")
        st.stop()

# [2]．pdfシフト表ファイル読込
# <1>．pdfシフト表ファイルをアップロード
uploaded_file = st.file_uploader("PDFシフト予定表ファイルをアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # 一時ファイルとして保存
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_path = tmp_file.name

    filename = uploaded_file.name
    
    # 元々のベストな年月抽出ロジック（変更なし）
    match = re.search(r'(\d{4})[-_/年\s](\d{1,2})', filename)
    
    y = 0
    m = 0

    if match:
        # ① ファイル名から年月を取得できた場合
        y = int(match.group(1))
        m = int(match.group(2))
        st.info(f"📂 ファイル名から年月を取得しました: **{y}年{m}月**")
    else:
        # ② 取得できない場合はユーザーに入力して貰う
        st.warning("⚠️ ファイル名から年月を取得できませんでした。")
        st.markdown("### 「このファイルを使用しますか？ファイルの年月を入力してください。」")
        
        # pdfファイルを表示
        display_pdf_as_image(tmp_path)
        
        # 入力フォームを表示
        col1, col2 = st.columns(2)
        with col1:
            y = st.number_input("年（西暦4桁）を入力してください", min_value=2020, max_value=2040, value=2026, key="input_year")
        with col2:
            m = st.number_input("月（1〜12）を入力してください", min_value=1, max_value=12, value=1, key="input_month")

    # ③、④、⑤、⑥（第1関門：検証処理）
    if y > 0 and m > 0:
        # 第1関門の検証処理を実行
        success, result_msg = p0.check_first_gate(tmp_path, y, m)

        if success:
            # ⑤ A=Bならそのまま通過（成功メッセージを出さずに次の処理を待つ状態にする）
            pass
        else:
            # ⑥ A≠Bなら理由、及びpdfシフト表を表示してプログラム停止する
            stop_with_pdf_image_only(f"❌ 【第一関門不一致】プログラムを停止しました。\n\n理由:\n{result_msg}", tmp_path)

    # 一時ファイルの削除
    try:
        os.unlink(tmp_path)
    except:
        pass
