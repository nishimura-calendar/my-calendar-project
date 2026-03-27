import streamlit as st
import pandas as pd
import practice_0 as p0
import io

def main():
    st.set_page_config(page_title="シフト抽出システム", layout="wide")
    st.title("🗓️ 勤務シフト抽出システム")

    # サイドバー：ユーザー設定
    target_staff = st.sidebar.text_input("自分の名前を入力", value="西村")
    sheet_id = st.sidebar.text_input("時程表スプレッドシートID", value="")

    # 注意：本来はここでGoogle Driveの認証を行い 'service' を作成します。
    # すでに認証コードをお持ちの場合は、ここで service を定義してください。
    # service = get_gdrive_service()

    uploaded_file = st.file_uploader("勤務表PDFを選択してください", type="pdf")
    
    if uploaded_file and target_staff:
        # 1. 読み取り位置をリセットして年月抽出
        uploaded_file.seek(0)
        y, m = p0.extract_year_month(uploaded_file)
        st.info(f"📅 対象年月: {y}年 {m}月 / 担当: {target_staff}さん")

        # 2. PDFから場所別の表を読み込み
        uploaded_file.seek(0)
        try:
            pdf_dic = p0.pdf_reader(uploaded_file, target_staff)
        except Exception as e:
            st.error(f"PDF解析エラー: {e}")
            st.stop()

        # 3. 時程表の取得（Google Drive 連携）
        try:
            # locals() または globals() に 'service' が存在するか確認
            if 'service' in locals() or 'service' in globals():
                time_dic = p0.time_schedule_from_drive(service, sheet_id) 
                if not time_dic:
                    st.info("テスト用データで動作確認します。")
                    time_dic = {
                        "T2": pd.DataFrame([
                            ["", "記号", "10:00", "11:00", "12:00"], # 時間ラベル
                            ["", "A", "西村", "", ""],            # A記号なら10時に西村
                            ["", "B", "", "西村", ""]             # B記号なら11時に西村
                        ])
                    }
                else:
                st.warning("時程表の取得にはGoogle認証(serviceオブジェクト)が必要です。")
                time_dic = {}
        except Exception as e:
            st.error(f"時程表の取得中にエラーが発生しました: {e}")
            time_dic = {}

        # 4. データの統合 ([my_s, other_s, t_s])
        integrated = p0.data_integration(pdf_dic, time_dic)

        # 5. メインループ
        for loc_key, data_list in integrated.items():
            if len(data_list) < 3:
                continue
                
            my_s = data_list[0]    # 自分のシフト
            t_s = data_list[2]     # 時程表
            
            final_rows = []
            valid_symbols = t_s.iloc[:, 1].astype(str).apply(p0.normalize_text).tolist()
            
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip()
                v2 = str(my_s.iloc[1, col]).strip()
                dt = f"{y}/{m}/{col}"
                
                if v1 == "" or "nan" in v1.lower():
                    continue

                norm_v1 = p0.normalize_text(v1)

                # A. 時程表にある記号(A, B等)
                if norm_v1 in valid_symbols:
                    final_rows.append([v1, dt, "", dt, "", "True", "", loc_key])
                    # 記号一致行から時間を抽出
                    match_idx = t_s[t_s.iloc[:, 1].apply(p0.normalize_text) == norm_v1].index[0]
                    for ts_col in range(2, t_s.shape[1]):
                        time_label = t_s.iloc[0, ts_col]
                        assigned_staff = str(t_s.iloc[match_idx, ts_col]).strip()
                        if p0.normalize_text(assigned_staff) == p0.normalize_text(target_staff):
                            final_rows.append([f"{v1}勤務", dt, time_label, dt, "", "False", "", loc_key])
                
                # B. 「本町」判定
                elif "本町" in v1:
                    final_rows.append(["本町", dt, "", dt, "", "True", "", loc_key])
                    st_t, en_t, ok = p0.parse_special_shift(v2)
                    if ok:
                        final_rows.append(["本町", dt, st_t, dt, en_t, "False", "", loc_key])
                
                # C. その他（有給など）
                else:
                    final_rows.append([v1, dt, "", dt, "", "False", "", loc_key])

            if final_rows:
                st.subheader(f"📍 {loc_key} の抽出結果")
                df_res = pd.DataFrame(final_rows, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
                st.dataframe(df_res)
                csv = df_res.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(f"{loc_key}のCSVを保存", csv, f"shift_{loc_key}.csv")

if __name__ == "__main__":
    main()
