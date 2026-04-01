import streamlit as st
import pandas as pd
import practice_0 as p0
import io

def main():
    st.set_page_config(page_title="勤務連携システム", layout="wide")
    st.title("🗓️ 勤務シフト・時程表連携システム")

    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("抽出名", value="西村")
    
    col1, col2 = st.columns(2)
    with col1:
        pdf_file = st.file_uploader("勤務表PDF", type="pdf")
    with col2:
        excel_file = st.file_uploader("時程表エクセル", type=["xlsx", "xls"])

    if pdf_file and excel_file and target_staff:
        # PDFから年月抽出
        pdf_file.seek(0)
        with io.BytesIO(pdf_file.read()) as pdf_stream:
            with io.BytesIO(pdf_file.getvalue()) as pdf_stream2:
                # 辞書化
                time_dic = p0.read_excel_schedule(excel_file)
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                
                # 年月
                import pdfplumber
                with pdfplumber.open(pdf_stream2) as pdf:
                    header_text = pdf.pages[0].extract_text() or ""
                    m = pd.Series(re.findall(r'(20\d{2})年(\d{1,2})月', header_text))
                    y, mo = ("2026", "1") if m.empty else m[0]

        if not pdf_dic:
            st.warning("データが見つかりませんでした。")
            st.stop()

        for loc_key, data_list in pdf_dic.items():
            my_daily_shift = data_list[0]
            final_rows = []
            
            for col in range(1, my_daily_shift.shape[1]):
                shift_code = str(my_daily_shift.iloc[0, col]).strip()
                second_row_val = str(my_daily_shift.iloc[1, col]).strip()
                dt = f"{y}/{mo}/{col}"
                
                if shift_code == "" or "nan" in shift_code.lower(): continue
                norm_code = p0.normalize_text(shift_code)
                norm_target = p0.normalize_text(target_staff)

                # 1. 休日判定
                if "休" in norm_code:
                    final_rows.append([shift_code, dt, "", dt, "", "True", "", loc_key])
                    continue

                # 2. 本町判定
                if "本町" in norm_code:
                    final_rows.append(["本町", dt, "", dt, "", "True", "", loc_key])
                    # 2段目を確認して時間指定作成
                    st_t, en_t, ok = p0.get_time_from_mark(second_row_val)
                    if ok:
                        final_rows.append(["本町", dt, st_t, dt, en_t, "False", second_row_val, loc_key])
                    continue

                # 3. 時程表（time_schedule）の確認
                found_in_excel = False
                if loc_key in time_dic:
                    df_block = time_dic[loc_key]
                    # B列(index 1)が記号と一致するか
                    match_df = df_block[df_block.iloc[:, 1].apply(p0.normalize_text) == norm_code]
                    
                    if not match_df.empty:
                        # Subject=Key+勤務コード、1日の予定=True
                        final_rows.append([f"{loc_key}_{shift_code}", dt, "", dt, "", "True", "", loc_key])
                        found_in_excel = True
                        
                        # 自分の名前が入っている列をスキャンして時間を抽出
                        for _, row_data in match_df.iterrows():
                            for c_idx in range(3, df_block.shape[1]):
                                time_label = str(df_block.iloc[0, c_idx])
                                cell_val = p0.normalize_text(str(row_data.iloc[c_idx]))
                                if norm_target in cell_val and ":" in time_label:
                                    final_rows.append([f"{shift_code}勤務", dt, time_label, dt, "", "False", "", loc_key])

                # 4. 時程表になければ my_daily_shift 通り
                if not found_in_excel:
                    final_rows.append([shift_code, dt, "", dt, "", "True", second_row_val, loc_key])

            if final_rows:
                st.subheader(f"📍 {loc_key}")
                df_res = pd.DataFrame(final_rows, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location']).drop_duplicates()
                st.dataframe(df_res)
                csv = df_res.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(f"{loc_key}のCSV保存", csv, f"shift_{loc_key}.csv", "text/csv")

if __name__ == "__main__":
    main()
