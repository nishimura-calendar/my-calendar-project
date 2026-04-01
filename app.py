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
    st.set_page_config(page_title="Shift Integration System", layout="wide")
    st.title("📅 シフト・時程表 統合システム")

    st.sidebar.header("ユーザー設定")
    target_staff = st.sidebar.text_input("検索氏名", value="田坂 友愛")
    target_date = st.sidebar.date_input("対象日")
    file_id = st.sidebar.text_input("時程表ファイルID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")
    
    uploaded_pdf = st.file_uploader("勤務表PDFをアップロード", type="pdf")

    if uploaded_pdf and target_staff:
        if st.button("🚀 解析開始"):
            drive_service = get_gcp_services()
            if not drive_service: st.stop()
            
            with st.spinner("時程表を取得し、範囲を特定しています..."):
                time_dic = p0.download_and_extract_schedule(drive_service, file_id)
                pdf_stream = io.BytesIO(uploaded_pdf.read())
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                final_results = p0.data_integration(pdf_dic, time_dic)

                if final_results:
                    for loc, data in final_results.items():
                        st.success(f"📍 勤務地: {loc}")
                        
                        my_shift_df = data["my_shift"]
                        areas_norm = data["areas"]
                        shift_details = my_shift_df.iloc[1].tolist()

                        st.subheader("📋 カレンダー登録判定")
                        for val in shift_details:
                            val_str = str(val).strip()
                            if not val_str: continue
                            norm_val = p0.normalize_for_match(val_str)
                            
                            if "本町" in val_str:
                                st.code(f"特殊(本町): ('{val_str}', {target_date}, '開始', {target_date}, '終了', False, '', '')")
                            elif norm_val in areas_norm:
                                st.code(f"区域一致: ('{loc}+{val_str}', {target_date}, '', {target_date}, '', True, '', '{loc}')")
                            else:
                                st.code(f"デフォルト: ('{val_str}', {target_date}, '', {target_date}, '', True, '', '')")
                        
                        st.info(f"Day End: ('打ち合わせ通り', {target_date}, '打ち合わせ通り', {target_date}, '打ち合わせ通り', False, '', '')")

                        t1, t2, t3 = st.tabs(["個人シフト", "同僚", "時程表(解析済み範囲)"])
                        with t1: st.dataframe(my_shift_df)
                        with t2: st.dataframe(data["others"])
                        with t3: 
                            st.caption("※「出勤」列以降をカットし、1行目の時間軸を整形済み。")
                            st.dataframe(data["schedule"])
                else:
                    st.error("紐付け可能な拠点が見つかりませんでした。")

if __name__ == "__main__":
    main()
