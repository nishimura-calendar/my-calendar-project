import pandas as pd
import pdfplumber
import re
import io
import unicodedata
import streamlit as st
from googleapiclient.http import MediaIoBaseDownload

def normalize_text(text):
    """全角半角、空白、改行を統一して比較しやすくする"""
    if not text or str(text).lower() == 'nan': return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[\s　\n\r]', '', normalized).strip()

def extract_year_month(pdf_stream):
    """PDFから年月を抽出"""
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            text = pdf.pages[0].extract_text()
            if not text: return "2026", "3"
            m = re.search(r'(20\d{2})[年\.]\s*(\d{1,2})', text)
            if m: return m.group(1), m.group(2)
    except: pass
    return "2026", "3"

def parse_special_shift(text):
    """'10.5@19' 形式を解析"""
    text = normalize_text(text)
    if "@" in text:
        try:
            parts = text.split("@")
            def conv(v_str):
                v = float(v_str)
                h = int(v)
                m = int(round((v % 1) * 60))
                return f"{h:02d}:{m:02d}"
            return conv(parts[0]), conv(parts[1]), True
        except: pass
    return "", "", False

def time_schedule_from_drive(service, file_id):
    """
    Google Driveからファイルを読み込みます。
    様々な文字コード(UTF-8, Shift-JIS, CP932)に対応します。
    """
    try:
        fh = io.BytesIO()
        # 1. Google Driveからデータをダウンロード
        try:
            # スプレッドシート形式の場合
            request = service.files().export_media(fileId=file_id, mimeType='text/csv')
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        except Exception:
            # CSVファイルが直接置かれている場合
            fh = io.BytesIO()
            request = service.files().get_media(fileId=file_id)
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        
        content = fh.getvalue()
        if not content:
            st.error("ファイルの中身が空です。")
            return {}

        # 2. 文字コードを順に試して読み込む
        full_df = None
        # 試行するエンコードリスト
        encodings = ['utf-8-sig', 'cp932', 'shift_jis', 'utf-8']
        
        for enc in encodings:
            try:
                full_df = pd.read_csv(io.BytesIO(content), header=None, encoding=enc).fillna('')
                # 読み込みに成功したらループを抜ける
                break
            except Exception:
                continue
        
        if full_df is None:
            st.error("ファイルの文字コードを判別できませんでした（UTF-8, CP932, Shift-JISのいずれでもありません）。")
            return {}
        
        # 3. データの整形
        location_data_dic = {}
        # A列に値がある行を「場所の区切り」として認識
        loc_idx = full_df[full_df.iloc[:, 0].astype(str).str.strip() != ""].index.tolist()
        
        for i, start_row in enumerate(loc_idx):
            raw_name = str(full_df.iloc[start_row, 0])
            norm_name = normalize_text(raw_name)
            
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 時間行（1行目）のシリアル値を時刻に変換
            for col in range(2, df.shape[1]):
                val = df.iloc[0, col]
                try:
                    num = float(val)
                    h = int(num * 24 if num < 1 else num)
                    m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
                    df.iloc[0, col] = f"{h:02d}:{m:02d}"
                except:
                    pass
            location_data_dic[norm_name] = df
            
        return location_data_dic
    except Exception as e:
        st.error(f"⚠️ 読み込み中にエラーが発生しました: {e}")
        return {}

def data_integration(pdf_dic, time_sched_dic):
    """PDFと時程表の場所名を紐付け"""
    integrated = {}
    for p_name, p_list in pdf_dic.items():
        norm_p = normalize_text(p_name)
        found_key = None
        for ts_key in time_sched_dic.keys():
            # 部分一致も含めて探索
            if ts_key in norm_p or norm_p in ts_key:
                found_key = ts_key
                break
        
        if found_key:
            integrated[p_name] = p_list + [time_sched_dic[found_key]]
        else:
            st.warning(f"⚠️ 場所 '{p_name}' の時程表が見つかりません。")
    return integrated

def pdf_reader(pdf_stream, target_staff):
    """PDF解析"""
    pdf_dic = {}
    clean_target = normalize_text(target_staff)
    with pdfplumber.open(pdf_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty or df.shape[1] < 2: continue
                first_cell = str(df.iloc[0, 0]).replace('\n', '')
                loc_name = first_cell.strip()
                my_s = None
                for idx, row in df.iterrows():
                    if clean_target in normalize_text("".join(row.astype(str))):
                        my_s = df.iloc[idx : idx+2, :].reset_index(drop=True)
                        break
                if my_s is not None:
                    pdf_dic[loc_name] = [my_s, df]
    return pdf_dic
