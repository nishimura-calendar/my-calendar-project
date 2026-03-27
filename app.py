import streamlit as st
import pandas as pd
import practice_0 as p0 
import io

def main():
    st.set_page_config(page_title="シフト抽出システム", layout="wide")
    st.title("🗓️ 勤務シフト抽出システム")

    target_staff = st.sidebar.text_input("自分の名前を入力", value="西村")
    sheet_id = st.sidebar.text_input("時程表スプレッドシートID", value="YOUR_SHEET_ID")

    uploaded_file = st.file_uploader("勤務表PDFを選択", type="pdf")
    
    if uploaded_file and target_staff:
        # --- 重要：読み取り位置を先頭に戻す ---
        uploaded_file.seek(0)
        
        # 1. 年月の抽出
        try:
            y, m = p0.extract_year_month(uploaded_file)
            st.info(f"📅 対象年月: {y}年 {m}月")
        except Exception as e:
            st.error(f"年月抽出エラー: {e}")
            st.stop()

        # --- 次の処理の前にもう一度先頭に戻す ---
        uploaded_file.seek(0)

        # 2. PDF読み取り
        try:
            pdf_dic = p0.pdf_reader(uploaded_file, target_staff)
        except Exception as e:
            st.error(f"PDF解析エラー: {e}")
            st.stop()
　　　　 # 3. 時程表の取得（Google Drive 連携）
        try:
            # ここで実際に Google Drive からデータを取得します
            # ※ service オブジェクトが定義されていることが前提です
            time_dic = p0.time_schedule_from_drive(service, sheet_id) 
            
            if not time_dic:
                st.warning("スプレッドシートからデータが見つかりませんでした。IDを確認してください。")
        except Exception as e:
            st.error(f"時程表の取得中にエラーが発生しました: {e}")
            time_dic = {}
        # 4. データの統合
        integrated = p0.data_integration(pdf_dic, time_dic)

        # 5. メインループ
        for loc_key, data_list in integrated.items():
            my_s = data_list[0]
            t_s = data_list[2]
            final_rows = []
            
            valid_symbols = t_s.iloc[:, 1].astype(str).tolist()
            
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip()
                v2 = str(my_s.iloc[1, col]).strip()
                dt = f"{y}/{m}/{col}"
                
                if v1 == "" or "nan" in v1.lower():
                    continue

                if v1 in valid_symbols:
                    final_rows.append([v1, dt, "", dt, "", "True", "", loc_key])
                    row_idx = t_s[t_s.iloc[:, 1] == v1].index[0]
                    for ts_col in range(2, t_s.shape[1]):
                        time_label = t_s.iloc[0, ts_col]
                        assigned = str(t_s.iloc[row_idx, ts_col]).strip()
                        if assigned == target_staff:
                            final_rows.append([f"{v1}勤務", dt, time_label, dt, "", "False", "", loc_key])
                elif "本町" in v1:
                    final_rows.append(["本町", dt, "", dt, "", "True", "", loc_key])
                    st_t, en_t, ok = p0.parse_special_shift(v2)
                    if ok:
                        final_rows.append(["本町", dt, st_t, dt, en_t, "False", "", loc_key])
                else:
                    final_rows.append([v1, dt, "", dt, "", "False", "", loc_key])

            if final_rows:
                st.subheader(f"📍 {loc_key}")
                df_res = pd.DataFrame(final_rows, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
                st.dataframe(df_res)
                csv = df_res.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(f"CSV保存({loc_key})", csv, f"shift_{loc_key}.csv")

if __name__ == "__main__":
    main()
