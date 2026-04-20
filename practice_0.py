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
    名前のヒット率を最大化するロジック。
    ターゲット(例:西村文宏)の全文字が、セルの中にバラバラでも存在すればTrue。
    """
    clean_target = normalize_text(target_name)
    clean_cell = normalize_text(text_to_check)
    
    if not clean_target or not clean_cell:
        return False
        
    # 各文字が含まれているかチェック
    match_count = sum(1 for char in clean_target if char in clean_cell)
    
    # ターゲットが4文字（西村文宏）なら、4文字すべて見つかれば一致とみなす
    if match_count >= len(clean_target):
        return True
            
    return False

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
    for col in range(1, df.shape[1]):
        cell_val = str(df.iloc[0, col])
        d_match = re.search(r'(\d+)', cell_val)
        w_match = re.search(r'([月火水木金土日])', cell_val)
        if d_match and w_match:
            pdf_days.append({"d": int(d_match.group(1)), "w": w_match.group(1)})

    if not pdf_days:
        return False, "日付行が認識できません", "Unknown"

    actual_max_day = max([x["d"] for x in pdf_days])
    day_one = next((x for x in pdf_days if x["d"] == 1), None)
    actual_first_wday = day_one["w"] if day_one else "不明"

    # UI表示
    st.markdown("### 📊 ファイル整合性チェック")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**【ファイル名からの期待値】**")
        st.write(f"{expected_year}年{expected_month}月")
        st.write(f"1日: {expected_first_wday}曜日")
    with col2:
        st.write("**【PDFデータからの実測値】**")
        st.write(f"最大日数: {actual_max_day}日")
        st.write(f"1日: {actual_first_wday}曜日")

    is_match = (actual_max_day == last_day) and (actual_first_wday == expected_first_wday)
    
    header_cell = str(df.iloc[0, 0])
    work_place = header_cell.splitlines()[len(header_cell.splitlines())//2].strip() if header_cell else "Unknown"

    return is_match, "OK", work_place

# --- 4. メイン解析 ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    pdf_stream.seek(0)
    year, month = extract_year_month_from_filename(file_name)
    
    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
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
        all_row_names = [] # デバッグ用

        for i in range(len(df)):
            current_row_text = str(df.iloc[i, 0])
            next_row_text = str(df.iloc[i+1, 0]) if i+1 < len(df) else ""
            combined_text = current_row_text + next_row_text
            
            # デバッグ用に正規化前のテキストを保持
            all_row_names.append(current_row_text.replace('\n', ' '))

            if is_name_match(target_staff, combined_text):
                # 発見
                my_daily = df.iloc[i : i + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, i, i+1] if i+1 < len(df) else [0, i]).copy().reset_index(drop=True)
                table_dictionary[work_place] = [my_daily, others]
                found = True
                break
        
        if found:
            st.success(f"👤 '{target_staff}' さんのデータを抽出しました。")
        else:
            # 見つからなかった場合にデバッグリストを表示
            st.warning(f"'{target_staff}' という名前がPDFの1列目に見つかりません。")
            with st.expander("🔍 システムがPDFから読み取った名前一覧を確認する"):
                st.write("以下のリストにあなたの名前が含まれているか確認してください。")
                for idx, name in enumerate(all_row_names):
                    st.text(f"行 {idx}: {name}")
                st.info("ヒント: 名前が他の文字と繋がっていたり、一文字だけ違っていたりする場合は教えてください。")
                
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
