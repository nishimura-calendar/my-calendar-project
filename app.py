import streamlit as st
import practice_0 as p0
import fitz  # PyMuPDF
import re
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

# メインUI画面
st.title("📅 シフト管理・カレンダー生成システム")

# PDFファイルのアップロード
uploaded_file = st.file_uploader("PDFシフト表ファイルをアップロードしてください", type=["pdf"])

# 年月入力UI
c1, c2 = st.columns(2)
year_input = c1.number_input("年を入力", min_value=2000, max_value=2100, value=2026)
month_input = c2.number_input("月を入力", min_value=1, max_value=12, value=1)

if uploaded_file:
    with open("temp_shift.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
        
    try:
        service = get_service()
        if "time_dic" not in st.session_state:
            st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表マスターの取得に失敗しました: {e}")
        st.stop()

    # 第1関門チェック
    res, message = p0.check_first_stage("temp_shift.pdf", year_input, month_input)
    
    if message != "通過":
        stop_with_pdf_image_only(message, "temp_shift.pdf")
    else:
        location = res['location']
        
        # 【第2関門チェック】 勤務地が時程表に設定されていません。確認が必要です。
        if location not in st.session_state.time_dic:
            error_msg = f"勤務地-{location}-が時程表に設定されていません。確認が必要です。"
            stop_with_pdf_image_only(error_msg, "temp_shift.pdf")
            
        target_staff = st.selectbox("シフトカレンダーを作成するスタッフを選んで下さい。", options=["該当なし"] + res['staff_list'])
        
        if target_staff != "該当なし":
            # データの抽出実行
            shift_data = p0.extract_target_data(res['df'], target_staff, location)
            
            if shift_data:
                # 仕様に基づき、勤務地(location)をキーとして辞書登録
                st.session_state.final_result = {
                    location: {
                        "time_schedule": st.session_state.time_dic[location],
                        "my_daily_shift": shift_data['my_daily_shift'],
                        "other_daily_shift": shift_data['other_daily_shift']
                    }
                }
                
                # 表示処理
                st.write(f"### {target_staff} の抽出結果（勤務地: {location}）")
                
                st.write("#### time_schedule")
                st.dataframe(st.session_state.final_result[location]["time_schedule"], hide_index=True)
                
                st.write("#### my_daily_shift")
                st.dataframe(st.session_state.final_result[location]["my_daily_shift"], hide_index=True)
                
                st.write("#### other_daily_shift")
                st.dataframe(st.session_state.final_result[location]["other_daily_shift"], hide_index=True)
                
                # --- [3] カレンダー自動生成連携 ---
                st.write("---")
                st.write("### 📆 3．カレンダー登録（CSV出力結果）")
                
                time_schedule_df = st.session_state.final_result[location]["time_schedule"]
                my_daily_shift_df = st.session_state.final_result[location]["my_daily_shift"]
                other_staff_shift_df = st.session_state.final_result[location]["other_daily_shift"]
                
                calendar_df = p0.generate_calendar_records(
                    year_input, month_input, location, time_schedule_df, my_daily_shift_df, other_staff_shift_df
                )
                
                st.dataframe(calendar_df, use_container_width=True, hide
