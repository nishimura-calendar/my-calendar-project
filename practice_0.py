import calendar
import re
import unicodedata
import streamlit as st

def get_canonical(text):
    return unicodedata.normalize('NFKC', str(text)).lower().strip()

def pdf_reader(file_name, df):
    # --- (A) ファイル名から算出 ---
    match = re.search(r'(\d+)月', file_name)
    target_month = int(match.group(1))
    year = 2026 # 運用年に合わせて固定または取得
    expected_days = calendar.monthrange(year, target_month)[1]
    # 最初の曜日(月=0, 日=6)を日本語に変換
    days_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_first_dow = days_jp[calendar.monthrange(year, target_month)[0]]

    # --- (B) PDF内容の抽出 (iloc[0,0]) ---
    elements = str(df.iloc[0, 0]).split()
    m = len(elements)
    
    actual_days = len([e for e in elements[:m // 2] if e.isdigit()])
    actual_location_raw = elements[m // 2]
    actual_first_dow = elements[m // 2 + 1]

    # A != B の判定
    mismatch_reasons = []
    if actual_days != expected_days:
        mismatch_reasons.append(f"日数が違います（ファイル名:{expected_days}日 / PDF:{actual_days}日）")
    if actual_first_dow != expected_first_dow:
        mismatch_reasons.append(f"最初の曜日が違います（期待:{expected_first_dow} / PDF:{actual_first_dow}）")

    if mismatch_reasons:
        st.error(f"【検証不一致】解析を終了します。対象ファイル: {file_name}")
        for r in mismatch_reasons:
            st.write(f"・{r}")
        st.stop() # 終了

    # 一致(A=B)なら進む
    location_key = get_canonical(actual_location_raw)
    
    # 勤務地をkeyとした辞書登録 (my_daily_shift, other_daily_shift)
    # ※ここでは例として構造のみ生成
    my_daily_shift = {location_key: "個人の詳細データ"}
    other_daily_shift = {location_key: "他者の詳細データ"}
    
    return location_key, actual_location_raw, my_daily_shift, other_daily_shift

def data_integration(location_key, raw_loc, time_sched, my_shift, other_shift):
    # 時程表（正）にキーがあるか確認。なければはじく。
    if location_key not in time_sched:
        st.error(f"勤務地が「{raw_loc}」で、設定値には見当たりません。")
        st.stop()
        
    return {
        location_key: {
            "time_schedule": time_sched[location_key],
            "my_daily_shift": my_shift[location_key],
            "other_shift": other_shift[location_key]
        }
    }                                                                                    
