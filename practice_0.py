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
    # 改行、空白、記号を削除
    clean = re.sub(r'[\s　\n\r\t\.\,・\-|_]', '', text).lower()
    return clean

def is_name_match(target_name, text_to_check):
    """
    名字(西村)が含まれているか判定
    """
    clean_target = normalize_text(target_name)
    clean_cell = normalize_text(text_to_check)
    if not clean_target or not clean_cell: return False
    
    # 「西村」の2文字が含まれているか
    surname = clean_target[:2]
    return all(char in clean_cell for char in surname)

# --- 2. ファイル名から「期待値」を取得 ---
def extract_year_month_from_filename(file_name):
    if not file_name: return None, None
    text = normalize_text(file_name)
    y_val, m_val = None, None
    month_match = re.search(r'(\d{1,2})月', text)
    if month_match: m_val = int(month_match.group(1))
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
    for r in range(min(15, len(df))):
        for col in range(df.shape[1]):
            cell_val = str(df.iloc[r, col])
            d_match = re.search(r'(\d+)', cell_val)
            w_match = re.search(r'([月火水木金土日])', cell_val)
            if d_match and w_match:
                pdf_days.append({"d": int(d_match.group(1)), "w": w_match.group(1)})
        if pdf_days: break

    if not pdf_days: return False, "日付行不明", "Unknown"

    actual_max_day = max([x["d"] for x in pdf_days])
    day_one = next((x for x in pdf_days if x["d"] == 1), None)
    actual_first_wday = day_one["w"] if day_one else "不明"

    is_match = (actual_max_day == last_day) and (actual_first_wday == expected_first_wday)
    header_all = "".join(df.iloc[:3, 0].astype(str))
    work_place = "第2ターミナル" if "2" in header_all or "T2" in header_all else "免税店"

    return is_match, "OK", work_place

# --- 4. メイン解析 ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    pdf_stream.seek(0)
    year, month = extract_year_month_from_filename(file_name)
    
    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    table_dictionary = {}
    
    # 複数の読み込みモードを試行
    for flavor in ['lattice', 'stream']:
        try:
            tables = camelot.read_pdf(temp_path, pages='all', flavor=flavor)
        except:
            continue

        for table in tables:
            df = table.df
            if df.empty: continue
            
            is_valid, msg, work_place = verify_pdf_calendar(df, year, month)
            if not is_valid: continue

            # 全行スキャン
            for i in range(len(df)):
                # 名前列（通常は0列目）を重点的にチェック
                name_cell = str(df.iloc[i, 0])
                # 名前列に「西村」が含まれているか、または行全体に「西村」が含まれているか
                row_full = "".join(df.iloc[i, :].astype(str))
                
                if is_name_match(target_staff, name_cell) or is_name_match(target_staff, row_full):
                    # 発見！ 自分の行と、その下の行（シフト詳細の可能性）を取得
                    my_daily = df.iloc[i : i + 2, :].copy().reset_index(drop=True)
                    others = df.drop(index=[i, i+1] if i+1 < len(df) else [i]).copy().reset_index(drop=True)
                    table_dictionary[work_place] = [my_daily, others]
                    st.success(f"🎯 {flavor}モードで '{target_staff}' 様を検出しました（行 {i}）")
                    return table_dictionary, year, month

    # ここまで来ても見つからない場合、最終手段：部分一致検索の全表示
    st.warning(f"⚠️ '{target_staff}' 様の名前が特定できませんでした。")
    with st.expander("🛠️ 調査用：PDF内部から読み取れた名前候補"):
        st.write("以下のリストにあなたのお名前（または名字）が含まれている行番号を教えてください。")
        for i in range(len(df)):
            txt = str(df.iloc[i, 0]).replace('\n', ' ')
            if len(txt.strip()) > 1: # 空でない行のみ
                st.text(f"行 {i}: {txt[:50]}")
                
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
