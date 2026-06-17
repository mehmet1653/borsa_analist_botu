import os
import time
import requests
import yfinance as yf
import ta
import threading
import json
import google.generativeai as genai
from http.server import SimpleHTTPRequestHandler, HTTPServer

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')

TAKIP_LISTESI = ["THYAO.IS", "TUPRS.IS", "SASA.IS", "KCHOL.IS", "KRDMB.IS", "ASTOR.IS", "BTC-USD", "NVDA"]
HAFIZA = {} 

def msg(text):
    try: 
        # Uzun mesajları parçala
        for i in range(0, len(text), 4000):
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": CHAT_ID, "text": text[i:i+4000], "parse_mode": "Markdown"}, timeout=15)
    except: pass

def ajani_calistir():
    msg("⌛ Veriler toplu olarak işleniyor...")
    
    # 1. TÜM VERİLERİ YERELDE TOPLA (API'yi meşgul etmeden)
    toplu_veri = {}
    for s in TAKIP_LISTESI:
        try:
            df = yf.download(s, period="1mo", progress=False)
            if not df.empty:
                close = df['Close']
                toplu_veri[s] = {
                    "fiyat": float(close.iloc[-1]),
                    "rsi": float(ta.momentum.rsi(close, window=14).iloc[-1]),
                    "macd": "AL" if ta.trend.macd_diff(close).iloc[-1] > 0 else "SAT"
                }
        except: continue

    # 2. TEK BİR İSTEK GÖNDER (Limit sorununu çözer)
    prompt = f"""
    Sen Mehmet'in borsa uzmanısın. 
    GEÇMİŞ: {json.dumps(HAFIZA)} 
    GÜNCEL: {json.dumps(toplu_veri)}
    
    Tüm hisseleri tek seferde analiz et. 
    Format: 
    ### [SEMBOL]
    * Fiyat: [FİYAT] | RSI: [RSI] | MACD: [AL/SAT]
    * GEÇMİŞ ANALİZİM: [Tuttu/Tutmadı - Nedeni]
    * YENİ TAHMİNİM: [OLUMLU/OLUMSUZ/TEMKİNLİ]
    * 📌 1 HAFTALIK ÖNGÖRÜ: [Tahmin]
    """
    
    try:
        rapor = model.generate_content(prompt).text
        msg(f"📊 **ANALİZ RAPORU**\n\n{rapor}")
        HAFIZA.update(toplu_veri)
    except Exception as e:
        msg(f"⚠️ Hata: Sistem hala yoğun, 5 dk sonra dene.")

# ... (Komut işleyici ve server kısmı aynı)
