import streamlit as st
import practice_0 as p0
import camelot
import os

SPREADSHEET_ID = '1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE'

st.set_page_config(layout="wide")
st.title("📅 シフト・時程表 統合システム")

uploaded_file = st.file_uploader("PDFをアップロード", type="pdf")
target_staff = st.text_input("検索氏名", value="四村 和義")

if 'time_dic' not in st.session_state:
    try:
        service = p0.get_gdrive_service(st.secrets)
        st.session_state.time_dic = p0.time_schedule_from_drive(service, SPREADSHEET_ID)
        st.sidebar.success("✅ マスター同期完了")
    except Exception as e:
        st.sidebar.error(f"⚠️ Drive接続エラー: {e}")

if uploaded_file and st.button("解析実行"):
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # --- 3者比較による動的な列幅決定 ---
    name_width = len(target_staff) * 15 + 20      # 名前の幅
    location_width = 10 * 15 + 20               # 勤務地の幅(目安10文字)
    safe_limit = 120                            # 安定列幅(最低保証)
    
    column_boundary = max(name_width, location_width, safe_limit)
    
try:
        # columnsを使用する場合は flavor='stream' を指定します
        tables = camelot.read_pdf(
            "temp.pdf", 
            pages='1', 
            flavor='stream',  # 'lattice' から 'stream' に変更
            columns=[str(column_boundary)]
        )
        
        if not tables or len(tables[0].df) <= 1:
            # もし stream でうまく取れない場合は、予備として lattice を試す（ただしcolumnsは外す）
            tables = camelot.read_pdf(
                "temp.pdf", 
                pages='1', 
                flavor='lattice'
            )        if not tables:
            st.error("表を検出できませんでした。")
        else:
            loc_key, my_df, other_df = p0.pdf_reader(uploaded_file.name, tables[0].df, target_staff)
            
            st.success(f"📍 拠点: {loc_key}")
            c1, c2 = st.columns([1, 1])
            with c1:
                st.subheader("🟢 個人シフト")
                st.dataframe(my_df, hide_index=True)
                st.subheader("👥 同拠点の他スタッフ")
                st.dataframe(other_df, hide_index=True)
            with c2:
                time_dic = st.session_state.get('time_dic', {})
                match = next((k for k in time_dic.keys() if p0.normalize_text(loc_key) in p0.normalize_text(k)), None)
                if match:
                    st.subheader(f"🕒 時程表マスター ({match})")
                    st.dataframe(time_dic[match], hide_index=True)
    finally:
        if os.path.exists("temp.pdf"):
            os.remove("temp.pdf")
