import streamlit as st
import practice_0 as p0
import fitz  # PyMuPDF
import re
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2 import service_account

# スプレッドシートID
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service():
    """GCP認証"""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('sheets', 'v4', credentials=creds), build('drive', 'v3', credentials=creds)

def display_pdf_as_image(pdf_path):
    """PDFを画像に変換して画面表示"""
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
    """エラーと画像のみを表示して処理を停止"""
    st.error(error_text)
    display_pdf_as_image(pdf_path)
    st.stop()

# --- UI設定 ---
st.title("🚗 シフトカレンダー自動生成システム")
st.write("Google Drive上の時程表モデルを利用し、PDFから『大枠予定』と『時間別予定』を確実に分離抽出します。")

uploaded_file = st.file_uploader("PDFシフト表ファイルをアップロードしてください", type=["pdf"])

# 年月選択ボックス
c1, c2 = st.columns(2)
year_input = c1.number_input("年を入力 (例: 2026)", min_value=2000, max_value=2100, value=2026)
month_input = c2.number_input("月を入力 (例: 1)", min_value=1, max_value=12, value=1)

if uploaded_file:
    with open("temp_shift.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
        
    # 1. Google Driveから時程表マスター辞書を直接構築（合体関数を呼び出し）
    try:
        sheets_service, drive_service = get_service()
        if "time_dic" not in st.session_state:
            st.session_state.time_dic = p0.time_schedule_from_drive(drive_service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表（Google Drive）の自動解析・同期に失敗しました: {e}")
        st.stop()

    # 2. 第1関門のチェック実行
    res, message = p0.check_first_stage("temp_shift.pdf", year_input, month_input)
    
    if message != "通過":
        stop_with_pdf_image_only(message, "temp_shift.pdf")
    else:
        location = res['location']
        
        # 【第2関門チェック】
        if location not in st.session_state.time_dic:
            stop_with_pdf_image_only(
                f"第2関門エラー: location「{location}」は時程表の勤務地キー(T1/T2)に設定されていません。確認が必要です。", 
                "temp_shift.pdf"
            )
            
        # 3. 第3関門: スタッフのプルダウン選択
        target_staff = st.selectbox(
            "シフトカレンダーを作成するスタッフを選んで下さい。", 
            options=["該当なし"] + res['staff_list']
        )
        
        if target_staff != "該当なし":
            # データの抽出実行
            shift_data = p0.extract_target_data(res['df'], target_staff, location)
            
            if shift_data:
                time_schedule_df = st.session_state.time_dic[location]
                my_daily_shift_df = shift_data['my_daily_shift']
                
                st.success(f"🎉 すべての関門を正常にクリアしました！ ({target_staff} / 勤務地: {location})")
                
                # 【カレンダー登録データ生成メイン工程（3．カレンダー登録）】
                calendar_df = p0.generate_calendar_records(
                    year_input, month_input, location, time_schedule_df, my_daily_shift_df
                )
                
                # 結果データフレームの表示
                st.write("### 📅 カレンダー登録用データリスト（完成予定）")
                st.write("1日の大枠予定と、エッジトリガーで検出された時間別予定が理想的なセット構造で生成されています。")
                st.dataframe(calendar_df, use_container_width=True)
                
            else:
                stop_with_pdf_image_only("指定されたスタッフのデータ抽出に失敗しました。", "temp_shift.pdf")
