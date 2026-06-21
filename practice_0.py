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

# ※今後ここへPDF解析のcamelotロジックを追加していきます
