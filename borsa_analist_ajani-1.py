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
# Model'i daha stabil bir hale getirdik
model = genai.GenerativeModel('gemini-2.0-flash')

TAKIP_LISTESI = ["THYAO.IS", "TUPRS.IS", "SASA.IS", "KCHOL.IS", "KRDMB.IS", "ASTOR.IS", "BTC-USD", "NVDA"]
HAFIZA = {} 

def msg(text):
    try: 
        # Mesajı parça parça gönder (Limit aşımını engeller)
        for i in range(0, len(text), 4000):
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": CHAT_ID, "text": text[i:i+4000], "parse_mode": "Markdown"}, timeout=15)
    except: pass

def analiz_hesapla(s):
    try:
        # Yahoo üzerindeki yükü azaltmak için süreyi artırdık
        time.sleep(3) 
        df = yf.download(s, period="1mo", progress=False) # Veri aralığını kısalttık (daha hızlı)
        if df.empty: return None
        close = df['Close']
        return {"fiyat": float(close.iloc[-1]), "rsi": float(ta.momentum.rsi(close, window=14).iloc[-1]),
                "macd": "AL" if ta.trend.macd_diff(close).iloc[-1] > 0 else "SAT",
                "ma50": float(close.rolling(window=50).mean().iloc[-1])}
    except: return None

def ajani_calistir():
    msg("⌛ Sistem soğuma süresinden çıkıyor, veriler toplanıyor...")
    guncel_veriler = {}
    for s in TAKIP_LISTESI:
        res = analiz_hesapla(s)
        if res: guncel_veriler[s] = res
    
    prompt = f"Sen Mehmet'in stratejistisin. GEÇMİŞ: {json.dumps(HAFIZA)}. GÜNCEL: {json.dumps(guncel_veriler)}. Tüm hisseler için 1 haftalık öngörü içeren net bir rapor hazırla. Format: SEMBOL | Fiyat | RSI | MACD | 📌 ÖNGÖRÜ."
    
    try:
        rapor = model.generate_content(prompt).text
        msg(f"📊 **ÖĞRENEN ANALİZ:**\n\n{rapor}")
        HAFIZA.update(guncel_veriler)
    except Exception as e:
        msg(f"⚠️ Limit aşıldı, lütfen 1-2 dakika bekle ve tekrar /analiz yaz.")

if __name__ == "__main__":
    threading.Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), SimpleHTTPRequestHandler).serve_forever(), daemon=True).start()
    last_id = 0
    while True:
        try:
            res = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id + 1}&timeout=30").json()
            for u in res.get("result", []):
                last_id = u["update_id"]
                if "message" in u and u["message"].get("text") == "/analiz":
                    ajani_calistir()
        except: time.sleep(10) # Döngü beklemesini artırdık (Sistemi yormamak için)
