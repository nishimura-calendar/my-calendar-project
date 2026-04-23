import pandas as pd
import re
import calendar
import streamlit as st

def pdf_reader(file_name, df, target_staff):
    # 1. ファイル名から「月」を取得 (例: "1月度" -> 1)
    month_match = re.search(r'(\d{1,2})月', file_name)
    target_month = int(month_match.group(1)) if month_match else 1
    target_year = 2026 # 年度固定
    
    # 2. カレンダー上の正解を計算
    # 1日の曜日
    first_weekday_idx = calendar.monthrange(target_year, target_month)[0]
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_first_day = weekdays_jp[first_weekday_idx]
    # 月の最終日（日数）
    expected_last_date = str(calendar.monthrange(target_year, target_month)[1])

    # 3. 表からのデータ取得
    # [1, 1] の曜日を取得
    actual_first_day_raw = str(df.iloc[1, 1]).strip()
    actual_first_day = re.search(r'[月火水木金土日]', actual_first_day_raw).group(0) if re.search(r'[月火水木金土日]', actual_first_day_raw) else ""
    
    # [0, 最終列] の日数を取得
    actual_last_date = str(df.iloc[0, -1]).strip().split('\n')[-1] # 改行がある場合に対応

    # 4. 検問実行
    errors = []
    if actual_first_day != expected_first_day:
        errors.append(f"曜日不一致 (表:{actual_first_day}曜 / 暦:{expected_first_day}曜)")
    
    if actual_last_date != expected_last_date:
        errors.append(f"日数不一致 (表:{actual_last_date}日 / 暦:{expected_last_date}日)")

    if errors:
        st.error(f"⚠️ 検問エラー: {' , '.join(errors)}")
        st.stop() # 一致しない場合は停止

    # 5. データ抽出処理
    location_key = str(df.iloc[0, 0]).strip()
    st.success(f"✅ 検問クリア: {target_month}月シフト（{location_key}）")
    
    # (以下、氏名検索とシフト表示ロジックに続く)
    # ...
