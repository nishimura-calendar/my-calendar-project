import pandas as pd
import datetime
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
    file_name = f"{datetime.datetime.now().strftime('%Y%m')}_{staff_name}_{key}.csv"
    header = ["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]
    
    with open(file_name, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header) 
        
        # シフト情報の判定と行追加
    　　for date, shift in shift_data.items():
           # 色分け判定（休・イベント・勤務地）
           color = "1" # デフォルト
           if shift in ["休", "休日", "公休", "有休", "有給"]:
               color = "4" # 赤系
           elif shift in ["イベント名等"]: # イベント.csvと照合
               color = "5" # 黄系
           else:
               color = "9" # 青系（勤務地別）

           # 時間の取得 (time_dic[key]を参照)
           start_time = format_time_value(time_dic.get(shift, "00:00"))
        
           rows.append([f"{key}_{shift}", date, start_time, date, "", "False", "", key])

    return file_name # 作成したファイル名を返す
    
    return rows
