import streamlit as st
import pandas as pd
import practice_0 

def main():
    st.set_page_config(page_title="シフト抽出システム", layout="wide")
    st.title("🗓️ 勤務シフト抽出システム")

    # サイドバーで個人設定（将来の拡張用）
    target_staff = st.sidebar.text_input("抽出する名前を入力（例: 西村）", value="西村")

    uploaded_file = st.file_uploader("勤務表PDFをアップロードしてください", type="pdf")
    
    if uploaded_file:
        # 1. 年月の抽出
        y, m = p0.extract_year_month(uploaded_file)
        st.info(f"📅 対象年月: {y}年 {m}月")

        # 2. PDF読み取り（pdf_dic の作成）
        # ※ practice_0.pdf_reader は [my_s, other_s] を返す想定
        pdf_dic = p0.pdf_reader(uploaded_file, target_staff)
        
        # 3. 時程表の取得（Google Drive）
        # ※ 認証済みの service と SHEET_ID を使用
        SHEET_ID = "YOUR_SPREADSHEET_ID_HERE" 
        try:
            # practice_0 の関数で時間を HH:MM 変換済みで取得
            time_dic = p0.time_schedule_from_drive(None, SHEET_ID) 
        except:
            st.error("時程表の取得に失敗しました。IDや認証を確認してください。")
            st.stop()

        # 4. データの統合（[my_s, other_s, t_s] のリストを作成）
        integrated = p0.data_integration(pdf_dic, time_dic)

        # 5. メインループ：場所（key）ごとの処理
        for loc_key, data_list in integrated.items():
            my_s = data_list[0]    # 自分の2行
            # other_s = data_list[1] # 全員の表（今回は使用せず）
            t_s = data_list[2]     # 時程表
            
            final_rows = []
            # 時程表のB列にある記号を取得
            valid_symbols = t_s.iloc[:, 1].astype(str).tolist()
            
            # 日付ごとのループ（1日から末日まで）
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip() # 1段目
                v2 = str(my_s.iloc[1, col]).strip() # 2段目
                dt = f"{y}/{m}/{col}"
                
                if v1 == "" or "nan" in v1.lower():
                    continue

                # --- 判定ロジック ---

                # (A) 時程表に記号がある場合
                if v1 in valid_symbols:
                    # まずPDFの表記で一行目(True)を作成
                    final_rows.append([v1, dt, "", dt, "", "True", "", loc_key])
                    
                    # 時程表から詳細(False)を抽出
                    # t_s の 1行目はすでに HH:MM 形式
                    row_idx = t_s[t_s.iloc[:, 1] == v1].index[0]
                    for ts_col in range(2, t_s.shape[1]):
                        time_label = t_s.iloc[0, ts_col]
                        staff_name = str(t_s.iloc[row_idx, ts_col]).strip()
                        
                        if staff_name == target_staff:
                            # 自分の名前が一致する枠だけを追加
                            final_rows.append([f"{v1}勤務", dt, time_label, dt, "", "False", "", loc_key])
                
                # (B) 本町判定
                elif "本町" in v1:
                    final_rows.append(["本町", dt, "", dt, "", "True", "", loc_key])
                    st_t, en_t, ok = p0.parse_special_shift(v2)
                    if ok:
                        final_rows.append(["本町", dt, st_t, dt, en_t, "False", "", loc_key])
                
                # (C) それ以外（有給、休日、その他）
                else:
                    # 3/24-27の有給などはここ。subject=v1, All Day=False
                    final_rows.append([v1, dt, "", dt, "", "False", "", loc_key])

            # --- CSV出力 ---
            if final_rows:
                st.subheader(f"📍 抽出結果: {loc_key}")
                df_res = pd.DataFrame(final_rows, columns=[
                    'Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'
                ])
                st.dataframe(df_res)
                
                csv = df_res.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label=f"{loc_key}のCSVを保存",
                    data=csv,
                    file_name=f"shift_{loc_key}_{y}{m}.csv",
                    mime="text/csv"
                )

if __name__ == "__main__":
    main()
