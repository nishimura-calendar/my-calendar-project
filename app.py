import streamlit as st
import practice_0 as p0
import fitz  # PyMuPDF
import re
import tempfile
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account

# スプレッドシートID（固定マスタ）
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
st.title("📅 シフトカレンダー（第一関門まで）")

# ==========================================================
# [1]．時程表読込
# ==========================================================
if "time_master" not in st.session_state:
    try:
        service = get_service()
        # マスタの読み込み（バックグラウンドで保持、成功ログは出さない）
        st.session_state.time_master = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}")
        st.stop()

# ==========================================================
# [2]．pdfシフト表ファイル読込 ＞ <1>．pdfシフト表ファイルをアップロード
# ==========================================================
uploaded_file = st.file_uploader("PDFシフト予定表ファイルをアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # 読込・検証用の一時ファイルを作成
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_path = tmp_file.name

    # ------------------------------------------------------
    # (3)．第１関門
    # ------------------------------------------------------
    # ① pdfシフト表ファイル名から年月を取得。
    filename = uploaded_file.name
    match_year_month = re.search(r'(\d{4})[-_/年\s](\d{1,2})', filename)
    
    # 年月の初期値設定
    y = 0
    m = 0

    if match_year_month:
        # ① ファイル名から年月が取得できる場合は、②を自動でスキップして③へ直行する
        y = int(match_year_month.group(1))
        m = int(match_year_month.group(2))
        st.info(f"📂 ファイル名から年月を自動抽出しました: **{y}年{m}月**")
    else:
        # ① ファイル名から年月が取得できない場合は、②を実行してから③へ進む
        st.warning("⚠️ ファイル名から年月を取得できませんでした。")
        
        # ② 取得できない場合はユーザーに入力して貰う。
        st.markdown("### 「このファイルを使用しますか？ファイルの年月を入力してください。」")
        
        # pdfファイルを表示。
        display_pdf_as_image(tmp_path)
        
        # 入力フォームを表示。
        col1, col2 = st.columns(2)
        with col1:
            y = st.number_input("年（西暦4桁）を入力してください", min_value=2020, max_value=2040, value=2026, key="input_year")
        with col2:
            m = st.number_input("月（1〜12）を入力してください", min_value=1, max_value=12, value=1, key="input_month")

    # ------------------------------------------------------
    # 検証と判定処理（③、④、⑤、⑥）
    # ------------------------------------------------------
    if y > 0 and m > 0:
        # ③ A：取得した年月から最終日付と最終曜日を取得する
        # ④ B：詠込んだpdfシフト表ファイルから最終日付と最終曜日を取得する
        # （上記は practice_0.py 内の check_first_gate で突合検証されます）
        success, result_msg = p0.check_first_gate(tmp_path, y, m)

        if success:
            # ⑤ A=Bならそのまま通過（次の実装に備えて安全な通過メッセージのみ表示）
            st.success("🤝 第一関門をクリアしました。次のステップへ進めます。")
            
            # --- 今後、この下に [2] <2>（第2関門・勤務地抽出処理）を追記していきます ---
            
        else:
            # ⑥ A≠Bなら理由、及びpdfシフト表を表示してプログラム停止する
            st.error(f"❌ 【第一関門不一致】プログラムを停止しました。\n\n理由:\n{result_msg}")
            
            # ②でまだPDFを表示していない（ファイル名自動取得でエラーになった）場合のみ、ここでPDFを表示
            if match_year_month:
                display_pdf_as_image(tmp_path)
            st.stop()

    # 一時ファイルの削除
    try:
        os.unlink(tmp_path)
    except:
        pass
