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

# --- 1. テキストの正規化 (ここが今回の核心です) ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    # 全角を半角に変換
    text = unicodedata.normalize('NFKC', text)
    # \n (改行) や 空白、タブ、記号をすべて削除して「1行の塊」にする
    clean = re.sub(r'[\s　\n\r\t\.\,・-]', '', text).lower()
    return clean

def is_name_match(target_name, cell_text):
    """
    ターゲット名(例: 西村文宏)がセルのテキストに含まれるか判定。
    改行を消し、かつ「名字+名前」「名前+名字」の両方でチェックする。
    """
    clean_target = normalize_text(target_name) # 例: 西村文宏
    clean_cell = normalize_text(cell_text)     # 例: c文宏西村
    
    if not clean_target or not clean_cell:
        return False
        
    # パターン1: そのまま含まれているか (西村文宏)
    if clean_target in clean_cell:
        return True
    
    # パターン2: 名字と名前を入れ替えて含まれているか (文宏西村)
    # ※ 2文字+2文字の名前を想定した簡易的な入れ替え
    if len(clean_target) >= 4:
        last_name = clean_target[:2]
        first_name = clean_target[2:]
        reversed_name = first_name + last_name # 文宏西村
        if reversed_name in clean_cell:
            return True
            
    return False

# --- 2. ファイル名から「正解」の年月を取得 ---
def extract_year_month_from_filename(file_name):
    if not file_name: return None, None
    text = unicodedata.normalize('NFKC', file_name)
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

# --- 3. 日数と曜日の表示・確認ロジック ---
def verify_pdf_calendar(df, expected_year, expected_month):
    """
    ファイル名からの期待値とPDFの実測値を表示し、照合する。
    """
    if not expected_year or not expected_month:
        return False, "年月不明", "Unknown"

    # --- A. ファイル名からの期待値 (カレンダー上の正解) ---
    first_wday_idx, last_day = calendar.monthrange(expected_year, expected_month)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_first_wday = weekdays_jp[first_wday_idx]
    
    # --- B. PDFからの実測値 ---
    pdf_days = []
    for col in range(1, df.shape[1]):
        cell_val = str(df.iloc[0, col])
        d_m = re.search(r'(\d+)', cell_val)
        w_m = re.search(r'([月火水木金土日])', cell_val)
        if d_m and w_m:
            pdf_days.append({"d": int(d_m.group(1)), "w": w_m.group(1)})

    if not pdf_days:
        return False, "日付行が読み取れません", "Unknown"

    max_day_in_pdf = max([x["d"] for x in pdf_days])
    day_one = next((x for x in pdf_days if x["d"] == 1), None)
    actual_first_wday = day_one["w"] if day_one else "不明"

    # --- C. 画面表示 ---
    st.markdown("### 📅 カレンダー照合結果")
    c1, c2 = st.columns(2)
    with c1:
        st.info(f"**【ファイル名より算出】**\n\n対象: {expected_year}年{expected_month}月\n\n日数: {last_day}日\n\n1日: {expected_first_wday}曜日")
    with c2:
        st.info(f"**【PDFデータより抽出】**\n\n判定: 解析成功\n\n日数: {max_day_in_pdf}日\n\n1日: {actual_first_wday}曜日")

    is_match = (max_day_in_pdf == last_day) and (actual_first_wday == expected_first_wday)
    
    if is_match:
        st.success("✅ ファイル名と中身が一致しました！")
    else:
        st.error("❌ ファイル名と中身の日付/曜日が一致しません。")

    header_cell = str(df.iloc[0, 0])
    work_place = header_cell.splitlines()[len(header_cell.splitlines())//2].strip() if header_cell else "Unknown"

    return is_match, "Check Complete", work_place

# --- 4. メイン解析関数 ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    pdf_stream.seek(0)
    year, month = extract_year_month_from_filename(file_name)
    
    temp_path = "current_process.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf(temp_path, pages='all', flavor='lattice')
    except Exception as e:
        st.error(f"解析エラー: {e}")
        return {}, year, month

    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # 1. 整合性確認
        is_valid, _, work_place = verify_pdf_calendar(df, year, month)
        if not is_valid:
            continue

        # 2. 名前検索 (改行削除 + 逆転検索)
        for i in range(len(df)):
            cell_text = str(df.iloc[i, 0])
            if is_name_match(target_staff, cell_text):
                # 見つかった場合、自分2行・他人1行のルールで抽出
                my_daily = df.iloc[i : i + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, i, i+1] if i+1 < len(df) else [0, i]).copy().reset_index(drop=True)
                table_dictionary[work_place] = [my_daily, others]
                break
                
    return table_dictionary, year, month

# --- 5. 時程表取得 ---
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
