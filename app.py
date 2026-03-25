import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from googleapiclient.discovery import build
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive

# --- 各種設定 ---
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト変換", layout="wide")
st.title("📅 シフトカレンダー一括変換（最終完成版）")

def get_gapi_service():
    """Google API 認証"""
    try:
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

def format_time(val):
    """数値(17.5等)やシリアル値(0.375等)を 'HH:MM' 形式の文字列に変換"""
    if pd.isna(val) or str(val).strip() == "" or str(val).lower() == "nan":
        return ""
    try:
        # すでに "9:00" 形式ならそのまま
        if isinstance(val, str) and ":" in val:
            return val
        
        num = float(val)
        # Excelシリアル値 (1未満の場合)
        if num < 1:
            h = int(num * 24)
            m = int(round((num * 24 - h) * 60))
        # 17.5 のような時間数値の場合
        else:
            h = int(num)
            m = int(round((num - h) * 60))
        return f"{h:02d}:{m:02d}"
    except:
        return str(val)

def shift_cal(key, target_date, col, shift_info, other_staff_shift, time_schedule, final_rows):
    """詳細スケジュール（15分刻み）の生成ロジック"""
    clean_info = unicodedata.normalize('NFKC', str(shift_info)).strip()
    t_s = time_schedule.copy()
    
    # 時刻ヘッダー（0行目）を事前に変換
    time_headers = [format_time(t_s.iloc[0, c]) for c in range(t_s.shape[1])]
    
    # 自分の記号行を特定
    my_row = t_s[t_s.iloc[:, 1].astype(str).apply(lambda x: unicodedata.normalize('NFKC', x).strip()) == clean_info]
    
    if not my_row.empty:
        # 終日予定を追加（True）
        final_rows.append([f"{key}_{clean_info}", target_date, "", target_date, "", "True", "", key])
        
        prev_val = ""
        # 2列目(時刻列の開始)からループ
        for t_col in range(2, t_s.shape[1]):
            raw_val = my_row.iloc[0, t_col]
            current_val = str(raw_val).strip() if pd.notna(raw_val) and str(raw_val).lower() != "nan" and str(raw_val) != "" else ""
            
            if current_val != prev_val:
                # 前の予定がある場合、その終了時刻をセット
                if len(final_rows) > 0 and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_headers[t_col]

                if current_val != "":
                    # 引き継ぎ相手の特定
                    h_dep = ""
                    mask_h = pd.Series([False] * len(t_s))
                    if prev_val == "":
                        # 勤務開始（交代）
                        mask_h = (t_s.iloc[:, t_col].astype(str).replace('nan','') == "") & (t_s.iloc[:, t_col-1].astype(str).replace('nan','') != "")
                        if mask_h.any(): h_dep = "(交代)"
                    else:
                        # 部署移動
                        h_dep = f"({prev_val})"
                        mask_h = (t_s.iloc[:, t_col].astype(str).str.strip() == prev_val)

                    # 受ける側（直前にその場所にいた人）
                    mask_t = (t_s.iloc[:, t_col-1].astype(str).str.strip() == current_val)
                    
                    names_to, names_from = [], []
                    for i, mask in enumerate([mask_h, mask_t]):
                        keys = t_s.loc[mask, t_s.columns[1]].unique()
                        names = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.strip().isin(keys)].iloc[:, 0].unique()
                        if i == 0: names_to = names.tolist()
                        else: names_from = names.tolist()

                    to_str = f"to {'・'.join(names_to)}" if names_to else ""
                    from_str = f"from {'・'.join(names_from)}" if names_from else ""
                    
                    # 詳細予定を追加（False）
                    final_rows.append([
                        f"{h_dep}{to_str}=>【{current_val}】{from_str}", 
                        target_date, 
                        time_headers[t_col], 
                        target_date, 
                        "", # 次のループでセット
                        "False", 
                        "", 
                        key
                    ])
            prev_val = current_val

# --- UI操作部 ---
uploaded_file = st.file_uploader("1. シフトPDFをアップロード", type="pdf")

if uploaded_file:
    if st.button("2. 変換を実行"):
        with st.spinner("処理中..."):
            service = get_gapi_service()
            if service:
                location_dic = time_schedule_from_drive(service, TIME_TABLE_ID)
                y, m = extract_year_month(uploaded_file)
                my_s, other_s = pdf_reader(uploaded_file, TARGET_STAFF)
                
                final_results = []
                # 各日付(列)をスキャン
                for col in range(1, my_s.shape[1]):
                    shift_code = str(my_s.iloc[0, col]).strip()
                    if not shift_code or shift_code.lower() == "nan": continue
                    
                    target_date = f"{y}/{m}/{col}"
                    
                    # 休暇判定
                    if any(h in shift_code for h in ["休", "有給", "公休"]):
                        final_results.append([f"T2_休日", target_date, "", target_date, "", "True", "", "T2"])
                    else:
                        # T2の時程表を使用
                        if "T2" in location_dic:
                            shift_cal("T2", target_date, col, shift_code, other_s, location_dic["T2"][0], final_results)
                
                if final_results:
                    df_res = pd.DataFrame(final_results, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
                    st.success(f"{y}年{m}月の変換に成功しました！")
                    st.table(df_res)
                    
                    # 文字化け対策（utf-8-sig）でCSV保存
                    csv = df_res.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button("3. Googleカレンダー用CSVを保存", csv, f"shift_{y}_{m}.csv", "text/csv")
                else:
                    st.warning("データが見つかりませんでした。")
