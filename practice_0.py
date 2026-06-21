import pandas as pd
import datetime
import csv
import camelot
import re

def format_time_value(val):
    """数値を15分刻みの時間表記 (HH:MM) に変換"""
    try:
        f = float(val)
        h = int(f)
        m = int((f - h) * 60)
        return f"{h:02d}:{m:02d}"
    except (ValueError, TypeError):
        return str(val)

def generate_shift_csv(key, staff_name, shift_data, time_dic):
    """CSVを作成し、生成したファイルパスを返す"""
    # ファイル名: YYYYMM_山田太郎_T1.csv
    file_name = f"{datetime.datetime.now().strftime('%Y%m')}_{staff_name}_{key}.csv"
    header = ["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]
    
    with open(file_name, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header) 
        
        for date, shift in shift_data.items():
            start_time = format_time_value(time_dic.get(shift, "00:00"))
            # カレンダー登録用の行を追加
            writer.writerow([f"{key}_{shift}", date, start_time, date, "", "False", "", key])
    
    return file_name
    
def load_time_schedule_from_sheets(service, spreadsheet_id):
    """スプレッドシートから時程表を読み込み、辞書化する"""
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    time_dic = {}
    
    for sheet in spreadsheet.get('sheets', []):
        title = sheet.get("properties", {}).get("title")
        res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=f"'{title}'!A1:Z300").execute()
        vals = res.get('values', [])
        if not vals: continue
        
        # DataFrame化して処理
        df = pd.DataFrame(vals).fillna('')
        
        # 勤務地(key)ごとに時間行を抽出するロジック
        current_loc = None
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a and val_a not in ["シフトコード", "ロッカー"]: # 勤務地らしき行
                current_loc = val_a
                # 勤務地が見つかったら、その下の行からデータを取得して辞書登録...
    return time_dic

# ※今後ここへPDF解析のcamelotロジックを追加していきます
