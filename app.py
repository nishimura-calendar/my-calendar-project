import streamlit as st
import pandas as pd
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration

TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

def shift_cal(key, target_date, col, shift_info, my_daily_shift, time_schedule, final_rows):
    """
    セルの値が変化した時のみイベントを生成する。
    """
    # 終日予定（シフトコード）
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    shift_code = str(my_daily_shift.iloc[0, col]).strip()
    sched_clean = time_schedule.fillna("").astype(str)
    
    # 自分のシフトに該当する行を取得
    my_time_shift = sched_clean.iloc[1:][sched_clean.iloc[1:, 1] == shift_code]
    
    if not my_time_shift.empty:
        prev_val = None
        last_row_idx = -1
        
        # 時刻列を横方向にスキャン
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col].strip()
            
            # 値がない（休憩など）場合はリセット
            if not current_val:
                prev_val = None
                continue
            
            # 【重要】値が変化したかどうかの判定
            if current_val == prev_val and last_row_idx != -1:
                # 前と同じ値なら、終了時間を現在の列の次の時刻で更新し続ける
                # これにより、同じ役割が続く限り1つのイベントとして伸びる
                next_time_label = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else str(time_schedule.iloc[0, t_col]).strip()
                final_rows[last_row_idx][4] = next_time_label
            else:
                # 新しい値になった（または休憩明け）
                start_time = str(time_schedule.iloc[0, t_col]).strip()
                # 暫定の終了時間は次の列
                end_time = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else start_time
                
                # 参考資料の「交代」などの文言があれば付与するロジックのベース
                event_name = f"【{current_val}】"
                
                final_rows.append([event_name, target_date, start_time, target_date, end_time, "False", "", key])
                last_row_idx = len(final_rows) - 1
                prev_val = current_val

# --- 以下、Streamlit UI部分は前回同様のため省略可能ですが、統合した形で実行してください ---
st.set_page_config(page_title="シフト変換", layout="wide")
st.title("📅 シフトカレンダー一括変換 (3/20リセット版)")

# (GAPIサービス取得関数などは既存のものを利用)
