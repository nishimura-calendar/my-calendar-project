import streamlit as st
import pandas as pd
import practice_0 as p0
import fitz
import re
from googleapiclient.discovery import build
from google.oauth2 import service_account

# スプレッドシートID
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service():
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return build('sheets', 'v4', credentials=creds)

def display_error_and_stop(msg, pdf_path=None):
    """エラーを表示してPDFプレビューを出し、プログラムを停止する"""
    st.error(msg)
    if pdf_path:
        doc = fitz.open(pdf_path)
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
        st.image(pix.tobytes("png"), caption="不一致箇所の確認用PDF")
    st.stop()

st.set_page_config(layout="wide")
st.title("シフトカレンダー生成システム")

# 時程表（スプレッドシート）の読込
if 'time_dic' not in st.session_state:
    try:
        st.session_state.time_dic = p0.load_master_from_sheets(get_service(), SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表の読み込みに失敗しました: {e}"); st.stop()

uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type="pdf")

if uploaded_file:
    pdf_path = "temp.pdf"
    with open(pdf_path, "wb") as f: f.write(uploaded_file.getvalue())
    
    # ファイル名から年月抽出
    fname = uploaded_file.name
    y_match = re.search(r'(\d{4})', fname)
    m_match = re.search(r'(\d{1,2})', fname)
    
    if not (y_match and m_match):
        st.warning("ファイル名から年月を特定できません。")
        y = st.number_input("年", value=2026)
        m = st.number_input("月", value=1, min_value=1, max_value=12)
        if not st.button("年月を確定して次へ"): st.stop()
    else:
        y, m = int(y_match.group(1)), int(m_match.group(1))

    # --- 第1関門・第2関門 判定 ---
    res, msg = p0.analyze_pdf_structure(pdf_path, y, m)
    if not res:
        display_error_and_stop(msg, pdf_path)
    
    location = res['location']
    
    # 第2関門：勤務地が時程表にあるかチェック
    if location not in st.session_state.time_dic:
        display_error_and_stop(f"第2関門不通過：【{location}】は時程表に設定されていません。", pdf_path)

    # --- 第3関門 判定 ---
    st.success(f"第2関門通過：勤務地 【{location}】")
    target_staff = st.selectbox("シフトカレンダーを作成するスタッフを選んで下さい。", options=["該当なし"] + res['staff_list'])
    
    if target_staff == "該当なし":
        st.info("スタッフを選択してください。")
        st.stop()

    # データの抽出と辞書登録
    shift_data = p0.extract_target_data(res['df'], target_staff, location)
    if not shift_data:
        display_error_and_stop(f"第3関門不通過：スタッフ【{target_staff}】のデータが見つかりません。")

    st.session_state.final_result = {
        location: {
            "time_schedule": st.session_state.time_dic[location],
            "my_daily_shift": shift_data['my_daily_shift'],
            "other_daily_shift": shift_data['other_daily_shift']
        }
    }

    # --- <プログラムのメイン工程> ---
    if st.button("CSVデータを生成する"):
        data = st.session_state.final_result[location]
        my_shift = data["my_daily_shift"]
        other_shift = data["other_daily_shift"]
        t_sched = data["time_schedule"]
        last_name_me = p0.get_last_name(target_staff)
        
        final_rows = []
        # 日付列を巡回
        for col in range(1, my_shift.shape[1]):
            target_date = f"{y}/{m:02d}/{col:02d}"
            s_code = str(my_shift.iloc[0, col]).strip().replace('\n', '')
            d_info = str(my_shift.iloc[1, col]).strip().replace('\n', '')

            if not s_code or s_code == "なし": continue

            # A. 休日関係 (赤)
            if any(x in s_code for x in ["休", "公休", "有給", "有休"]):
                final_rows.append([f"{last_name_me}_{s_code}", target_date, "", target_date, "", "True", "", location])
            
            # B. 本町対応 (工程6 - 青)
            elif "本町" in s_code or "本町" in d_info:
                st_t, en_t = p0.parse_honmachi_time(d_info)
                final_rows.append([f"{last_name_me}_本町", target_date, st_t, target_date, en_t, "False", f"詳細:{d_info}", location])
            
            # C. 通常シフト (時程表あり - 緑)
            elif (t_sched.iloc[:, 1] == s_code).any():
                final_rows.append([f"{location}_{s_code}", target_date, "", target_date, "", "True", "", location])
                p0.shift_cal(last_name_me, target_date, col, s_code, other_shift, t_sched, final_rows)
            
            # D. その他イベント (青)
            else:
                final_rows.append([f"{last_name_me}_{s_code}", target_date, "", target_date, "", "True", f"詳細:{d_info}", location])

        # 出力表示
        cal_df = pd.DataFrame(final_rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
        st.write("### 生成されたカレンダーデータ")
        st.dataframe(cal_df, hide_index=True)
        
        csv = cal_df.to_csv(index=False, encoding='utf_8_sig')
        st.download_button("CSVを保存", csv, f"{target_staff}.csv", "text/csv")
