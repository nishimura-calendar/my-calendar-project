import re

def get_pdf_info(pdf_file_path):
    """
    PDFから「日本語の曜日」のみを抽出し、その数をカウントする
    """
    tables = camelot.read_pdf(pdf_file_path, pages='1', flavor='stream')
    if not tables: 
        return 0, None
    
    # テーブルデータ全体を1つの文字列として結合
    all_text = "".join(tables[0].df.astype(str).values.flatten())
    
    # 「月・火・水・木・金・土・日」という文字のみを抽出（それ以外は無視）
    weekdays_found = re.findall(r'[日月火水木金土]', all_text)
    
    # 曜日が出現した数＝月末日とみなす
    count = len(weekdays_found)
    
    return count, tables[0].df
