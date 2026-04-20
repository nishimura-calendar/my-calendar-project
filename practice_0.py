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
    # 改行、空白、記号、タブを完全に削除
    clean = re.sub(r'[\s　\n\r\t\.\,・\-|_]', '', text).lower()
    return clean

def is_name_match(target_name, text_to_check):
    """
    名前のヒット率を最大化するロジック。
    名字（西村）と名前（文宏）を分けて、名字さえあればOKとする緩和策を導入。
    """
    clean_target = normalize_text(target_name)
    clean_cell = normalize_text(text_to_check)
    
    if not clean_target or not clean_cell:
        return False
        
    # ターゲットから「名字」と「名前」を推測（西村文宏 -> 西村, 文宏）
    surname = clean_target[:2] # 西村
    first_name = clean_target[2:] # 文宏

    # 1. 名字が含まれているか？
    has_surname = all(char in clean_cell for char in surname)
    # 2. 名前が含まれているか？
    has_firstname = all(char in clean_cell for char in first_name) if first_name else True

    # 名字さえ合っていれば、ほぼ確定とする（他の方と被る可能性が低いため）
    if has_surname:
        return True
    
    # 万が一名字が1文字欠けても、全体で3文字以上合致すればOK
    match_count = sum(1 for char in clean_target if char in clean_cell)
    if match_count >= 3:
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
    # 最初の10行以内を広範囲にスキャンして日付行を探す
    for r in range(min(10, len(df))):
        for col in range(df.shape[1]):
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

    is_match = (actual_max_day == last_day) and (actual_first_wday == expected_first_wday)
    header_cell = str(df.iloc[0, 0])
    work_place = "第2ターミナル" if "2" in header_cell or "T2" in header_cell else "免税店"

    return is_match, "OK", work_place

# --- 4. メイン解析 ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    pdf_stream.seek(0)
    year, month = extract_year_month_from_filename(file_name)
    
    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    table_dictionary = {}
    
    # 読み込みモードを2パターン試す
    for flavor in ['lattice', 'stream']:
        try:
            tables = camelot.read_pdf(temp_path, pages='all', flavor=flavor)
        except:
            continue

        for table in tables:
            df = table.df
            if df.empty: continue
            
            # カレンダー構造を持っているか確認
            is_valid, msg, work_place = verify_pdf_calendar(df, year, month)
            if not is_valid: continue

            all_row_previews = []
            for i in range(len(df)):
                # 全列のテキストを結合
                row_content = "".join(df.iloc[i, :].astype(str))
                # 前後の行も含めて検索
                search_area = row_content
                if i > 0: search_area += "".join(df.iloc[i-1, :].astype(str))
                if i+1 < len(df): search_area += "".join(df.iloc[i+1, :].astype(str))
                
                # プレビュー用
                all_row_previews.append(row_content[:60])

                if is_name_match(target_staff, search_area):
                    my_daily = df.iloc[i : i + 2, :].copy().reset_index(drop=True)
                    others = df.drop([0, i, i+1] if i+1 < len(df) else [0, i]).copy().reset_index(drop=True)
                    table_dictionary[work_place] = [my_daily, others]
                    st.success(f"👤 '{target_staff}' 様の行を発見しました（モード: {flavor}）")
                    return table_dictionary, year, month

    # 見つからない場合
    st.warning(f"'{target_staff}' 様の名前が検出できませんでした。")
    with st.expander("🔍 内部データを確認する（こちらを開いて内容を教えてください）"):
        st.write("解析された各行のテキストです：")
        for idx, txt in enumerate(all_row_previews if 'all_row_previews' in locals() else []):
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
