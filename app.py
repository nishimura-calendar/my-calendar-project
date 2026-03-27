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
        # Streamlit Cloudの Settings -> Secrets に 'gcp_service_account' という名前でJSONを貼っている想定です
        if "gcp_service_account" in st.secrets:
            info = st.secrets["gcp_service_account"]
            creds = service_account.Credentials.from_service_account_info(info)
            return build('drive', 'v3', credentials=creds)
        else:
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
    sheet_id = st.sidebar.text_input("1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG", value="")

    # Google Drive 認証サービスの作成
    service = get_gdrive_service()

    uploaded_file = st.file_uploader("勤務表PDFを選択してください", type="pdf")
    
    if uploaded_file and target_staff:
        # 1. 年月抽出
        uploaded_file.seek(0)
        y, m = p0.extract_year_month(uploaded_file)
        st.info(f"📅 対象年月: {y}年 {m}月 / 担当: {target_staff}さん")

        # 2. PDF解析（場所ごとのシフト読み取り）
        uploaded_file.seek(0)
        try:
            pdf_dic = p0.pdf_reader(uploaded_file, target_staff)
        except Exception as e:
            st.error(f"PDF解析エラー: {e}")
            st.stop()

        # 3. 時程表の取得（Google Drive から本番データを取得）
        time_dic = {}
        if service and sheet_id:
            with st.spinner('Google Driveから時程表を取得中...'):
                time_dic = p0.time_schedule_from_drive(service, sheet_id)
        
        # 認証情報がない、またはIDが空の場合のバックアップ処理
        if not time_dic:
            if not sheet_id:
                st.warning("⚠️ スプレッドシートIDが未入力です。テスト用データで動作を確認します。")
            else:
                st.warning("⚠️ 時程表を取得できませんでした。認証情報やIDを確認してください。テスト用データを使用します。")
            
            # テスト用ダミーデータ（動作確認用）
            time_dic = {
                "T2": pd.DataFrame([
                    ["", "記号", "10:00", "11:00", "12:00"],
                    ["", "A", "西村", "", ""],
                    ["", "B", "", "西村", ""]
                ])
            }

        # 4. データの統合（PDFの場所名と時程表を紐付け）
        integrated = p0.data_integration(pdf_dic, time_dic)

        # 5. メインループ：場所ごとにCSVデータを作成
        for loc_key, data_list in integrated.items():
            if len(data_list) < 3:
                continue
            
            my_s = data_list[0]    # PDFから抽出した自分のシフト（2行）
            t_s = data_list[2]     # スプレッドシートから取得した時程表
            
            final_rows = []
            # 時程表にある勤務記号（A, Bなど）のリストを作成
            valid_symbols = t_s.iloc[:, 1].astype(str).apply(p0.normalize_text).tolist()
            
            # 1日〜末日までスキャン
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip() # シフト記号
                v2 = str(my_s.iloc[1, col]).strip() # 備考欄（特殊時間など）
                dt = f"{y}/{m}/{col}"
                
                if v1 == "" or "nan" in v1.lower():
                    continue

                norm_v1 = p0.normalize_text(v1)

                # A. 記号勤務の場合（時程表から時間を引く）
                if norm_v1 in valid_symbols:
                    # 終日予定（記号名）
                    final_rows.append([v1, dt, "", dt, "", "True", "", loc_key])
                    
                    # 自分の名前が割り当てられている時間枠を探す
                    match_idx = t_s[t_s.iloc[:, 1].apply(p0.normalize_text) == norm_v1].index[0]
                    for ts_col in range(2, t_s.shape[1]):
                        time_label = t_s.iloc[0, ts_col]
                        assigned_staff = str(t_s.iloc[match_idx, ts_col]).strip()
                        if p0.normalize_text(assigned_staff) == p0.normalize_text(target_staff):
                            # 個別の勤務時間予定
                            final_rows.append([f"{v1}勤務", dt, time_label, dt, "", "False", "", loc_key])
                
                # B. 「本町」など備考に時間がある場合
                elif "本町" in v1:
                    final_rows.append(["本町", dt, "", dt, "", "True", "", loc_key])
                    st_t, en_t, ok = p0.parse_special_shift(v2)
                    if ok:
                        final_rows.append(["本町", dt, st_t, dt, en_t, "False", "", loc_key])
                
                # C. その他（有給、休日、その他直接入力された文字）
                else:
                    final_rows.append([v1, dt, "", dt, "", "False", "", loc_key])

            # --- 結果の表示とダウンロード ---
            if final_rows:
                st.subheader(f"📍 {loc_key} の抽出結果")
                df_res = pd.DataFrame(final_rows, columns=[
                    'Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'
                ])
                st.dataframe(df_res)
                
                # CSV変換（Googleカレンダー用）
                csv = df_res.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label=f"{loc_key}のCSVを保存",
                    data=csv,
                    file_name=f"shift_{loc_key}_{y}{m}.csv",
                    mime="text/csv"
                )

if __name__ == "__main__":
    main()
