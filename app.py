import streamlit as st
import camelot
import re
import calendar
import pandas as pd
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- 1. 時程表読み込み (IDを固定) ---
def time_schedule_from_drive(service, file_id="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"):
    """
    指定IDのスプレッドシートから勤務地Keyと時間行を抽出して辞書化する
    """
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    downloader.next_chunk()
    fh.seek(0)
    
    # 形式に従い読み込み
    df = pd.read_excel(fh, header=None, dtype=str).fillna('')
    
    # A列に勤務地(T1, T2等)がある行を特定
    location_rows = df[df.iloc[:, 0].str.strip() != ''].index.tolist()
    location_data_dic = {}
    
    for i, start_row in enumerate(location_rows):
        key = df.iloc[start_row, 0].strip()
        end_row = location_rows[i+1] if i+1 < len(location_rows) else len(df)
        # 範囲内のデータを辞書へ (詳細な時間変換ロジックはここへ追加)
        location_data_dic[key] = df.iloc[start_row:end_row, :]
        
    return location_data_dic

# --- 2. 第1・第2関門突破ロジック ---
def get_last_date_from_filename(filename):
    """A: ファイル名から年月を取得し、最終日と最終曜日を算出"""
    match = re.search(r'20(\d{2})年?(\d{1,2})月', filename)
    if not match:
        return None, None
    year = int(f"20{match.group(1)}")
    month = int(match.group(2))
    _, last_day = calendar.monthrange(year, month)
    last_weekday = calendar.weekday(year, month, last_day)
    return last_day, last_weekday

def get_last_date_from_pdf(pdf_path):
    """B: PDFのkey行から最終日と最終曜日を抽出"""
    # PDFを読み込み（抽出ロジックはレイアウトに依存するため適宜調整）
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    df = tables[0].df
    
    # 日付と曜日が含まれる行を抽出するロジック
    # (例: セル内の数値と曜日文字列を探す)
    all_cells = df.astype(str).values.flatten()
    days = [int(n) for cell in all_cells for n in re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', cell)]
    
    # 最終日(最大値)
    last_day = max(days) if days else 0
    # 最終曜日(ロジックにより抽出)
    # ※PDFデータから曜日文字列を抽出する処理をここに記述
    last_weekday = 5 # 仮の値(土曜日)
    
    return last_day, last_weekday

def stop_and_display_pdf(pdf_path, msg):
    """PDFを表示してプログラムを停止"""
    st.error(msg)
    with open(pdf_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    st.markdown(f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>', unsafe_allow_html=True)
    st.stop()

# --- メインロジック ---
def validate_process(uploaded_file):
    pdf_path = "temp.pdf"
    with open(pdf_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
        
    last_day_A, last_weekday_A = get_last_date_from_filename(uploaded_file.name)
    last_day_B, last_weekday_B = get_last_date_from_pdf(pdf_path)
    
    # 判定
    if last_day_A != last_day_B or last_weekday_A != last_weekday_B:
        msg = (
            f"A≠Bです。不一致のため処理を停止します。\n\n"
            f"【算出データ(A)】最終日: {last_day_A}, 最終曜日: {last_weekday_A}\n"
            f"【抽出データ(B)】最終日: {last_day_B}, 最終曜日: {last_weekday_B}"
        )
        stop_and_display_pdf(pdf_path, msg)
    else:
        st.success("A=Bを確認しました。通過します。")
