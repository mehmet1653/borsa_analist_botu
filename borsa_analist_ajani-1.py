import os
import requests
import yfinance as yf
import ta
import json
import google.generativeai as genai
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading

# --- AYARLAR ---
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def msg(text):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

def ajani_calistir():
    # 1. Veri çekme (Çok hızlı, API'ye yük bindirmez)
    hisseler = ["THYAO.IS", "TUPRS.IS", "SASA.IS", "KCHOL.IS"]
    veri_ozeti = ""
    
    for s in hisseler:
        df = yf.download(s, period="1mo", progress=False)
        if not df.empty:
            fiyat = df['Close'].iloc[-1]
            rsi = ta.momentum.rsi(df['Close'], window=14).iloc[-1]
            veri_ozeti += f"{s}: Fiyat {fiyat:.2f}, RSI {rsi:.1f}\n"

    # 2. Tek bir API çağrısı
    try:
        cevap = model.generate_content(f"Aşağıdaki hisseler için kısa bir özet yap: {veri_ozeti}").text
        msg(f"📊 **ANALİZ:**\n\n{cevap}")
    except Exception as e:
        msg(f"Hata: {str(e)}")

# --- BASİT SERVER (Render'ın ölmemesi için) ---
def run():
    HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), SimpleHTTPRequestHandler).serve_forever()

threading.Thread(target=run, daemon=True).start()

# --- DİNLEYİCİ ---
last_id = 0
while True:
    try:
        res = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id + 1}").json()
        for u in res.get("result", []):
            last_id = u["update_id"]
            if "/analiz" in u.get("message", {}).get("text", ""):
                ajani_calistir()
    except: pass
        
