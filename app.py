import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from googleapiclient.discovery import build
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive

# --- 設定情報 ---
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG" # Google Driveの時程表ExcelのID
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト変換", layout="wide")
st.title("📅 シフトカレンダー一括変換（完成版）")

def get_gapi_service():
    """Streamlit Secretsから認証情報を取得"""
    try:
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Google API認証エラー: {e}")
        return None

def shift_cal(key, target_date, col, shift_info, other_staff_shift, time_schedule, final_rows):
    """時程表を解析して詳細行を生成"""
    clean_info = unicodedata.normalize('NFKC', str(shift_info)).strip()
    t_s = time_schedule.copy()
    
    # 自分の記号行を特定
    my_row = t_s[t_s.iloc[:, 1].astype(str).apply(lambda x: unicodedata.normalize('NFKC', x).strip()) == clean_info]
    
    if not my_row.empty:
        # 終日予定を追加
        final_rows.append([f"{key}_{clean_info}", target_date, "", target_date, "", "True", "", key])
        
        prev_val = ""
        for t_col in range(2, t_s.shape[1]):
            raw_val = my_row.iloc[0, t_col]
            current_val = str(raw_val).strip() if pd.notna(raw_val) and str(raw_val).lower() != "nan" and str(raw_val) != "" else ""
            
            if current_val != prev_val:
                # 前の予定の終了時刻を確定
                if len(final_rows) > 0 and final_rows[-1][5] == "False":
                    final_rows[-1][4] = str(t_s.iloc[0, t_col]).strip()

                if current_val != "":
                    # 引き継ぎ相手の特定
                    h_dep = ""
                    mask_h = pd.Series([False] * len(t_s))
                    if prev_val == "":
                        mask_h = (t_s.iloc[:, t_col].astype(str).replace('nan','') == "") & (t_s.iloc[:, t_col-1].astype(str).replace('nan','') != "")
                        if mask_h.any(): h_dep = "(交代)"
                    else:
                        h_dep = f"({prev_val})"
                        mask_h = (t_s.iloc[:, t_col].astype(str).str.strip() == prev_val)

                    mask_t = (t_s.iloc[:, t_col-1].astype(str).str.strip() == current_val)
                    
                    names_to, names_from = [], []
                    for i, mask in enumerate([mask_h, mask_t]):
                        keys = t_s.loc[mask, t_s.columns[1]].unique()
                        names = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.strip().isin(keys)].iloc[:, 0].unique()
                        if i == 0: names_to = names.tolist()
                        else: names_from = names.tolist()

                    to_str = f"to {'・'.join(names_to)}" if names_to else ""
                    from_str = f"from {'・'.join(names_from)}" if names_from else ""
                    
                    final_rows.append([f"{h_dep}{to_str}=>【{current_val}】{from_str}", target_date, str(t_s.iloc[0, t_col]).strip(), target_date, "", "False", "", key])
            prev_val = current_val

# --- メイン画面の操作部 ---
st.info("左側のサイドバーが開いている場合は閉じると見やすくなります。")
uploaded_file = st.file_uploader("1. シフトPDFをアップロードしてください", type="pdf")

if uploaded_file:
    if st.button("2. カレンダーデータに変換する"):
        with st.spinner("変換中..."):
            service = get_gapi_service()
            if service:
                # 1. 時程表の取得
                location_dic = time_schedule_from_drive(service, TIME_TABLE_ID)
                
                # 2. PDFの読み込み
                y, m = extract_year_month(uploaded_file)
                # pdf_readerは「自分」と「全員分」のDFを返す前提
                my_s, other_s = pdf_reader(uploaded_file, TARGET_STAFF)
                
                final_results = []
                # 各日付(列)をループ
                for col in range(1, my_s.shape[1]):
                    shift_code = str(my_s.iloc[0, col]).strip()
                    if not shift_code or shift_code.lower() == "nan": continue
                    
                    target_date = f"{y}/{m}/{col}"
                    
                    if any(h in shift_code for h in ["休", "有給", "公休"]):
                        final_results.append(["T2_休日", target_date, "", target_date, "", "True", "", "T2"])
                    else:
                        # 今回は例として "T2" の時程表を使用
                        if "T2" in location_dic:
                            shift_cal("T2", target_date, col, shift_code, other_s, location_dic["T2"][0], final_results)
                
                # 結果表示
                if final_results:
                    df_res = pd.DataFrame(final_results, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
                    st.success("変換が完了しました！")
                    st.table(df_res)
                    
                    # ダウンロードボタン
                    csv = df_res.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button("3. Googleカレンダー用CSVを保存", csv, f"shift_{y}_{m}.csv", "text/csv")
                else:
                    st.warning("データが抽出されませんでした。PDFの形式を確認してください。")
