import streamlit as st
import pandas as pd
import practice_0 as p0
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_gdrive_service():
    """
    StreamlitのSecretsから認証情報を取得してGoogle Drive APIサービスを作成します。
    """
    try:
        if "gcp_service_account" in st.secrets:
            info = st.secrets["gcp_service_account"]
            creds = service_account.Credentials.from_service_account_info(info)
            return build('drive', 'v3', credentials=creds)
        return None
    except Exception as e:
        st.error(f"認証エラーが発生しました: {e}")
        return None

def main():
    st.set_page_config(page_title="シフト抽出システム", layout="wide")
    st.title("🗓️ 勤務シフト抽出システム")

    # サイドバー：ユーザー設定
    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("自分の名前を入力", value="西村")
    
    # スプレッドシートID（必要に応じてデフォルト値を書き換えてください）
    default_id = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG" 
    sheet_id = st.sidebar.text_input("スプレッドシートID", value=default_id)

    # 認証サービスの作成
    service = get_gdrive_service()

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

        # 3. 時程表の取得（Google Driveから全場所のデータを取得）
        time_dic = {}
        if service and sheet_id:
            with st.spinner('スプレッドシート（時程表）を読み込み中...'):
                time_dic = p0.time_schedule_from_drive(service, sheet_id)
        
        if not time_dic:
            st.warning("⚠️ スプレッドシートからデータが取得できませんでした。記号からの時間抽出は行われません。")
        else:
            st.info("✅ 時程表の取得に成功しました。")

        # 4. 各場所（T1, T2など）ごとの処理
        for loc_key, pdf_data in pdf_dic.items():
            my_s = pdf_data[0] # PDFから抽出された自分の2行分データ
            final_rows = []
            
            # 日付（列）ごとにループ処理
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip() # 1段目（記号：A, B, C...）
                v2 = str(my_s.iloc[1, col]).strip() # 2段目（特記事項：10①19など）
                dt = f"{y}/{m}/{col}"
                
                # 記号が空（休み等）の場合はスキップ
                if v1 == "" or "nan" in v1.lower():
                    continue

                norm_v1 = p0.normalize_text(v1)
                norm_target = p0.normalize_text(target_staff)

                # --- 判定A: 2段目に特殊な時間指定(①や@)がある場合を最優先 ---
                st_t, en_t, is_special = p0.parse_special_shift(v2)
                if is_special:
                    # 終日予定として「場所_記号」を登録
                    final_rows.append([f"{loc_key}_{v1}", dt, "", dt, "", "True", v2, loc_key])
                    # 2段目の解析結果（①の前後）を勤務時間として登録
                    final_rows.append([f"{v1}勤務", dt, st_t, dt, en_t, "False", v2, loc_key])
                    continue

                # --- 判定B: スプレッドシート（時程表）を全探索して時間を探す ---
                found_in_sheet = False
                if time_dic:
                    for sheet_loc, t_s in time_dic.items():
                        # B列に記号(A, B等)が一致する行を探す
                        match_indices = t_s[t_s.iloc[:, 1].apply(p0.normalize_text) == norm_v1].index.tolist()
                        
                        for match_idx in match_indices:
                            # その行の各時間に「西村」が含まれているかチェック
                            for ts_col in range(2, t_s.shape[1]):
                                time_label = t_s.iloc[0, ts_col] # 1行目の時刻
                                staff_in_cell = p0.normalize_text(str(t_s.iloc[match_idx, ts_col]))
                                
                                # 名前が含まれていれば、その時間を抽出
                                if norm_target in staff_in_cell and norm_target != "":
                                    if not found_in_sheet:
                                        # 最初に見つかった時に終日予定を入れる
                                        final_rows.append([f"{loc_key}_{v1}", dt, "", dt, "", "True", "", loc_key])
                                        found_in_sheet = True
                                    
                                    # 勤務時間を追加
                                    final_rows.append([f"{v1}勤務", dt, str(time_label), dt, "", "False", "", loc_key])

                # --- 判定C: 時程表にも2段目にも情報がない場合（公休や単なる記号のみ） ---
                if not found_in_sheet:
                    # 「本町」が含まれる場合は終日予定扱いにする
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
