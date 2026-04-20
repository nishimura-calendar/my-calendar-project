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
    # 全角を半角に、濁点などを結合
    text = unicodedata.normalize('NFKC', text)
    # 改行、空白、記号を完全に削除
    clean = re.sub(r'[\s　\n\r\t\.\,・\-|_]', '', text).lower()
    return clean

def is_name_match(target_name, text_to_check):
    """
    名前の全文字が含まれているか判定。
    順番がバラバラでも、改行で泣き別れていても検知します。
    """
    clean_target = normalize_text(target_name)
    clean_cell = normalize_text(text_to_check)
    
    if not clean_target or not clean_cell:
        return False
        
    # 「西」「村」「文」「宏」が全て含まれているか
    match_count = sum(1 for char in clean_target if char in clean_cell)
    return match_count >= len(clean_target)

# --- 2. ファイル名から「期待値」を取得 ---
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

# --- 3. カレンダー整合性チェック ---
def verify_pdf_calendar(df, expected_year, expected_month):
    if not expected_year or not expected_month:
        return False, "年月特定不能", "Unknown"

    first_wday_idx, last_day = calendar.monthrange(expected_year, expected_month)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_first_wday = weekdays_jp[first_wday_idx]
    
    pdf_days = []
    # 全列をスキャンして日付行を探す（1行目とは限らないため）
    for r in range(min(3, len(df))):
        for col in range(1, df.shape[1]):
            cell_val = str(df.iloc[r, col])
            d_match = re.search(r'(\d+)', cell_val)
            w_match = re.search(r'([月火水木金土日])', cell_val)
            if d_match and w_match:
                pdf_days.append({"d": int(d_match.group(1)), "w": w_match.group(1)})
        if pdf_days: break

    if not pdf_days:
        return False, "日付行が認識できません", "Unknown"

    actual_max_day = max([x["d"] for x in pdf_days])
    day_one = next((x for x in pdf_days if x["d"] == 1), None)
    actual_first_wday = day_one["w"] if day_one else "不明"

    # UI表示
    st.markdown("### 📊 ファイル整合性チェック")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**【期待値】** {expected_year}年{expected_month}月 / 1日:{expected_first_wday}")
    with col2:
        st.write(f"**【実測値】** 最大{actual_max_day}日 / 1日:{actual_first_wday}")

    is_match = (actual_max_day == last_day) and (actual_first_wday == expected_first_wday)
    header_cell = str(df.iloc[0, 0])
    work_place = "第2ターミナル" if "第2" in header_cell or "T2" in header_cell else "免税店"

    return is_match, "OK", work_place

# --- 4. メイン解析 ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    pdf_stream.seek(0)
    year, month = extract_year_month_from_filename(file_name)
    
    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        # flavor='lattice'（罫線重視）で読み込み
        tables = camelot.read_pdf(temp_path, pages='all', flavor='lattice')
    except Exception as e:
        st.error(f"解析失敗: {e}")
        return {}, year, month

    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if df.empty: continue
        
        is_valid, _, work_place = verify_pdf_calendar(df, year, month)
        if not is_valid: continue

        found = False
        all_text_rows = []

        for i in range(len(df)):
            # ★最重要変更点：1列目だけでなく、行全体の文字を合体させて検索
            # これにより、名前が列をはみ出していたり、日付と混ざっていても検知可能
            full_row_text = "".join(df.iloc[i, :].astype(str))
            
            # 2行セットで名前が泣き別れている可能性も考慮
            next_row_text = "".join(df.iloc[i+1, :].astype(str)) if i+1 < len(df) else ""
            combined_search_area = full_row_text + next_row_text
            
            all_text_rows.append(full_row_text[:50] + "...") # デバッグ用

            if is_name_match(target_staff, combined_search_area):
                # 発見：自分用2行、他人用は除外
                my_daily = df.iloc[i : i + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, i, i+1] if i+1 < len(df) else [0, i]).copy().reset_index(drop=True)
                table_dictionary[work_place] = [my_daily, others]
                found = True
                break
        
        if found:
            st.success(f"👤 '{target_staff}' さんの行を特定しました。")
        else:
            st.warning(f"'{target_staff}' 様の名前を行データから検出できませんでした。")
            with st.expander("🔍 PDFから読み取られた各行の先頭データ"):
                for idx, txt in enumerate(all_text_rows):
                    st.text(f"行 {idx}: {txt}")
                
    return table_dictionary, year, month

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
