import streamlit as st
import pandas as pd
import camelot
import practice_0 as p0
import os

st.title("📅 21時テスト用：シフト解析画面")

# 1. ユーザー入力
uploaded_file = st.file_uploader("PDFファイルをアップロードしてください", type="pdf")
target_staff = st.text_input("検索する氏名を入力してください", value="四村 和義")

# --- 事前準備: 時程表の辞書化（本来はGoogle Driveから取得） ---
# テスト用に、空の辞書またはダミーデータを用意
if "time_dic" not in st.session_state:
    # ここに時程表を読み込む処理が入ります。
    # 現在はテスト用に空の辞書を作成。本来は p0.time_schedule_from_drive() 等で取得。
    st.session_state.time_dic = {"t1": pd.DataFrame(), "t2": pd.DataFrame()} 

time_dic = st.session_state.time_dic

# 2. 解析実行ボタン
if uploaded_file and st.button("21時の最終解析実行"):
    
    # PDFを一時保存してCamelotで読み込む
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    try:
        # flavor='lattice' で解析。
        # ここで「名前の幅」に合わせる設定が必要な場合は、table_areas等の指定を追加します。
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        
        if not tables:
            st.error("PDFから表を検出できませんでした。")
            st.stop()
            
        df = tables[0].df
        
        # practice_0.py の解析関数を呼び出し
        loc_key, my_df, other_df = p0.pdf_reader(uploaded_file.name, df, target_staff)
        
        # 3. 辞書キーによる紐付け確認
        if loc_key in time_dic:
            st.success(f"✅ 勤務地 '{loc_key.upper()}' の紐付けに成功しました")
            
            # 三表の一括表示
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("🟢 my_daily_shift")
                st.dataframe(my_df)
            with col2:
                st.subheader("👥 other_daily_shift")
                st.dataframe(other_df)
                
            st.subheader(f"🕒 time_schedule ({loc_key.upper()})")
            st.dataframe(time_dic[loc_key])
        else:
            st.error(f"⚠️ 紐付け失敗: PDFから見つかった '{loc_key}' は時程表にありません。")
            st.info(f"現在の時程表リスト: {list(time_dic.keys())}")
            
    except Exception as e:
        st.error(f"解析中にエラーが発生しました: {e}")
    finally:
        if os.path.exists("temp.pdf"):
            os.remove("temp.pdf")
