import pandas as pd
import pdfplumber
import re
import io
import unicodedata
import streamlit as st
from googleapiclient.http import MediaIoBaseDownload

def normalize_text(text):
    """
    全角・半角・空白・改行の差異を吸収して、比較しやすくする関数。
    これが無いと app.py でエラーになります。
    """
    if not text or str(text).lower() == 'nan':
        return ""
    # NFKC正規化（全角英数を半角にするなど）を行い、空白と改行を削除
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[\s　\n\r]', '', normalized).strip()

def extract_year_month(pdf_stream):
    """PDFのテキストから『2026年3月』などの年月を抽出"""
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            text = pdf.pages[0].extract_text()
            if not text:
                return "2026", "3"
            # 年月パターンの検索
            match = re.search(r'(20\d{2})[年\.]\s*(\d{1,2})', text)
            if match:
                return match.group(1), match.group(2)
    except:
        pass
    return "2026", "3"

def parse_special_shift(text):
    """'10.5@19' のような特殊な勤務時間を『10:30』『19:00』に変換"""
    text = normalize_text(text)
    if "@" in text:
        try:
            parts = text.split("@")
            def conv_time(val_str):
                v = float(val_str)
                h = int(v)
                m = int(round((v % 1) * 60))
                return f"{h:02d}:{m:02d}"
            return conv_time(parts[0]), conv_time(parts[1]), True
        except:
            pass
    return "", "", False

def time_schedule_from_drive(service, file_id):
    """Google Driveからスプレッドシート（時程表）を取得して辞書にする"""
    try:
        if not service or not file_id:
            return {}
        request = service.files().export_media(fileId=file_id, mimeType='text/csv')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        
        # CSV読み込み
        full_df = pd.read_csv(fh, header=None).fillna('')
        location_data_dic = {}
        
        # A列に文字がある行（場所の開始行）を特定
        loc_idx = full_df[full_df.iloc[:, 0] != ""].index.tolist()
        for i, start_row in enumerate(loc_idx):
            raw_name = str(full_df.iloc[start_row, 0])
            norm_name = normalize_text(raw_name)
            
            end_row = loc_idx[i+1] if i+1 < len(loc_idx) else len(full_df)
            df = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 1行目の時間軸を整形
            for col in range(2, df.shape[1]):
                try:
                    num = float(df.iloc[0, col])
                    h = int(num * 24 if num < 1 else num)
                    m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
                    df.iloc[0, col] = f"{h:02d}:{m:02d}"
                except:
                    pass
            location_data_dic[norm_name] = df
        return location_data_dic
    except:
        return {}

def data_integration(pdf_dic, time_sched_dic):
    """PDFから出した場所名と、時程表の場所名を紐付ける"""
    integrated = {}
    for p_name, p_list in pdf_dic.items():
        norm_p = normalize_text(p_name)
        # 時程表の中に、名前を掃除した後の場所名があるか探す
        if norm_p in time_sched_dic:
            integrated[p_name] = p_list + [time_sched_dic[norm_p]]
        else:
            # 見つからない場合はテスト用データ等のために T2 などのキーを探す
            if "T2" in norm_p and "T2" in time_sched_dic:
                integrated[p_name] = p_list + [time_sched_dic["T2"]]
            else:
                st.warning(f"場所 '{p_name}' に一致する時程表が見つかりません。")
    return integrated

def pdf_reader(pdf_stream, target_staff):
    """PDFを解析して、『場所名』をキーに自分と全体の表を分ける"""
    pdf_dic = {}
    clean_target = normalize_text(target_staff)
    with pdfplumber.open(pdf_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty or df.shape[1] < 2:
                    continue
                
                # 左上のセルを場所名とする
                loc_name = str(df.iloc[0, 0]).split('\n')[0].strip()
                
                # 自分の行を探す
                my_s = None
                for idx, row in df.iterrows():
                    combined_row_text = "".join(row.astype(str))
                    if clean_target in normalize_text(combined_row_text):
                        # 名前のある行と、そのすぐ下の行（備考など）をセットにする
                        my_s = df.iloc[idx : idx+2, :].reset_index(drop=True)
                        break
                
                if my_s is not None:
                    # [自分の2行, 全体の表] のリストを保存
                    pdf_dic[loc_name] = [my_s, df]
    return pdf_dic
