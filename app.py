import streamlit as st
import pandas as pd
import practice_0 as p0

def main():
    st.set_page_config(page_title="勤務シフト抽出", layout="wide")
    st.title("🗓️ 勤務シフト連携システム（最新ロジック版）")

    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("抽出する名前", value="西村")
    
    col1, col2 = st.columns(2)
    with col1:
        pdf_file = st.file_uploader("1. 勤務表PDF", type="pdf")
    with col2:
        excel_file = st.file_uploader("2. 時程表エクセル", type=["xlsx", "xls"])

    if pdf_file and excel_file and target_staff:
        pdf_file.seek(0); y, m = p0.extract_year_month(pdf_file)
        time_dic = p0.read_excel_schedule(excel_file)
        pdf_file.seek(0); pdf_dic = p0.pdf_reader(pdf_file, target_staff)

        if not pdf_dic:
            st.warning("データが見つかりませんでした。")
            st.stop()

        for loc_key, my_s in pdf_dic.items():
            final_rows = []
            
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip() # my_daily_shift (記号)
                v2 = str(my_s.iloc[1, col]).strip() # 特記/2段目
                dt = f"{y}/{m}/{col}"
                if v1 == "" or "nan" in v1.lower(): continue

                norm_v1 = p0.normalize_text(v1)
                norm_target = p0.normalize_text(target_staff)

                # 1. 休日処理
                if "休" in v1:
                    final_rows.append([v1, dt, "", dt, "", "True", "", loc_key])
                    continue

                # 2. 本町処理
                if "本町" in v1:
                    # 終日予定を追加
                    final_rows.append(["本町", dt, "", dt, "", "True", "", loc_key])
                    # 2段目から時間を抽出して時間指定予定を追加
                    st_t, en_t, found = p0.get_time_from_mark(v2)
                    if found:
                        final_rows.append(["本町", dt, st_t, dt, en_t, "False", v2, loc_key])
                    continue

                # 3. 時程表（time_schedule）の確認
                found_in_excel = False
                if loc_key in time_dic:
                    df_block = time_dic[loc_key]
                    # B列に記号があるか確認
                    match_rows = df_block[df_block.iloc[:, 1].apply(p0.normalize_text) == norm_v1].index.tolist()
                    
                    if match_rows:
                        # Subject = Key + 勤務コード、終日=True
                        final_rows.append([f"{loc_key}_{v1}", dt, "", dt, "", "True", "", loc_key])
                        found_in_excel = True
                        
                        # 詳細な時間別シフトの作成 (shift_cal相当のロジック)
                        for r_idx in match_rows:
                            for c_idx in range(2, df_block.shape[1]):
                                time_label = str(df_block.iloc[0, c_idx])
                                cell_val = p0.normalize_text(str(df_block.iloc[r_idx, c_idx]))
                                if norm_target in cell_val and ":" in time_label:
                                    final_rows.append([f"{v1}勤務", dt, time_label, dt, "", "False", "", loc_key])

                # 4. 時程表になかった場合、またはその他の場合
                if not found_in_excel:
                    # Subject = my_daily_shiftの記載通り、終日=True
                    final_rows.append([v1, dt, "", dt, "", "True", v2, loc_key])

            if final_rows:
                st.subheader(f"📍 場所: {loc_key}")
                df_res = pd.DataFrame(final_rows, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location']).drop_duplicates()
                st.dataframe(df_res)
                csv = df_res.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(f"{loc_key}のCSV保存", csv, f"shift_{loc_key}.csv", "text/csv")

if __name__ == "__main__":
    main()
