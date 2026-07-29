import streamlit as st
import pandas as pd
import pdfplumber

st.title("免税店シフト表・自動解析アプリ")

# 1. ファイルアップロード
uploaded_pdf = st.file_uploader("シフト表PDFをアップロードしてください", type="pdf")

def get_clean_names(df):
    """0列目から名前を抽出し、不要な文字を除去してリスト化する"""
    # 0列目のデータを取得（欠損値を除去して文字列化）
    raw_names = df.iloc[:, 0].dropna().astype(str).tolist()
    clean_names = []
    
    for item in raw_names:
        # T1, T2などのキーが含まれる行は無視
        if "T1" in item or "T2" in item:
            continue
        # 改行コードがある場合はその前までを取得
        name = item.split('\n')[0].strip()
        # 2文字以上で、リストに未登録のものだけ追加
        if len(name) >= 2 and name not in clean_names:
            clean_names.append(name)
    return clean_names

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        page = pdf.pages[0]
        table = page.extract_table()
        
        if table:
            df_pdf = pd.DataFrame(table)
            
            # 2. 人名リストの作成
            clean_names = get_clean_names(df_pdf)
            
            if clean_names:
                # 3. 選択メニューの表示
                selected_name = st.selectbox("シフトを確認する人を選択してください", clean_names)
                st.write(f"### 選択された人: **{selected_name}** さんの行データ")
                
                # 4. 選択した人の行データを抽出
                # (0列目に名前が含まれている行を検索)
                row_data = df_pdf[df_pdf.iloc[:, 0].astype(str).str.contains(selected_name, na=False)]
                
                if not row_data.empty:
                    st.dataframe(row_data)
                    
                    # 補足：ここから先は個別のシフト情報の処理に使えます
                    st.info("この行データを解析して、個別のシフトをカレンダーに追加する準備が整いました。")
                else:
                    st.error("データの抽出に失敗しました。")
            else:
                st.warning("人名が抽出できませんでした。")
        else:
            st.error("PDFから表データを読み込めませんでした。")
