import streamlit as st
import pandas as pd
import unicodedata
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from practice_0 import (
    pdf_reader, extract_year_month, time_schedule_from_drive, 
    data_integration, parse_special_shift
)

def format_time(val):
    """Excelのシリアル値または数値を時刻文字列(HH:MM)に変換"""
    try:
        num = float(val)
        h = int(num * 24 if num < 1 else num)
        m = int(round((num * 24 - h) * 60 if num < 1 else (num - h) * 60))
        return f"{h:02d}:{m:02d}"
    except:
        return str(val)

def shift_cal(loc_name, target_date, day_col, shift_info, other_s, t_s, final_rows):
    """
    エクセル資料の「引渡し・引受け」概念を忠実に再現したロジック
    """
    time_headers = [format_time(t_s.iloc[0, c]) for c in range(t_s.shape[1])]
    clean_info = unicodedata.normalize('NFKC', str(shift_info)).strip()
    
    my_time_row = t_s[t_s.iloc[:, 1].astype(str).str.strip() == clean_info]
    if my_time_row.empty:
        return

    # 背景（終日）
    final_rows.append([f"{loc_name}_{clean_info}", target_date, "", target_date, "", "True", "", loc_name])
    
    # --- 引受け・引渡し相手の特定 ---
    # 同じ日の同じシフト記号を持つ人を「相手」として抽出
    opponents = []
    for r_idx in range(len(other_s)):
        cell_val = unicodedata.normalize('NFKC', str(other_s.iloc[r_idx, day_col])).strip()
        staff_name = str(other_s.iloc[r_idx, 0]).replace('\n', '').strip()
        if clean_info == cell_val and "西村" not in staff_name and staff_name != "":
            opponents.append(staff_name)
    
    opponent_str = " / ".join(list(set(opponents)))
    
    # 相手がいる場合は「相手名」、いない場合は「(無)」とする（資料のtaking_over/handing_overに対応）
    person_context = opponent_str if opponent_str else ""

    prev_val = ""
    for t_col in range(2, t_s.shape[1]):
        val = str(my_time_row.iloc[0, t_col]).strip()
        # 有効な業務名のみ抽出
        actual_val = val if val not in ["出勤","退勤","実働時間","休憩時間","深夜","nan","","0","0.0"] else ""

        if actual_val != prev_val:
            # 【変化点：前の業務を閉じる】
            if len(final_rows) > 0 and final_rows[-1][4] == "" and final_rows[-1][5] == "False":
                final_rows[-1][4] = time_headers[t_col]
            
            # 【変化点：新しい業務を開始する】
            if actual_val != "":
                # エクセル資料の ① subject={handing_over} => {taking_over} の再現
                # handing_over: 前の業務（または相手からの引継ぎ）
                # taking_over: これから始まる業務
                
                if prev_val == "":
                    # 勤務開始時：相手から業務を「引受ける」
                    prefix = f"({person_context})引受" if person_context else ""
                    subj = f"{prefix}=>【{actual_val}】"
                else:
                    # 業務交代時：前の業務を次の業務へ「繋ぐ」
                    subj = f"({prev_val})=>【{actual_val}】"
                
                final_rows.append([subj, target_date, time_headers[t_col], target_date, "", "False", "", loc_name])
            
            # もし業務が終了（actual_valが空）になった場合、
            # 直前のイベント名に「引渡し」を付与するなどの調整も可能ですが、
            # まずはこの「引受け」開始の形で午前中の精度に戻るか確認してください。
            
            prev_val = actual_val
            
# --- Streamlit UI ---
st.set_page_config(page_title="シフト変換ツール", layout="wide")
st.title("📅 シフト一括変換システム")
st.write("PDFからカレンダー用CSVを作成します（本町・複数勤務地・ペア名抽出対応）")

up = st.file_uploader("勤務予定表(PDF)をアップロードしてください", type="pdf")

if up and st.button("変換を実行する"):
    if "gcp_service_account" not in st.secrets:
        st.error("エラー: Streamlit Secretsに 'gcp_service_account' が設定されていません。")
    else:
        # Google Drive API 準備
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        service = build('drive', 'v3', credentials=creds)
        
        # データの読み込みと統合
        with st.spinner('データを解析中...'):
            # 時程表（Excel）の取得
            t_dic = time_schedule_from_drive(service, "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG")
            # PDFから年月の抽出
            y, m = extract_year_month(up)
            # PDFから各勤務地のデータ抽出
            p_dic = pdf_reader(up, "西村文宏")
            # 勤務地名でマージ
            integrated = data_integration(p_dic, t_dic)
        
        if not integrated:
            st.warning("該当する勤務データが見つかりませんでした。")
        
        for loc_key, data in integrated.items():
            my_s, other_s, t_s = data[0], data[1], data[2]
            res = []
            
            # 日ごとのループ（1列目は名前列なので2列目から）
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip() # 上段（通常はシフト記号）
                v2 = str(my_s.iloc[1, col]).strip() # 下段（通常は空欄、本町時は時刻）
                dt = f"{y}/{m}/{col}"
                
                # A. 特殊判定（@が含まれる場合: 本町など）
                s_t, e_t, is_spec = parse_special_shift(v2)
                if is_spec:
                    res.append([f"{v1}_{v2}", dt, s_t, dt, e_t, "False", "", loc_key])
                    continue
                
                # B. 通常判定
                target_shift = v1 if v1 and "nan" not in v1.lower() else ""
                if not target_shift:
                    continue
                
                if any(h in target_shift for h in ["休", "有給", "公休"]):
                    res.append([f"{loc_key}_休日", dt, "", dt, "", "True", "", loc_key])
                else:
                    # 時程表に基づいた詳細計算へ
                    shift_cal(loc_key, dt, col, target_shift, other_s, t_s, res)
            
            # 結果の表示とダウンロード
            if res:
                st.subheader(f"📍 勤務地: {loc_key}")
                df_out = pd.DataFrame(res, columns=[
                    'Subject','Start Date','Start Time','End Date','End Time',
                    'All Day Event','Description','Location'
                ])
                st.dataframe(df_out)
                csv = df_out.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label=f"{loc_key}のCSVをダウンロード",
                    data=csv,
                    file_name=f"shift_{loc_key}_{y}{m}.csv",
                    mime='text/csv'
                )

st.info("※ModuleNotFoundErrorが出る場合は、web_practice_0.pyが同じフォルダにあるか確認してください。")
