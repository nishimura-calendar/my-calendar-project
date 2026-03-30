import streamlit as st
import pandas as pd
import practice_0 as p0
import io

def main():
    st.set_page_config(page_title="勤務シフト抽出", layout="wide")
    st.title("🗓️ 勤務シフト・時程表連携システム")

    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("抽出する名前を入力", value="西村")
    
    col1, col2 = st.columns(2)
    with col1:
        pdf_file = st.file_uploader("1. 勤務表PDFをアップロード", type="pdf")
    with col2:
        excel_file = st.file_uploader("2. 時程表エクセルをアップロード", type=["xlsx", "xls"])

    if pdf_file and excel_file and target_staff:
        # PDFから年月を抽出
        pdf_file.seek(0)
        y, m = p0.extract_year_month(pdf_file)
        st.info(f"📅 対象年月: {y}年 {m}月 / 名前: {target_staff}")

        # エクセルの解析（A列をキーとした辞書作成）
        time_dic = p0.read_excel_schedule(excel_file)
        
        # PDFの解析（場所ごとの記号取得）
        pdf_file.seek(0)
        pdf_dic = p0.pdf_reader(pdf_file, target_staff)

        if not pdf_dic:
            st.warning(f"「{target_staff}」さんの勤務が見つかりませんでした。")
            st.stop()

        for loc_key, my_s in pdf_dic.items():
            final_rows = []
            
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip() # 記号 (A, B, Cなど)
                v2 = str(my_s.iloc[1, col]).strip() # 特殊時間 (10.5①19など)
                dt = f"{y}/{m}/{col}"
                if v1 == "" or "nan" in v1.lower(): continue

                norm_v1 = p0.normalize_text(v1)
                norm_target = p0.normalize_text(target_staff)

                # --- ロジックA: 特殊時間の解析 ---
                st_t, en_t, is_special = p0.parse_special_shift(v2)
                if is_special:
                    final_rows.append([f"{loc_key}_{v1}", dt, "", dt, "", "True", v2, loc_key])
                    final_rows.append([f"{v1}勤務", dt, st_t, dt, en_t, "False", v2, loc_key])
                    continue

                # --- ロジックB: エクセルから時刻を抽出 ---
                found_in_excel = False
                if loc_key in time_dic:
                    df_block = time_dic[loc_key]
                    # B列(index 1)が記号(v1)と一致する行を探す
                    match_rows = df_block[df_block.iloc[:, 1].apply(p0.normalize_text) == norm_v1].index.tolist()
                    
                    for r_idx in match_rows:
                        # 2列目以降を横に見て、自分の名前が入っている列の「1行目の時刻」を取得
                        for c_idx in range(2, df_block.shape[1]):
                            time_label = str(df_block.iloc[0, c_idx])
                            cell_val = p0.normalize_text(str(df_block.iloc[r_idx, c_idx]))
                            
                            if norm_target in cell_val and norm_target != "":
                                if not found_in_excel:
                                    final_rows.append([f"{loc_key}_{v1}", dt, "", dt, "", "True", "", loc_key])
                                    found_in_excel = True
                                # 既に practice_0 内で数値は HH:MM に変換済み
                                if ":" in time_label:
                                    final_rows.append([f"{v1}勤務", dt, time_label, dt, "", "False", "", loc_key])

                # --- ロジックC: 連携できなかった場合（予備） ---
                if not found_in_excel:
                    all_day = "True" if "本町" in v1 or "休" in v1 else "False"
                    final_rows.append([v1, dt, "", dt, "", all_day, v2, loc_key])

            if final_rows:
                st.subheader(f"📍 場所: {loc_key}")
                df_res = pd.DataFrame(final_rows, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
                df_res = df_res.drop_duplicates()
                st.dataframe(df_res)
                
                csv_data = df_res.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(label=f"{loc_key}のCSVをダウンロード", data=csv_data, file_name=f"shift_{loc_key}.csv", mime="text/csv")

if __name__ == "__main__":
    main()
