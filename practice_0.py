import pdfplumber
import camelot
import pandas as pd
import re
import unicodedata
import io
import os
from googleapiclient.discovery import build

def normalize_text(text):
    """
    consideration_0.py準拠: 
    NFKC正規化を行い、すべての空白（全角・半角）を除去し、小文字に統一します。
    """
    if not isinstance(text, str): return ""
    # NFKC正規化で全角英数を半角に、記号を統一
    text = unicodedata.normalize('NFKC', text)
    # 空白文字をすべて除去
    text = re.sub(r'[\s　]', '', text)
    return text.lower()

def extract_year_month_from_text(text):
    """
    consideration_0.py準拠: 
    ファイル名などから「4桁の年」と「〇月」を抽出します。
    """
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    
    y_val, m_val = None, None
    # 「月」の前の数字を探す
    month_match = re.search(r'(\d{1,2})月', clean_text)
    if month_match:
        m_val = int(month_match.group(1))
    
    # 数字の羅列から年を推測
    nums = re.findall(r'\d+', clean_text)
    for n in nums:
        val = int(n)
        if len(n) == 4:
            y_val = val
        elif len(n) == 2 and y_val is None:
            # 2桁の場合は2000年代と仮定
            y_val = 2000 + val
            
    return str(y_val or "2026"), str(m_val or "04")

def time_schedule_from_drive(sheets_service, file_id):
    """
    consideration_0.py準拠:
    スプレッドシートの全シートを巡回し、A列の空白（結合セル相当）を補完。
    勤務地名をキーとした辞書形式でデータを返します。
    """
    try:
        # スプレッドシートの構成情報を取得
        spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
        sheets = spreadsheet.get('sheets', [])
        
        location_data_dic = {}
        for s in sheets:
            title = s.get("properties", {}).get("title")
            # A1からZ200までの広範囲を読み込み
            result = sheets_service.spreadsheets().values().get(
                spreadsheetId=file_id, 
                range=f"'{title}'!A1:Z200"
            ).execute()
            
            vals = result.get('values', [])
            if not vals:
                continue
            
            # DataFrame化して1行目をヘッダーに設定
            df = pd.DataFrame(vals)
            df.columns = df.iloc[0]
            df = df[1:].reset_index(drop=True)
            
            # 【重要】A列（勤務地）の空白を、上の値で埋める (ffill)
            # これにより「T1」の下に続く空白がすべて「T1」として認識されます
            df.iloc[:, 0] = df.iloc[:, 0].replace('', None).replace(' ', None).ffill()
            
            # 勤務地名（補完されたA列の値）ごとにデータを辞書に格納
            first_col_name = df.columns[0]
            for location_name in df[first_col_name].unique():
                if not location_name or str(location_name).strip() == "":
                    continue
                # その勤務地の行だけを抽出
                temp_range = df[df[first_col_name] == location_name]
                location_data_dic[str(location_name)] = temp_range.fillna('')
                
        return location_data_dic
    except Exception as e:
        raise e

def pdf_reader(pdf_stream, target_staff):
    """
    consideration_0.py準拠:
    Camelot(lattice)を使用してPDFを解析。
    指定されたスタッフ名の行（自分のシフト）と、それ以外のスタッフ（他人の状況）を分離します。
    """
    clean_target = normalize_text(target_staff)
    
    # Camelotはファイルパスを必要とするため、一度一時ファイルに保存
    pdf_stream.seek(0)
    temp_filename = "temp_process.pdf"
    with open(temp_filename, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        # PDFの全ページから表を抽出
        tables = camelot.read_pdf(temp_filename, pages='all', flavor='lattice')
        
        table_dictionary = {}
        for table in tables:
            df = table.df
            if df.empty:
                continue
            
            # 左上のセルから勤務地名を推測（consideration_0のロジಿಕを再現）
            header_content = str(df.iloc[0, 0]).splitlines()
            work_place = header_content[len(header_content)//2] if header_content else "不明"
            
            # A列（スタッフ名列）を正規化して検索
            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matched_indices = df.index[search_col == clean_target].tolist()
            
            if matched_indices:
                idx = matched_indices[0]
                # 自分のデータ：指定行とその次の行（時間行）
                my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                # 他人のデータ：ヘッダー（0行）と自分以外を除去
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                
                table_dictionary[work_place] = [my_daily, others]
        
        return table_dictionary

    except Exception as e:
        print(f"PDF解析中にエラーが発生しました: {e}")
        return {}
    finally:
        # 一時ファイルの削除
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
