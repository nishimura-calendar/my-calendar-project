import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

# --- 1. テキストの正規化 ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    clean = re.sub(r'[\s　\n\r\t\.\,・-]', '', text).lower()
    return clean

# --- 2. ファイル名から「正解」の年月を取得 ---
def extract_year_month_from_filename(file_name):
    if not file_name: return None, None
    text = normalize_text(file_name)
    y_val, m_val = None, None
    
    month_match = re.search(r'(\d{1,2})月', text)
    if month_match:
        m_val = int(month_match.group(1))
    
    nums = re.findall(r'\d+', text)
    for n in nums:
        if len(n) == 4:
            y_val = int(n)
            break
    return y_val, m_val

# --- 3. 日数と曜日の精密判定および表示ロジック ---
def verify_pdf_calendar(df, expected_year, expected_month):
    """
    ファイル名から算出した「正解」と、PDFの中身を比較判定し、結果を表示する。
    """
    if not expected_year or not expected_month:
        return False, "ファイル名から年月を特定できませんでした。", None

    # --- A. 暦上の「期待値（正解）」を計算 ---
    first_wday_idx, last_day = calendar.monthrange(expected_year, expected_month)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_first_wday = weekdays_jp[first_wday_idx]
    
    # --- B. PDFの0行目から「実測値」を抽出 ---
    pdf_days = []
    for col in range(1, df.shape[1]):
        cell_val = normalize_text(str(df.iloc[0, col]))
        d_match = re.search(r'(\d+)', cell_val)
        w_match = re.search(r'([月火水木金土日])', cell_val)
        if d_match and w_match:
            pdf_days.append({"day": int(d_match.group(1)), "wday": w_match.group(1)})

    if not pdf_days:
        return False, "PDFの1行目から日付・曜日を読み取れませんでした。", None

    # 実測値の初日と末日
    max_day_in_pdf = max([x["day"] for x in pdf_days])
    day_one = next((x for x in pdf_days if x["day"] == 1), None)
    actual_first_wday = day_one["wday"] if day_one else "不明"

    # --- C. 画面表示（デバッグ用） ---
    with st.expander("📅 カレンダー整合性チェック詳細"):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**【ファイル名からの期待値】**")
            st.write(f"対象年月: {expected_year}年{expected_month}月")
            st.write(f"期待される日数: {last_day}日")
            st.write(f"1日の曜日: {expected_first_wday}")
        with col2:
            st.markdown("**【PDFデータからの実測値】**")
            st.write(f"読み取れた最大日数: {max_day_in_pdf}日")
            st.write(f"読み取れた1日の曜日: {actual_first_wday}")

        if (max_day_in_pdf == last_day) and (actual_first_wday == expected_first_wday):
            st.success("✅ ファイル名とPDF内容が一致しました。")
        else:
            st.warning("⚠️ 整合性チェックに不一致があります。正しいページか確認してください。")

    # 一致判定の最終結果
    if actual_first_wday != expected_first_wday:
        return False, "1日の曜日が不一致です。", None
    if max_day_in_pdf != last_day:
        return False, "月末の日数が不一致です。", None

    header_raw = str(df.iloc[0, 0])
    header_lines = header_raw.splitlines()
    work_place = header_lines[len(header_lines)//2].strip() if header_lines else "Unknown"

    return True, "一致確認済み", work_place

# --- 4. メイン解析関数 ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    
    year, month = extract_year_month_from_filename(file_name)
    
    temp_path = "current_target.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf(temp_path, pages='all', flavor='lattice')
    except Exception as e:
        st.error(f"Camelotエラー: {e}")
        return {}, year, month

    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # 整合性チェックと表示を実行
        is_valid, message, work_place = verify_pdf_calendar(df, year, month)
        
        if not is_valid:
            continue

        # 名前検索
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        matched_indices = [i for i, v in enumerate(search_col) if len(v) > 1 and (clean_target in v or v in clean_target)]
        
        if matched_indices:
            idx = matched_indices[0]
            my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
            others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
            table_dictionary[work_place] = [my_daily, others]
                
    return table_dictionary, year, month

# --- 5. Google Drive 連携 ---
def time_schedule_from_drive(service, spreadsheet_id):
    try:
        request = service.files().export_media(fileId=spreadsheet_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return pd.read_excel(fh, header=None, engine='openpyxl').fillna('')
    except:
        return pd.DataFrame()
