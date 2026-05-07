import streamlit as st
import pandas as pd
import practice_0 as p0
import fitz  # PyMuPDF
import re
from googleapiclient.discovery import build
from google.oauth2 import service_account

# スプレッドシートID
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service():
    """GCP認証：Secretsから情報を取得"""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

def display_pdf_as_image(pdf_path):
    """エラー時にPDFを表示して停止するための処理"""
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        st.image(pix.tobytes("png"), caption="PDFプレビュー", use_container_width=True)
        doc.close()
    except Exception as e:
        st.warning(f"プレビュー生成失敗: {e}")

# --- アプリケーション設定 ---
st.set_page_config(page_title="Shift to Calendar", layout="wide")
st.title("シフト解析・カレンダー生成システム")

# 1. 時程表の事前読み込み
if 'time_dic' not in st.session_state:
    try:
        service = get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表の読み込みに失敗しました。認証情報を確認してください: {e}")
        st.stop()

# 2. PDFアップロード
uploaded_file = st.file_uploader("勤務予定表（PDF）をアップロードしてください", type="pdf")

if uploaded_file:
    # 一時保存
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getvalue())
    
    # ファイル名から年月抽出
    fname = uploaded_file.name
    match_y = re.search(r'(\d{4})', fname)
    match_m = re.search(r'(\d{1,2})', fname)
    
    y = int(match_y.group(1)) if match_y else None
    m = int(match_m.group(1)) if match_m else None
    
    # 年月が不明な場合の入力ボックス
    if not y or not m:
        col1, col2 = st.columns(2)
        y = col1.number_input("年", value=2026)
        m = col2.number_input("月", value=1, min_value=1, max_value=12)

    # 3. PDF解析（第一関門〜location特定）
    res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
    
    if not res:
        st.error(msg)
        display_pdf_as_image("temp.pdf")
        st.stop()
    
    location = res['location']
    
    # 4. 第2関門：勤務地照合
    if location not in st.session_state.time_dic:
        st.error(f"「{location}」は時程表に登録されていません。確認が必要です。")
        display_pdf_as_image("temp.pdf")
        st.stop()
    
    st.success(f"勤務地「{location}」を特定しました。")

    # 5. 第3関門：スタッフ選択とデータ辞書登録
    target_staff = st.selectbox("シフトカレンダーを作成するスタッフを選んで下さい。", options=["該当なし"] + res['staff_list'])
    
    if target_staff != "該当なし":
        # my_daily_shift / other_daily_shift の抽出
        shift_data = p0.extract_target_data(res['df'], target_staff, location)
        
        if shift_data:
            # セッションに辞書登録
            st.session_state.current_process = {
                "location": location,
                "time_schedule": st.session_state.time_dic[location],
                "my_daily_shift": shift_data['my_daily_shift'],
                "other_daily_shift": shift_data['other_daily_shift']
            }
            
            # 抽出データの確認表示
            st.write("---")
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("#### my_daily_shift")
                st.dataframe(st.session_state.current_process["my_daily_shift"], hide_index=True)
            with col_b:
                st.write("#### time_schedule")
                st.dataframe(st.session_state.current_process["time_schedule"], hide_index=True)

            # 6. メイン工程：カレンダー生成
            if st.button("カレンダーCSVを生成する"):
                final_rows = []
                my_shift = st.session_state.current_process["my_daily_shift"]
                other_shift = st.session_state.current_process["other_daily_shift"]
                t_schedule = st.session_state.current_process["time_schedule"]
                
                # 1日から末日まで巡回
                # 0列目は氏名なので 1列目から巡回
                for col_idx in range(1, my_shift.shape[1]):
                    target_date = f"{y}/{m:02d}/{col_idx:02d}"
                    shift_info = str(my_shift.iloc[0, col_idx]).strip().replace('\n', '')
                    detail_info = str(my_shift.iloc[1, col_idx]).strip().replace('\n', '')
                    
                    if not shift_info or shift_info == "なし":
                        continue
                    
                    # practice_0のメイン計算ロジックを呼び出し
                    p0.shift_cal(
                        target_staff, 
                        target_date, 
                        col_idx, 
                        shift_info, 
                        detail_info,
                        other_shift, 
                        t_schedule, 
                        final_rows
                    )
                
                # 結果の表示とダウンロード
                if final_rows:
                    cal_df = pd.DataFrame(final_rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
                    st.write("### 生成されたカレンダー予定")
                    st.dataframe(cal_df, use_container_width=True, hide_index=True)
                    
                    csv = cal_df.to_csv(index=False, encoding='utf_8_sig')
                    st.download_button(
                        label="CSVファイルを保存",
                        data=csv,
                        file_name=f"{y}{m:02d}_{target_staff}_calendar.csv",
                        mime="text/csv"
                    )
