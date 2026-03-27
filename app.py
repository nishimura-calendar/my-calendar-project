import streamlit as st
import pandas as pd
import practice_0 
import os

# --- Google Drive API 認証用 (既存のコードがあれば差し替えてください) ---
# ※ service = get_gdrive_service() など、認証済みのオブジェクトが必要です。

def main():
    st.set_page_config(page_title="シフト抽出システム", layout="wide")
    st.title("🗓️ 勤務シフト抽出システム")
    st.write("PDFから勤務予定を読み取り、Googleカレンダー用CSVを作成します。")

    # 1. ユーザー入力
    target_staff = st.sidebar.text_input("名前を入力（例: 西村）", value="西村")
    sheet_id = st.sidebar.text_input("時程表スプレッドシートID", value="YOUR_SHEET_ID_HERE")

    uploaded_file = st.file_uploader("勤務表PDFをアップロードしてください", type="pdf")
    
    if uploaded_file and target_staff:
        # --- 実行フェーズ ---

        # (1) PDFから年月を取得
        y, m = p0.extract_year_month(uploaded_file)
        st.info(f"📅 対象年月: {y}年 {m}月 / 担当: {target_staff}さん")

        # (2) PDFから場所別の表を読み込み
        # practice_0の「def pdf_reader」を呼び出し
        pdf_dic = p0.pdf_reader(uploaded_file, target_staff)

        # (3) 時程表（Google Drive）からデータを取得
        # ※ 認証済みの service が必要です
        try:
            # 実際にはここに service を入れます
            time_dic = p0.time_schedule_from_drive(None, sheet_id) 
        except Exception as e:
            st.warning("時程表の取得にはGoogle認証が必要です。")
            time_dic = {} # テスト用

        # (4) データの統合（[my_s, other_s, t_s] の形にする）
        integrated = p0.data_integration(pdf_dic, time_dic)

        # (5) メインループ：場所ごとにCSVデータを作成
        for loc_key, data_list in integrated.items():
            my_s = data_list[0]    # 自分のシフト
            t_s = data_list[2]     # 時程表
            
            final_rows = []
            # 時程表のB列にある有効な記号（A, B, Cなど）
            valid_symbols = t_s.iloc[:, 1].astype(str).tolist()
            
            # 日付（列）ごとにスキャン
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip() # 1段目（記号や有給）
                v2 = str(my_s.iloc[1, col]).strip() # 2段目（備考）
                dt = f"{y}/{m}/{col}"
                
                if v1 == "" or "nan" in v1.lower():
                    continue

                # --- 判定ロジック ---

                # A. 時程表にある記号の場合
                if v1 in valid_symbols:
                    # 終日予定として1行追加
                    final_rows.append([v1, dt, "", dt, "", "True", "", loc_key])
                    
                    # 時程表の詳細時間をチェック
                    row_idx = t_s[t_s.iloc[:, 1] == v1].index[0]
                    for ts_col in range(2, t_s.shape[1]):
                        time_label = t_s.iloc[0, ts_col]
                        assigned = str(t_s.iloc[row_idx, ts_col]).strip()
                        
                        # 自分の名前と一致する時間枠だけを抽出
                        if assigned == target_staff:
                            final_rows.append([f"{v1}勤務", dt, time_label, dt, "", "False", "", loc_key])
                
                # B. 「本町」の場合
                elif "本町" in v1:
                    final_rows.append(["本町", dt, "", dt, "", "True", "", loc_key])
                    start_t, end_t, is_ok = p0.parse_special_shift(v2)
                    if is_ok:
                        final_rows.append(["本町", dt, start_t, dt, end_t, "False", "", loc_key])
                
                # C. その他（有給、休日、時程表にない記号など）
                else:
                    # 3/24-27の有給などもここで処理
                    final_rows.append([v1, dt, "", dt, "", "False", "", loc_key])

            # --- 結果表示とダウンロード ---
            if final_rows:
                st.subheader(f"📍 {loc_key} の抽出結果")
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
