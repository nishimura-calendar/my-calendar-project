import pandas as pd
import datetime
import re
import csv

def format_time_value(val):
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
        
        # インデントは必ず半角スペース4つにしてください
        for date, shift in shift_data.items():
            start_time = format_time_value(time_dic.get(shift, "00:00"))
            writer.writerow([f"{key}_{shift}", date, start_time, date, "", "False", "", key])

    return file_name
