import streamlit as st
import practice_0 as p0
import fitz  # PyMuPDF
import re
from googleapiclient.discovery import build
from google.oauth2 import service_account

# スプレッドシートID
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
# CSV保存先Google DriveフォルダID 
DRIVE_FOLDER_ID = "19GBObKKJQylZXLaxfApt3iSgA1893TKa"

def get_services():
    """GCP認証 (Sheets API と Drive API を取得)"""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive"  # カレンダーCSVの保存に必要
        ]
    )
    sheets_service = build('sheets', 'v4', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return sheets_service, drive_service

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

st.set_page_config(layout="wide")

# 1. 時程表の事前読込とサービス初期化
if 'time_dic' not in st.session_state:
    try:
        sheets_svc, drive_svc = get_services()
        st.session_state.drive_service = drive_svc
        st.session_state.time_dic = p0.load_master_from_sheets(sheets_svc, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込または認証に失敗: {e}"); st.stop()

# 2. PDFアップロード
uploaded_file = st.file_uploader("PDFシフト表を選択してください", type="pdf")

if uploaded_file:
    pdf_bytes = uploaded_file.getvalue()
    with open("temp.pdf", "wb") as f:
        f.write(pdf_bytes)

    fname = uploaded_file.name
    match_y, match_m = re.search(r'(\d{4})', fname), re.search(r'(\d{1,2})', fname)
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    if y is None or m is None:
        st.warning("年月を入力してください。")
        y = st.number_input("年", value=2026); m = st.number_input("月", min_value=1, max_value=12)
        is_ready = st.button("ファイル確認")
    else: 
        is_ready = True

    if is_ready:
        # 第1関門
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        
        if res is None:
            error_msg = f"ファイル名【{fname}】とファイル内容に相違があります。確認して下さい。\n\n理由：{msg}"
            stop_with_pdf_image_only(error_msg, "temp.pdf")

        # 第2関門
        location = res['location']
        if location not in st.session_state.time_dic:
            stop_with_pdf_image_only(f"【{location}】は時程表の勤務地には設定されていません。確認が必要です。", "temp.pdf")
        
        # 第3関門
        st.success(f"勤務地「{location}」の照合に成功しました。")
        target_staff = st.selectbox("シフトカレンダーを作成するスタッフを選んで下さい。", options=["該当なし"] + res['staff_list'])
        
        if target_staff != "該当なし":
            shift_data = p0.extract_target_data(res['df'], target_staff, location)
            
            if shift_data:
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
                
                # [3] カレンダー登録 [cite: 2]
                st.write("---")
                st.write("### カレンダー連携")
                if st.button("カレンダー用CSVを作成しDriveへ保存"):
                    with st.spinner("CSVを作成し保存しています..."):
                        try:
                            saved_files = p0.create_and_upload_calendar_csv(
                                st.session_state.drive_service,
                                DRIVE_FOLDER_ID,
                                y, m, location,
                                st.session_state.final_result[location]["my_daily_shift"],
                                st.session_state.final_result[location]["time_schedule"]
                            )
                            st.success("1年保存用のカレンダーCSVをGoogle Driveに保存しました。")
                            for f_name, f_id in saved_files.items():
                                st.write(f"- `{f_name}` (File ID: {f_id})")
                        except Exception as e:
                            st.error(f"保存中にエラーが発生しました: {e}")
            else:
                stop_with_pdf_image_only("target_staffが見つかりません。確認して下さい。", "temp.pdf")
