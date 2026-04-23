import streamlit as st
import practice_0 as p0
import camelot
import os

# 解析するスプレッドシートID
SPREADSHEET_ID = '1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE'

st.set_page_config(layout="wide")
st.title("📅 シフト・時程表 統合システム")

uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
target_staff = st.text_input("検索する氏名", value="四村 和義")

# 時程表マスターの読み込み
if 'time_dic' not in st.session_state:
    try:
        service = p0.get_gdrive_service(st.secrets)
        st.session_state.time_dic = p0.time_schedule_from_drive(service, SPREADSHEET_ID)
        st.sidebar.success("✅ 時程表マスター同期完了")
    except Exception as e:
        st.sidebar.error(f"⚠️ Drive接続エラー: {e}")

if uploaded_file and st.button("解析実行"):
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # --- 動的な列幅決定（3者比較：名前、勤務地、最低保証120） ---
    # 日本語1文字あたり約15pt + 左右マージン
    name_width = len(target_staff) * 15 + 20
    location_width = 10 * 15 + 20  # 勤務地（目安10文字）
    safe_limit = 120              # 安定列幅（最低保証：これより狭いと日付列を破壊する）
    
    column_boundary = max(name_width, location_width, safe_limit)
    
    try:
        # 【重要】columnsオプションを使用するため flavor='stream' を指定
        tables = camelot.read_pdf(
            "temp.pdf", 
            pages='1', 
            flavor='stream', 
            columns=[str(column_boundary)]
        )
        
        # 万が一 stream で全く表が取れなかった場合のフォールバック（予備）
        if not tables or len(tables[0].df) <= 1:
            tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
            
        if not tables:
            st.error("表を検出できませんでした。")
        else:
            # practice_0.py の解析エンジンを呼び出し
            loc_key, my_df, other_df = p0.pdf_reader(uploaded_file.name, tables[0].df, target_staff)
            
            st.divider()
            st.success(f"📍 判定された拠点: {loc_key}")
            
            # 画面を左右に分割して表示
            c1, c2 = st.columns([1, 1])
            
            with c1:
                st.subheader("🟢 あなたのシフト")
                if my_df is not None:
                    st.dataframe(my_df, hide_index=True)
                else:
                    st.warning(f"{target_staff} さんのデータが見つかりませんでした。")
                
                st.subheader("👥 同拠点の他スタッフ")
                if other_df is not None:
                    st.dataframe(other_df, hide_index=True)

            with c2:
                # 勤務地名による時程表の自動マッチング
                time_dic = st.session_state.get('time_dic', {})
                match_key = next((k for k in time_dic.keys() if p0.normalize_text(loc_key) in p0.normalize_text(k)), None)
                
                if match_key:
                    st.subheader(f"🕒 時程表マスター ({match_key})")
                    # practice_0 側で時刻変換(6.25 -> 6:15等)済みの表を表示
                    st.dataframe(time_dic[match_key], hide_index=True)
                else:
                    st.warning(f"⚠️ 拠点 '{loc_key}' に合致する時程表が見つかりません。")

    except Exception as e:
        st.error(f"解析中にエラーが発生しました: {e}")
    finally:
        if os.path.exists("temp.pdf"):
            os.remove("temp.pdf")
