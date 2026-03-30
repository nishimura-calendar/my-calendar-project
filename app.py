import streamlit as st
import pandas as pd
import practice_0 as p0
import io

def main():
    st.set_page_config(page_title="シフト抽出システム", layout="wide")
    st.title("🗓️ 勤務シフト抽出システム (エクセル管理版)")

    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("自分の名前を入力", value="西村")
    
    # ファイルアップロード
    col1, col2 = st.columns(2)
    with col1:
        pdf_file = st.file_uploader("1. 勤務表PDFを選択", type="pdf")
    with col2:
        excel_file = st.file_uploader("2. 時程表エクセルを選択", type=["xlsx", "xls"])

    if pdf_file and excel_file and target_staff:
        # 年月抽出
        pdf_file.seek(0)
        y, m = p0.extract_year_month(pdf_file)
        st.success(f"📅 {y}年 {m}月 / 担当: {target_staff}さん")

        # 時程表（エクセル）の読み込み
        time_dic = p0.read_excel_schedule(excel_file)
        if not time_dic:
            st.error("時程表エクセルの読み込みに失敗しました。")
            st.stop()

        # PDF解析
        pdf_file.seek(0)
        pdf_dic = p0.pdf_reader(pdf_file, target_staff)

        if not pdf_dic:
            st.warning(f"「{target_staff}」さんの情報が見つかりませんでした。")
            st.stop()

        # 抽出処理
        for loc_key, pdf_data in pdf_dic.items():
            my_s = pdf_data[0] 
            final_rows = []
            
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip() # 記号
                v2 = str(my_s.iloc[1, col]).strip() # 特殊表記(①など)
                dt = f"{y}/{m}/{col}"
                if v1 == "" or "nan" in v1.lower(): continue

                norm_v1 = p0.normalize_text(v1)
                norm_target = p0.normalize_text(target_staff)

                # --- A: PDFの2段目に丸文字や@がある場合を最優先 ---
                st_t, en_t, is_special = p0.parse_special_shift(v2)
                if is_special:
                    final_rows.append([f"{loc_key}_{v1}", dt, "", dt, "", "True", v2, loc_key])
                    final_rows.append([f"{v1}勤務", dt, st_t, dt, en_t, "False", v2, loc_key])
                    continue

                # --- B: 時程表（エクセル）から検索 ---
                found_in_excel = False
                # PDFの場所名と一致するシート（データブロック）を探す
                if loc_key in time_dic:
                    t_s = time_dic[loc_key]
                    # B列の記号が一致する行を特定
                    match_rows = t_s[t_s.iloc[:, 1].apply(p0.normalize_text) == norm_v1].index.tolist()
                    for r_idx in match_rows:
                        for c_idx in range(2, t_s.shape[1]):
                            time_label = t_s.iloc[0, c_idx]
                            cell_val = p0.normalize_text(str(t_s.iloc[r_idx, c_idx]))
                            if norm_target in cell_val and norm_target != "":
                                if not found_in_excel:
                                    final_rows.append([f"{loc_key}_{v1}", dt, "", dt, "", "True", "", loc_key])
                                    found_in_excel = True
                                final_rows.append([f"{v1}勤務", dt, str(time_label), dt, "", "False", "", loc_key])

                # --- C: その他（記号のみ） ---
                if not found_in_excel:
                    all_day = "True" if "本町" in v1 else "False"
                    final_rows.append([v1, dt, "", dt, "", all_day, v2, loc_key])

            if final_rows:
                st.subheader(f"📍 {loc_key} の結果")
                df_res = pd.DataFrame(final_rows, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
                df_res = df_res.drop_duplicates().reset_index(drop=True)
                st.dataframe(df_res)
                
                csv = df_res.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(label=f"{loc_key}のCSVを保存", data=csv, file_name=f"shift_{loc_key}.csv", mime="text/csv")

if __name__ == "__main__":
    main()
