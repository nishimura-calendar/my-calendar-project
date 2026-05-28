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
    """GCP認証を行いサービスを生成"""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

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

# --- Streamlit アプリケーション画面 ---
st.title("🚗 シフトカレンダー自動生成システム")
st.write("手順書に従い、時程表マスターとPDFシフト表を照合し、Googleカレンダー形式のインポートデータを生成します。")

# PDFファイルのアップロード
uploaded_file = st.file_uploader("PDFシフト表ファイルをアップロードしてください", type=["pdf"])

# 年月選択のUI
c1, c2 = st.columns(2)
year_input = c1.number_input("年を入力 (例: 2026)", min_value=2000, max_value=2100, value=2026)
month_input = c2.number_input("月を入力 (例: 1)", min_value=1, max_value=12, value=1)

if uploaded_file:
    # 一時ファイルとして書き込み
    with open("temp_shift.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
        
    # 1. [１] 時程表読込マスターデータの自動取得
    try:
        service = get_service()
        if "time_dic" not in st.session_state:
            st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表（Googleスプレッドシート）の読み込みに失敗しました: {e}")
        st.stop()

    # 2. [2] <1> 第1関門のチェック実行
    res, message = p0.check_first_stage("temp_shift.pdf", year_input, month_input)
    
    if message != "通過":
        stop_with_pdf_image_only(message, "temp_shift.pdf")
    else:
        location = res['location']
        
        # 4. [2] <2> (2) 第2関門チェック修正
        # 指定された勤務地(C)が時程表のkeyに含まれない場合、PDFを表示した上で指定の文言で停止
        if location not in st.session_state.time_dic:
            error_msg = f"勤務地-{location}-が時程表に設定されていません。確認が必要です。"
            stop_with_pdf_image_only(error_msg, "temp_shift.pdf")
            
        # 5. 第3関門: スタッフのプルダウン選択
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
                other_staff_shift_df = shift_data['other_daily_shift']
                
                st.success(f"🎉 すべての関門をクリアしました！ ({target_staff} / 勤務地: {location})")
                
                # 6. [3] カレンダー登録データの生成
                calendar_df = p0.generate_calendar_records(
                    year_input, month_input, location, time_schedule_df, my_daily_shift_df, other_staff_shift_df
                )
                
                # カレンダーCSVデータのプレビュー表示
                st.write("### 📅 Googleカレンダー登録用データ（完成）")
                st.write("手順書の仕様（本町の2重登録、エッジトリガー、退勤結合）に基づき作成された、インポート用の8列CSV形式データです。")
                st.dataframe(calendar_df, use_container_width=True, hide_index=True)
                
                # CSVダウンロードボタンの設置
                csv_data = calendar_df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 Googleカレンダー用CSVをダウンロード",
                    data=csv_data,
                    file_name=f"shift_calendar_{year_input}_{month_input}_{target_staff}.csv",
                    mime="text/csv"
                )
            else:
                stop_with_pdf_image_only("指定されたスタッフのデータ抽出に失敗しました。", "temp_shift.pdf")
