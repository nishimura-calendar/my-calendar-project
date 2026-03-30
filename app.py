import streamlit as st
import pandas as pd
import practice_0 as p0
import io

def main():
    st.set_page_config(page_title="シフト抽出システム", layout="wide")
    st.title("🗓️ 勤務シフト抽出システム")

    # サイドバー：ユーザー設定
    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("自分の名前を入力", value="西村")
    
    # PDFファイルのアップロード
    uploaded_file = st.file_uploader("勤務表PDFを選択してください", type="pdf")
    
    if uploaded_file and target_staff:
        # 1. 年月抽出
        uploaded_file.seek(0)
        y, m = p0.extract_year_month(uploaded_file)
        st.success(f"📅 対象年月: {y}年 {m}月 / 担当: {target_staff}さん")

        # 2. PDF解析（自分の行と、その下の特記事項行を取得）
        uploaded_file.seek(0)
        try:
            pdf_dic = p0.pdf_reader(uploaded_file, target_staff)
        except Exception as e:
            st.error(f"PDF解析エラー: {e}")
            st.stop()

        if not pdf_dic:
            st.warning(f"指定されたスタッフ「{target_staff}」が見つかりませんでした。")
            st.stop()

        # 3. 各場所（T1, T2など）ごとの処理
        for loc_key, pdf_data in pdf_dic.items():
            my_s = pdf_data[0] # PDFから抽出された自分の2行分データ
            final_rows = []
            
            # 日付（列）ごとにループ処理
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip() # 1段目（記号：A, B, C...）
                v2 = str(my_s.iloc[1, col]).strip() # 2段目（特記事項：10①19など）
                
                # 日付の組み立て
                dt = f"{y}/{m}/{col}"
                
                # 記号が空（休み等）の場合はスキップ
                if v1 == "" or "nan" in v1.lower():
                    continue

                # --- 判定: 2段目に特殊な時間指定(①や@)がある場合を解析 ---
                st_t, en_t, is_special = p0.parse_special_shift(v2)
                
                if is_special:
                    # 終日予定として「場所_記号」を登録
                    final_rows.append([f"{loc_key}_{v1}", dt, "", dt, "", "True", v2, loc_key])
                    # 特殊記号から抽出された勤務時間を登録
                    final_rows.append([f"{v1}勤務", dt, st_t, dt, en_t, "False", v2, loc_key])
                else:
                    # 時間指定がない場合、記号のみを表示
                    all_day = "True" if "本町" in v1 else "False"
                    final_rows.append([v1, dt, "", dt, "", all_day, v2, loc_key])

            # 結果があれば表示とダウンロードボタンを作成
            if final_rows:
                st.subheader(f"📍 {loc_key} の抽出結果")
                df_res = pd.DataFrame(final_rows, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
                
                # 重複を排除
                df_res = df_res.drop_duplicates().reset_index(drop=True)
                
                st.dataframe(df_res)
                
                csv = df_res.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label=f"{loc_key} のCSVを保存",
                    data=csv,
                    file_name=f"shift_{loc_key}_{y}{m}.csv",
                    mime="text/csv"
                )

if __name__ == "__main__":
    main()
