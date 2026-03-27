import streamlit as st
import pandas as pd
import practice_0 as p0
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_gdrive_service():
    """
    Google Drive API サービスを作成し、失敗した場合はエラー内容を画面に出します。
    """
    try:
        if "gcp_service_account" in st.secrets:
            info = st.secrets["gcp_service_account"]
            creds = service_account.Credentials.from_service_account_info(info)
            return build('drive', 'v3', credentials=creds)
        else:
            # Secrets 自体が読み込めていない場合
            st.error("【原因1】Secretsの設定が見つかりません。Streamlit管理画面の 'Secrets' に [gcp_service_account] の記述があるか確認してください。")
            return None
    except Exception as e:
        st.error(f"【原因2】認証情報の形式エラー: {e}")
        return None

def main():
    st.set_page_config(page_title="シフト抽出システム", layout="wide")
    st.title("🗓️ 勤務シフト抽出システム")

    # サイドバー設定
    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("自分の名前を入力", value="西村")
    
    # 時程表のスプレッドシートID
    # ※ 西村さんの正しいIDに書き換えてください
    default_id = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG" 
    sheet_id = st.sidebar.text_input("時程表スプレッドシートID", value=default_id)

    service = get_gdrive_service()

    uploaded_file = st.file_uploader("勤務表PDFを選択してください", type="pdf")
    
    if uploaded_file and target_staff:
        uploaded_file.seek(0)
        y, m = p0.extract_year_month(uploaded_file)
        st.info(f"📅 対象年月: {y}年 {m}月 / 担当: {target_staff}さん")

        uploaded_file.seek(0)
        try:
            pdf_dic = p0.pdf_reader(uploaded_file, target_staff)
        except Exception as e:
            st.error(f"PDF解析エラー: {e}")
            st.stop()

        # 時程表取得の試行
        time_dic = {}
        if service and sheet_id:
            with st.spinner('本物の時程表を取得中...'):
                try:
                    time_dic = p0.time_schedule_from_drive(service, sheet_id)
                    if not time_dic:
                        st.error("【原因3】スプレッドシートが見つかりません。IDが正しいか、または client_email に共有設定がされているか確認してください。")
                except Exception as e:
                    st.error(f"【原因4】Google Drive アクセス拒否: {e}")
        
        # 取得失敗時のテストデータ表示
        if not time_dic:
            st.warning("⚠️ 現在は『テスト用データ』を使用しています。")
            time_dic = {
                "T2": pd.DataFrame([
                    ["", "記号", "10:00", "11:00", "12:00"],
                    ["", "A", "西村", "", ""],
                    ["", "B", "", "西村", ""]
                ])
            }

        # データ統合と表示
        integrated = p0.data_integration(pdf_dic, time_dic)

        for loc_key, data_list in integrated.items():
            if len(data_list) < 3:
                continue
            
            my_s = data_list[0]
            t_s = data_list[2]
            final_rows = []
            valid_symbols = t_s.iloc[:, 1].astype(str).apply(p0.normalize_text).tolist()
            
            for col in range(1, my_s.shape[1]):
                v1 = str(my_s.iloc[0, col]).strip()
                v2 = str(my_s.iloc[1, col]).strip()
                dt = f"{y}/{m}/{col}"
                if v1 == "" or "nan" in v1.lower(): continue
                norm_v1 = p0.normalize_text(v1)

                if norm_v1 in valid_symbols:
                    final_rows.append([v1, dt, "", dt, "", "True", "", loc_key])
                    match_idx_list = t_s[t_s.iloc[:, 1].apply(p0.normalize_text) == norm_v1].index.tolist()
                    if match_idx_list:
                        match_idx = match_idx_list[0]
                        for ts_col in range(2, t_s.shape[1]):
                            time_label = t_s.iloc[0, ts_col]
                            assigned_staff = str(t_s.iloc[match_idx, ts_col]).strip()
                            if p0.normalize_text(assigned_staff) == p0.normalize_text(target_staff):
                                final_rows.append([f"{v1}勤務", dt, time_label, dt, "", "False", "", loc_key])
                elif "本町" in v1:
                    final_rows.append(["本町", dt, "", dt, "", "True", "", loc_key])
                    st_t, en_t, ok = p0.parse_special_shift(v2)
                    if ok: final_rows.append(["本町", dt, st_t, dt, en_t, "False", "", loc_key])
                else:
                    final_rows.append([v1, dt, "", dt, "", "False", "", loc_key])

            if final_rows:
                st.subheader(f"📍 {loc_key} の抽出結果")
                df_res = pd.DataFrame(final_rows, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
                st.dataframe(df_res)
                csv = df_res.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(label=f"{loc_key}のCSVを保存", data=csv, file_name=f"shift_{loc_key}_{y}{m}.csv", mime="text/csv")

if __name__ == "__main__":
    main()
