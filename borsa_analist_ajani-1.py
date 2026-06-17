import os
import time
import json
import requests
import yfinance as yf
import ta
import threading
import pandas as pd
import google.generativeai as genai
from http.server import SimpleHTTPRequestHandler, HTTPServer
from datetime import datetime

# --- AYARLAR ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')

# HAFIZA (Sadece analiz sonuçlarını tutar)
HAFIZA = {"gecmis_analiz": {}}
TAKIP_LISTESI = ["THYAO.IS", "TUPRS.IS", "SASA.IS", "KCHOL.IS", "KRDMB.IS", "ASTOR.IS", "BTC-USD", "NVDA"]

def msg(text):
    try: 
        for i in range(0, len(text), 4000):
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": CHAT_ID, "text": text[i:i+4000], "parse_mode": "Markdown"}, timeout=15)
    except: pass

def verileri_hazirla():
    """Hisseleri tek tek değil, toplu paketler halinde hazırlar (Hız için)"""
    paket = {}
    for s in TAKIP_LISTESI:
        try:
            df = yf.download(s, period="1mo", progress=False)
            if not df.empty:
                close = df['Close']
                paket[s] = {
                    "fiyat": float(close.iloc[-1]),
                    "rsi": float(ta.momentum.rsi(close, window=14).iloc[-1]),
                    "macd": "AL" if ta.trend.macd_diff(close).iloc[-1] > 0 else "SAT"
                }
        except: continue
    return paket

def ajani_calistir():
    msg("🧠 Analiz başlıyor...")
    guncel_veriler = verileri_hazirla()
    
    # KESİNLİKLE HATA ALMAYACAK BASİT VE NET PROMPT
    prompt = f"Sen Mehmet'in borsa stratejistisin. Şu verileri kullanarak 1 haftalık öngörü oluştur: {json.dumps(guncel_veriler)}. Her hisse için sadece şunu yaz: Sembol - Fiyat - Öngörü (OLUMLU/OLUMSUZ/TEMKİNLİ) ve nedenini kısaca yaz."
    
    try:
        rapor = model.generate_content(prompt).text
        msg(f"📊 **HIZLI ANALİZ:**\n\n{rapor}")
    except Exception as e:
        msg("⚠️ Analiz şu an çok yoğun, lütfen 1 dakika sonra tekrar /analiz yaz.")


# SERVER DÖNGÜSÜ
if __name__ == "__main__":
    threading.Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), SimpleHTTPRequestHandler).serve_forever(), daemon=True).start()
    
    last_id = 0
    while True:
        try:
            res = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id + 1}&timeout=30").json()
            for u in res.get("result", []):
                last_id = u["update_id"]
                if u.get("message", {}).get("text") == "/analiz":
                    ajani_calistir()
        except: time.sleep(10)
            
