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
    """PDFの1ページ目を画像に変換して画面に確認プレビュー表示"""
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("png")
        st.image(img_bytes, caption="アップロードされたPDFのプレビュー", use_container_width=True)
        doc.close()
    except Exception as e:
        st.warning(f"PDFプレビューの画像生成に失敗しました: {e}")

def stop_with_pdf_image_only(error_text, pdf_path):
    """エラーメッセージとPDF画像のみを表示して処理を安全に停止（関門失敗時）"""
    st.error(error_text)
    display_pdf_as_image(pdf_path)
    st.stop()


# --- Streamlit アプリケーション画面構成 ---
st.set_page_config(page_title="シフトCSV自動生成システム", layout="wide")
st.title("📅 シフトカレンダー CSV自動生成システム")

# [1] 時程表マスターの自動読み込み
if "time_master" not in st.session_state:
    try:
        with st.spinner("Googleスプレッドシートから時程表マスターをロード中..."):
            service = get_service()
            st.session_state.time_master = p0.load_master_from_sheets(service, SPREADSHEET_ID)
        st.success("時程表マスターの読み込みが完了しました。")
    except Exception as e:
        st.error(f"時程表読込失敗: {e}")
        st.stop()

# [2] PDFファイルアップロード
uploaded_file = st.file_uploader("PDFシフト予定表ファイルをアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # 一時ファイルとして書き込み
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_path = tmp_file.name

    # ファイル名から年月の抽出を自動試行
    filename = uploaded_file.name
    match_year_month = re.search(r'(\d{4})[-_/年\s](\d{1,2})', filename)
    
    if match_year_month:
        y = int(match_year_month.group(1))
        m = int(match_year_month.group(2))
        st.info(f"📂 ファイル名から自動検知: **{y}年{m}月度** のデータを解析します。")
    else:
        st.warning("ファイル名から年月を自動判定できませんでした。")
        col1, col2 = st.columns(2)
        with col1:
            y = st.number_input("年（西暦4桁）を手入力", min_value=2020, max_value=2040, value=2026)
        with col2:
            m = st.number_input("月（1〜12）を手入力", min_value=1, max_value=12, value=1)

    # PDFの構造解析と関門検証
    with st.spinner("PDFファイルを解析中..."):
        parse_result, status = p0.analyze_pdf_structure(tmp_path, y, m)

    # 【第1関門】月末日・曜日の照合検証
    if parse_result is None:
        stop_with_pdf_image_only(f"【第1関門失敗】 {status}", tmp_path)

    # 抽出された純粋な勤務地コード(C)の取得
    location_c = parse_result["location"]
    master_keys = list(st.session_state.time_master.keys())

    # 【第2関門】勤務地キーの完全一致照合検証
    if location_c not in master_keys:
        error_msg = f"【第2関門失敗】 勤務地「{location_c}」が時程表マスターに登録されていません。確認が必要です。(登録済キー: {master_keys})"
        stop_with_pdf_image_only(error_msg, tmp_path)

    # 関門通過時のUI表示
    st.success(f"🎉 すべての関門をクリア！ 勤務地キー: **{location_c}**")
    
    # 解析したDataFrameとスタッフ名を保持
    st.session_state.current_df = parse_result["df"]
    st.session_state.staff_list = parse_result["staff_list"]

    # [3] 対象スタッフのセレクトボックス
    st.write("---")
    st.write("### 👥 対象スタッフの選択")
    target_staff = st.selectbox("カレンダーデータを生成するスタッフを選択してください", st.session_state.staff_list)

    if target_staff:
        # 【第3関門】選択された本人のシフトと他スタッフのシフトを分離
        extracted = p0.extract_target_data(st.session_state.current_df, target_staff, location_c)
        
        if extracted:
            st.write(f"### 📆 **{target_staff}** のカレンダー用データ構築")
            
            if st.button("Googleカレンダー登録用CSVの生成"):
                time_schedule_df = st.session_state.time_master[location_c]
                my_daily_shift_df = extracted["my_daily_shift"]
                other_staff_shift_df = extracted["other_daily_shift"]
                
                # CSVマトリクス生成
                calendar_df = p0.generate_calendar_records(
                    y, m, location_c, time_schedule_df, my_daily_shift_df, other_staff_shift_df
                )
                st.session_state.calendar_df = calendar_df
                st.success("カレンダーCSVのデータ作成に成功しました。")

            # プレビュー表示およびダウンロードコンポーネント
            if "calendar_df" in st.session_state:
                st.write("#### 📋 Googleカレンダー用CSVプレビュー")
                st.dataframe(st.session_state.calendar_df, use_container_width=True, hide_index=True)
                
                csv_bytes = st.session_state.calendar_df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 Googleカレンダー用CSVをダウンロード",
                    data=csv_bytes,
                    file_name=f"google_calendar_{y}_{m}_{target_staff}.csv",
                    mime="text/csv"
                )
        else:
            st.error(f"エラー: 「{target_staff}」のシフトデータをマトリクス内から分離できませんでした。")

    # ファイルポインタ解放・一時ファイルの安全クリーンアップ
    try:
        os.unlink(tmp_path)
    except:
        pass
