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

st.set_page_config(layout="wide")

# 1. 時程表の事前読込
if 'time_dic' not in st.session_state:
    try:
        service = get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}"); st.stop()

# 2. PDFアップロード
st.title("📅 シフト管理・カレンダー生成システム")
uploaded_file = st.file_uploader("PDFシフト表を選択してください", type="pdf")

if uploaded_file:
    pdf_bytes = uploaded_file.getvalue()
    with open("temp.pdf", "wb") as f:
        f.write(pdf_bytes)

    fname = uploaded_file.name
    match_y = re.search(r'(\d{4})', fname)
    match_m = re.search(r'(\d{1,2})', fname)
    
    # ファイル名から年月を取得できたか判定
    if match_y and match_m:
        y = int(match_y.group(1))
        m = int(match_m.group(1))
        is_ready = True
    else:
        # 指示反映：ファイル名から年月が取得できない場合、PDFを表示した上で指定メッセージと入力フォームを出す
        display_pdf_as_image("temp.pdf")
        st.warning("「このファイルを使用しますか？ファイルの年月を入力してください。」")
        c1, c2 = st.columns(2)
        y = c1.number_input("年", value=2026, key="manual_year")
        m = c2.number_input("月", min_value=1, max_value=12, value=1, key="manual_month")
        is_ready = st.button("ファイル確認")

    if is_ready:
        # 第1関門 (月末の日付と曜日の一致チェック)
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        
        if res is None:
            error_msg = f"ファイル名【{fname}】とファイル内容に相違があります。確認して下さい。\n\n理由：{msg}"
            stop_with_pdf_image_only(error_msg, "temp.pdf")

        # 第2関門
        location = res['location']
        if location not in st.session_state.time_dic:
            stop_with_pdf_image_only(f"勤務地-【{location}】-が時程表に設定されていません。確認が必要です。", "temp.pdf")
        
        # 指示反映：「照合に成功しました」メッセージは必要なしのためカット
        target_staff = st.selectbox("シフトカレンダーを作成するスタッフを選んで下さい。", options=["該当なし"] + res['staff_list'])
        
        if target_staff != "該当なし":
            # データの抽出実行
            shift_data = p0.extract_target_data(res['df'], target_staff, location)
            
            if shift_data:
                # ⑤ 勤務地をkeyとして各データを辞書登録
                st.session_state.final_result = {
                    location: {
                        "time_schedule": st.session_state.time_dic[location],
                        "my_daily_shift": shift_data['my_daily_shift'],
                        "other_daily_shift": shift_data['other_daily_shift']
                    }
                }
                
                # 指示反映：⑤の辞書登録の後、中間データの表示処理は飛ばしてそのまま進む
                
                # --- [3] カレンダー登録自動生成セクション ---
                st.write("---")
                st.write(f"### 📆 {target_staff} のカレンダー登録用データの作成")
                
                if st.button("Googleカレンダー登録用データを生成"):
                    time_schedule_df = st.session_state.final_result[location]["time_schedule"]
                    my_daily_shift_df = st.session_state.final_result[location]["my_daily_shift"]
                    other_staff_shift_df = st.session_state.final_result[location]["other_daily_shift"]
                    
                    calendar_df = p0.generate_calendar_records(
                        y, m, location, time_schedule_df, my_daily_shift_df, other_staff_shift_df
                    )
                    
                    st.session_state.calendar_df = calendar_df
                    st.success("カレンダー用データの生成に成功しました！")

                if "calendar_df" in st.session_state:
                    st.write("#### カレンダー登録用CSVプレビュー")
                    st.dataframe(st.session_state.calendar_df, use_container_width=True, hide_index=True)
                    
                    csv_bytes = st.session_state.calendar_df.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📥 Googleカレンダー用CSVをダウンロード",
                        data=csv_bytes,
                        file_name=f"google_calendar_{y}_{m}_{target_staff}.csv",
                        mime="text/csv"
                    )
            else:
                stop_with_pdf_image_only("target_staffが見つかりません。確認して下さい。", "temp.pdf")
