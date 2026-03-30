import streamlit as st
import pandas as pd
import practice_0 as p0
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_gdrive_service():
    try:
        if "gcp_service_account" in st.secrets:
            info = st.secrets["gcp_service_account"]
            creds = service_account.Credentials.from_service_account_info(info)
            return build('drive', 'v3', credentials=creds)
        return None
    except Exception as e:
        st.error(f"認証エラー: {e}"); return None

def main():
    st.set_page_config(page_title="シフト抽出システム", layout="wide")
    st.title("🗓️ 勤務シフト抽出システム")

    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("自分の名前を入力", value="西村")
    default_id = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG" 
    sheet_id = st.sidebar.text_input("スプレッドシートID", value=default_id)
    show_raw_sheet = st.sidebar.checkbox("読み取った時程表を確認する")

    service = get_gdrive_service()
    uploaded_file = st.file_uploader("勤務表PDFを選択してください", type="pdf")
    
    if uploaded_file and target_staff:
        uploaded_file.seek(0)
        y, m = p0.extract_year_month(uploaded_file)
        st.success(f"📅 対象年月: {y}年 {m}月 / 担当: {target_staff}さん")

        uploaded_file.seek(0)
        pdf_dic = p0.pdf_reader(uploaded_file, target_staff)

        time_dic = {}
        if service and sheet_id:
            with st.spinner('時程表読み込み中...'):
                time_dic = p0.time_schedule_from_drive(service, sheet_id)
        
        if time_dic:
            st.info("✅ 時程表の取得に成功しました。")
            if show_raw_sheet:
                with st.expander("📄 時程表の生データ"):
                    for loc_n, df_raw in time_dic.items():
                        st.write(f"**{loc_n}**"); st.dataframe(df_raw)

        for loc_key, pdf_data in pdf_dic.items():
            my_s = pdf_data[0] 
            final_rows = []
            
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip() # 記号
                v2 = str(my_s.iloc[1, col]).strip() # 2段目(時間情報等)
                dt = f"{y}/{m}/{col}"
                if v1 == "" or "nan" in v1.lower(): continue

                norm_v1 = p0.normalize_text(v1)
                norm_target = p0.normalize_text(target_staff)

                # --- A: 特殊時間(①や@)がある場合 ---
                st_t, en_t, is_special = p0.parse_special_shift(v2)
                if is_special:
                    final_rows.append([f"{loc_key}_{v1}", dt, "", dt, "", "True", v2, loc_key])
                    final_rows.append([f"{v1}勤務", dt, st_t, dt, en_t, "False", v2, loc_key])
                    continue

                # --- B: 時程表から検索 ---
                found_in_sheet = False
                for sheet_loc, t_s in time_dic.items():
                    match_indices = t_s[t_s.iloc[:, 1].apply(p0.normalize_text) == norm_v1].index.tolist()
                    for match_idx in match_indices:
                        for ts_col in range(2, t_s.shape[1]):
                            time_label = t_s.iloc[0, ts_col]
                            staff_in_cell = p0.normalize_text(str(t_s.iloc[match_idx, ts_col]))
                            if norm_target in staff_in_cell and norm_target != "":
                                if not found_in_sheet:
                                    final_rows.append([f"{loc_key}_{v1}", dt, "", dt, "", "True", "", loc_key])
                                    found_in_sheet = True
                                final_rows.append([f"{v1}勤務", dt, str(time_label), dt, "", "False", "", loc_key])

                # --- C: その他 ---
                if not found_in_sheet:
                    all_day = "True" if "本町" in v1 else "False"
                    final_rows.append([v1, dt, "", dt, "", all_day, v2, loc_key])

            if final_rows:
                st.subheader(f"📍 {loc_key}")
                df_res = pd.DataFrame(final_rows, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
                df_res = df_res.drop_duplicates().reset_index(drop=True)
                st.dataframe(df_res)
                csv = df_res.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(label=f"{loc_key}のCSVを保存", data=csv, file_name=f"shift_{loc_key}.csv", mime="text/csv")

if __name__ == "__main__":
    main()
