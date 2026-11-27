import streamlit as st
import pandas as pd
import io
import pdfplumber
import re
import calendar
import unicodedata
import fitz  # PyMuPDF
import datetime
import time
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.auth.transport.requests import Request

# --- PDFを画面に画像として表示する補助関数 ---
def display_pdf_as_images(file_bytes):
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            st.image(img_bytes, caption=f"PDF プレビュー (ページ {page_num + 1})", use_container_width=True)
    except Exception as e:
        st.error(f"PDFのプレビュー表示に失敗しました: {e}")

# --- 0行目の最後の文字と下段(1行目)の文字を抽出する補助関数 ---
def extract_last_char_row1_and_above(df):
    if df is None or df.empty or df.shape[0] < 2:
        return None, None

    def clean_cell(val):
        if val is None:
            return ""
        s = unicodedata.normalize("NFKC", str(val)).strip()
        if not s or s.lower() == "nan" or s == "None":
            return ""
        return s

    last_col = None
    last_val_row0 = ""
    for col in range(df.shape[1] - 1, -1, -1):
        val0 = clean_cell(df.iloc[0, col])
        if val0:
            last_col = col
            last_val_row0 = val0
            break

    if last_col is None:
        return None, None

    last_char_row0 = last_val_row0[-1]
    val1 = clean_cell(df.iloc[1, last_col])
    last_char_row1 = val1[-1] if val1 else None

    return last_char_row0, last_char_row1

# --- Google Driveから過去30日のPDFをリスト化する補助関数 ---
def get_recent_pdfs
