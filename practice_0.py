import pandas as pd
import re
import unicodedata
import os
import camelot
import calendar
import io
from googleapiclient.http import MediaIoBaseDownload

def normalize_text(text):
    """全角半角を統一し、空白を除去して小文字化（照合用）"""
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'[\s　]', '', text).lower()

def extract_year_month_from_text(text):
    """ファイル名（正）から年・月・日数・曜日を算出"""
    if not text: return "2026", "04", 30, 0
    text = unicodedata.normalize('NFKC', text)
    y_val, m_val = 2026, 4
    m_match = re.search(r'(\d{1,2})月', text)
    if m_match: m_val = int(m_match.group(1))
    y_match = re.search(r'(\d{4})', text)
    if y_match: y_val = int(y_match.group(1))
    days_in_month = calendar.monthrange(y_val, m_val)[1]
    first_weekday = calendar.monthrange(y_val, m_val)[0]
    return str(y_val), str(m_val), days_in_month, first_weekday

def time_schedule_from_drive(service, file_id):
    """
    時程表を解析し、A列をキーに辞書登録します。
    ご提示いただいた時刻変換ロジックを統合しつつ、構造を維持します。
    """
    try:
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        request = service.files().get_media(fileId=file_id)
        if file_metadata.get('mimeType') == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str)
        
        # A列に値がある行（拠点名）を特定
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name_raw = str(full_df.iloc[start_row, 0]).strip()
            
            # 正規化したキーを作成（例: "T 1" -> "t1"）
            norm_key = normalize_text(location_name_raw)
            if not norm_key or norm_key == 'nan': continue
            
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 時刻変換 (6.25 -> 6:15)
            for col in range(len(temp_range.columns)):
                if col < 2: continue # A, B列はスキップ
                v = temp_range.iloc[0, col]
                try:
                    f_v = float(v)
                    if 0 <= f_v <= 28:
                        h = int(f_v)
                        m = int(round((f_v - h) * 60))
                        temp_range.iloc[0, col] = f"{h}:{m:02d}"
                except: pass
            
            # 辞書に「正規化キー」を登録
            location_data_dic[norm_key] = {
                "df": temp_range.fillna(''),
                "original_name": location_name_raw
            }
            
        return location_data_dic
    except Exception as e:
        raise e

def pdf_reader(pdf_stream, target_staff, expected_days, time_master_dic):
    """
    ご指示通り：全てのキーを対象に、PDFの見出しに含まれているか検索します。
    """
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    temp_name = "temp_process.pdf"
    with open(temp_name, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf(temp_name, pages='all', flavor='lattice')
        if not tables:
            return {"error_type": "SYSTEM", "msg": "PDFから表を抽出できませんでした。"}

        res = {}
        # キーの長い順に回す（T10がT1に誤判定されるのを防ぐ）
        master_keys = sorted(time_master_dic.keys(), key=len, reverse=True)

        for table in tables:
            df = table.df
            if df.empty: continue
            
            # PDFの左上セル（勤務地＋日付＋曜日が繋がっている文字列）
            raw_header = "".join(df.iloc[0, 0].splitlines())
            norm_header = normalize_text(raw_header)
            
            # 【思い通りのロジック】全てのkeyを対象に検索
            matched_key = None
            for key in master_keys:
                if key in norm_header:
                    matched_key = key
                    break
            
            if not matched_key:
                return {"error_type": "WP_MISSING", "wp": raw_header}

            # 第2関門：日程チェック
            pdf_days = df.shape[1] - 1 
            if pdf_days != expected_days:
                return {"error_type": "DAY_MISMATCH", "exp": expected_days, "act": pdf_days}

            # スタッフ抽出
            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matches = df.index[search_col == clean_target].tolist()
            
            if matches:
                idx = matches[0]
                my_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                # 紐付け成功
                res[matched_key] = [my_shift, others, time_master_dic[matched_key]["original_name"]]
        
        return res if res else {"error_type": "SYSTEM", "msg": f"『{target_staff}』さんが見つかりません。"}
    except Exception as e:
        return {"error_type": "SYSTEM", "msg": str(e)}
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)
