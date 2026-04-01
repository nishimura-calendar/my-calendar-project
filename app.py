import streamlit as st
import practice_0 as p0
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_gcp_services():
    try:
        creds_info = st.secrets["gcp_service_account"]
        credentials = service_account.Credentials.from_service_account_info(
            creds_info, 
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=credentials)
    except Exception as e:
        st.error(f"GCP認証エラー: {e}")
        return None

def main():
    st.set_page_config(page_title="シフト・時程統合システム", layout="wide")
    st.title("📅 シフト・時程表 統合システム")

    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("検索する氏名", value="田坂 友愛")
    target_date = st.sidebar.date_input("対象日付")
    file_id = st.sidebar.text_input("時程表SS ID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")
    
    pdf_file = st.file_uploader("勤務表PDFを選択", type="pdf")

    if pdf_file and target_staff:
        if st.button("🚀 解析と紐付けを実行"):
            drive_service = get_gcp_services()
            if not drive_service: st.stop()
            
            with st.spinner("データを取得中..."):
                time_dic = p0.download_and_extract_schedule(drive_service, file_id)
                pdf_stream = io.BytesIO(pdf_file.read())
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                final_data = p0.data_integration(pdf_dic, time_dic)

                if final_data:
                    for loc_key, content in final_data.items():
                        st.success(f"📍 拠点: {loc_key}")
                        
                        my_shift = content["my_shift"]
                        areas_norm = content["areas_info"]["norm"]
                        details = my_shift.iloc[1].tolist()
                        
                        st.subheader("💡 基本事項に基づく判定結果")
                        
                        results = []
                        # 詳細行（2行目）をループ
                        for val in details:
                            val_str = str(val).strip()
                            if not val_str: continue
                            
                            clean_val = p0.normalize_for_match(val_str)
                            
                            # 1. 本町判定
                            if "本町" in val_str:
                                # ロジック: (本町, target_date, 開始, target_date, 終了, False, "", "")
                                results.append({
                                    "type": "本町",
                                    "data": (val_str, target_date, "開始時間", target_date, "終了時間", False, "", "")
                                })
                            
                            # 2. 時程表B列(巡回区域)一致判定
                            elif clean_val in areas_norm:
                                # ロジック: (key+値, target_date, "", target_date, "", True, "", key)
                                results.append({
                                    "type": "一致",
                                    "data": (f"{loc_key}+{val_str}", target_date, "", target_date, "", True, "", loc_key)
                                })
                            
                            # 3. 不一致(デフォルト)
                            else:
                                # ロジック: (値, target_date, "", target_date, "", True, "", "")
                                results.append({
                                    "type": "デフォルト",
                                    "data": (val_str, target_date, "", target_date, "", True, "", "")
                                })
                        
                        # 判定結果の表示
                        for res in results:
                            st.code(f"{res['type']}: {res['data']}")

                        # その日の処理終了時(打ち合わせ通り)のダミー表示
                        st.info(f"Day End: ('打ち合わせ通り', {target_date}, '打ち合わせ通り', {target_date}, '打ち合わせ通り', False, '', '')")

                        tab1, tab2, tab3 = st.tabs(["👤 個人シフト", "👥 同僚の動き", "⏱ 拠点時程表"])
                        with tab1: st.dataframe(my_shift, use_container_width=True)
                        with tab2: st.dataframe(content["others"], use_container_width=True)
                        with tab3: st.dataframe(content["schedule"], use_container_width=True)
                else:
                    st.error("紐付けに失敗しました。")

if __name__ == "__main__":
    main()
