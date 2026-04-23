import pandas as pd
import re
import calendar
import streamlit as st

def pdf_reader(file_name, df, target_staff):
    # 1. ファイル名から「月」を取得
    month_match = re.search(r'(\d{1,2})月', file_name)
    target_month = int(month_match.group(1)) if month_match else 1
    
    # 2. カレンダー検問（A1=勤務地、B1=1日、B2=曜日 と想定）
    # A1セルの勤務地を取得
    location_key = str(df.iloc[0, 0]).strip()
    
    # B1セルの「1日」と、最終列の「31日」をチェック
    actual_first_date = str(df.iloc[0, 1]).strip()
    actual_last_date = str(df.iloc[0, -1]).strip()
    
    # B2セルの「曜日」を取得
    actual_weekday = str(df.iloc[1, 1]).strip() # row_tol=2なら1行下に入る

    # 2026年1月の正解
    expected_weekday = "木"
    expected_last = "31"

    # 検問実行
    errors = []
    if actual_first_date != "1":
        errors.append(f"開始日ズレ(取得:{actual_first_date})")
    if actual_weekday != expected_weekday:
        errors.append(f"曜日不一致(取得:{actual_weekday})")
    if actual_last_date != expected_last:
        errors.append(f"日数不一致(取得:{actual_last_date})")

    if errors:
        st.error(f"⚠️ 検問エラー: {' / '.join(errors)}")
        st.write("現在の表の左上(A1付近):", df.iloc[:3, :3])
        return

    # 3. 成功時の処理
    st.success(f"✅ 検問クリア: {target_month}月 {location_key} シフト表")
    
    # ここにスタッフの行を探してシフトを抽出するコードが続きます
    # st.dataframe(df) # デバッグ用表示
