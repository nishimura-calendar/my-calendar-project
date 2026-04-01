import streamlit as st
import practice_0 as p0
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_gcp_services():
    """Drive APIのみを使用して認証（スプレッドシートもDrive経由で変換・取得）"""
    try:
        creds_info = st.secrets["gcp_service_account"]
        credentials = service_account.Credentials.from_service_account_info(
            creds_info, 
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        # Drive API v3 を使用
        drive_service = build('drive', 'v3', credentials=credentials)
        return drive_service
    except Exception as e:
        st.error(f"GCP認証エラー: {e}")
        return None

def main():
    st.set_page_config(page_title="シフト・時程統合システム", layout="wide")
    st.title("📅 シフト・時程表 統合システム (Drive変換版)")

    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("検索する氏名", value="田坂 友愛")
    # スプレッドシートID または ExcelファイルID
    file_id = st.sidebar.text_input("ファイルID (時程表)", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")
    
    pdf_file = st.file_uploader("勤務表PDFを選択", type="pdf")

    if pdf_file and target_staff:
        if st.button("🚀 解析と紐付けを実行"):
            drive_service = get_gcp_services()
            if not drive_service: st.stop()
            
            with st.spinner("データを取得中..."):
                # Drive API経由でSSをExcel変換ダウンロード
                time_dic = p0.download_and_extract_schedule(drive_service, file_id)
                
                pdf_stream = io.BytesIO(pdf_file.read())
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                
                final_data = p0.data_integration(pdf_dic, time_dic)

                if final_data:
                    for loc_key, content in final_data.items():
                        st.success(f"📍 拠点: {loc_key}")
                        
                        my_shift = content["my_shift"]
                        areas = content["patrol_areas"]
                        details = my_shift.iloc[1].tolist()
                        
                        st.subheader("💡 シフト内容の解析")
                        cols = st.columns(len(details))
                        for i, val in enumerate(details):
                            val_str = str(val).strip()
                            clean_val = p0.normalize_for_match(val_str)
                            with cols[i]:
                                if not clean_val: st.write("-")
                                elif "本町" in val_str: st.info(f"**{val_str}**\n\n特殊(本町)")
                                elif clean_val in areas: st.success(f"**{val_str}**\n\n時程表一致")
                                else: st.warning(f"**{val_str}**\n\nデフォルト")

                        tab1, tab2, tab3 = st.tabs(["👤 個人シフト", "👥 同僚の動き", "⏱ 拠点時程表"])
                        with tab1: st.dataframe(my_shift, use_container_width=True)
                        with tab2: st.dataframe(content["others"], use_container_width=True)
                        with tab3: st.dataframe(content["schedule"], use_container_width=True)
                else:
                    st.error("紐付けに失敗しました。IDや権限を確認してください。")

if __name__ == "__main__":
    main()
