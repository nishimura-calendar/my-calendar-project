import streamlit as st
import pandas as pd
import practice_0 as p0

# ==========================================
# 1. 定数・基本設定（NameError防止のため最初に定義）
# ==========================================
SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(
    page_title="シフト・時程 統合管理システム",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📅 シフト・時程 統合管理システム")
st.caption("PDF座標指定 [0,0],[0,1],[1,1] および A列Key照合ロジック実装済み")

# ==========================================
# 2. サービス認証とデータ読み込み
# ==========================================
# practice_0.py 内の get_unified_services を呼び出し
drive_service, sheets_service = p0.get_unified_services()

if sheets_service:
    try:
        # 【重要】A列をKey（勤務地）として行列範囲を辞書登録するロジックを実行
        with st.spinner("スプレッドシートから時程マスターを読み込み中..."):
            time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
        
        st.sidebar.success(f"✅ 時程表マスター読込完了 ({len(time_dic)}拠点のKeyを取得)")

        # 読み込まれたKey（勤務地）の確認用（デバッグ用）
        with st.sidebar.expander("登録済みKey一覧"):
            st.write(list(time_dic.keys()))

        # ==========================================
        # 3. ユーザー入力エリア（サイドバー）
        # ==========================================
        st.sidebar.header("解析パラメータ")
        target_staff = st.sidebar.text_input("解析対象者名", value="西村 文宏")
        uploaded_pdf = st.sidebar.file_uploader("勤務表PDFをアップロード", type="pdf")

        # ==========================================
        # 4. メイン解析ロジック（基本事項の7）
        # ==========================================
        if st.sidebar.button("解析・照合実行", type="primary"):
            if uploaded_pdf and target_staff:
                # PDFの座標からKeyを抽出し、time_dicのKeyと照合して「通過資格」を判定
                results = p0.pdf_reader_with_logic_7(uploaded_pdf, target_staff, time_dic)
                
                if results:
                    st.success(f"🔍 {len(results)}件の該当データが見つかりました")
                    
                    for res in results:
                        st.divider()
                        # 第3関門を通過したKey（勤務地）を表示
                        st.header(f"📍 勤務地Key: {res['key']}")
                        
                        # 座標 [0,0], [0,1], [1,1] から取得した情報の表示
                        with st.expander("PDF指定座標からの取得値詳細"):
                            col_a, col_b, col_c = st.columns(3)
                            col_a.metric("座標 [0,0]", res['coords'].get("[0,0]"))
                            col_b.metric("座標 [0,1]", res['coords'].get("[0,1]"))
                            col_c.metric("座標 [1,1]", res['coords'].get("[1,1]"))
                        
                        # 結果の表示
                        tab1, tab2 = st.tabs(["📄 自分のシフト (PDF抽出)", "🕒 適用された時程表 (行列範囲)"])
                        
                        with tab1:
                            st.subheader("個人シフト抽出結果")
                            st.dataframe(res['my_data'], use_container_width=True)
                            
                        with tab2:
                            st.subheader(f"勤務地「{res['key']}」のマスターデータ")
                            st.info("A列をKeyとして、D列以降の時間軸（数字〜文字列）を抽出した範囲です。")
                            st.dataframe(res['time_range'], use_container_width=True)
                else:
                    st.error("⚠️ 通過資格なし: PDFから抽出したKeyが時程表マスターのKey(A列)と一致しませんでした。")
            else:
                st.warning("解析対象者名とPDFファイルの両方を準備してください。")

    except Exception as e:
        st.error(f"❌ アプリケーション実行エラー: {e}")
        st.info("practice_0.py の関数名や引数が app.py と一致しているか確認してください。")
else:
    st.error("❌ Google APIサービスを起動できませんでした。secrets.tomlの設定を確認してください。")
