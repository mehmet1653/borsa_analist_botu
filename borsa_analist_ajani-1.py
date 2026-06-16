import os
import time
import json
import requests
import yfinance as yf
import ta
import threading
import google.generativeai as genai
from http.server import SimpleHTTPRequestHandler, HTTPServer

# AYARLAR
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')

TAKIP_LISTESI = ["THYAO.IS", "TUPRS.IS", "SASA.IS", "KCHOL.IS", "KRDMB.IS", "ASTOR.IS", "BTC-USD", "NVDA"]

def msg(text):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def analiz_hesapla(sembol):
    try:
        df = yf.download(sembol, period="3mo", progress=False)
        if df.empty: return {"fiyat": "-", "rsi": "-", "macd": "-", "ma50": "-"}
        close = df['Close']
        return {
            "fiyat": f"{close.iloc[-1]:.2f}",
            "rsi": f"{ta.momentum.rsi(close, window=14).iloc[-1]:.2f}",
            "macd": "AL" if ta.trend.macd_diff(close).iloc[-1] > 0 else "SAT",
            "ma50": f"{close.rolling(window=50).mean().iloc[-1]:.2f}"
        }
    except:
        return {"fiyat": "-", "rsi": "-", "macd": "-", "ma50": "-"}

def ajani_calistir():
    msg("🔄 Veriler analiz ediliyor...")
    rapor_data = [{"sembol": s, **analiz_hesapla(s)} for s in TAKIP_LISTESI]
    
    prompt = f"""
    Sen bir borsa analiz uzmanısın. Şu verileri kullanarak rapor yaz: {json.dumps(rapor_data)}
    
    FORMATI ASLA BOZMA, AYNEN ŞUNU KULLAN:
    ---
    ### [SEMBOLE]
    * Fiyat: [FİYAT] | RSI: [RSI] | MACD: [MACD]
    * MA50: [MA50]
    * TREND: [OLUMLU/OLUMSUZ/TEMKİNLİ]
    * Yorum: [Kısa teknik analiz yorumu]
    * 📌 1 HAFTALIK ÖNGÖRÜ: [Tahmin]
    ---
    
    Profesyonel, net, finansal bir dil kullan. Mehmet'e hitap et.
    """
    
    try:
        rapor = model.generate_content(prompt).text
        msg(f"📊 **AKILLI PORTFÖY RAPORU**\n\n{rapor}")
    except Exception as e:
        msg(f"⚠️ Analiz hatası: {str(e)}")

if __name__ == "__main__":
    # Server başlat
    threading.Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), SimpleHTTPRequestHandler).serve_forever(), daemon=True).start()
    
    last_id = 0
    while True:
        try:
            res = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id + 1}&timeout=30").json()
            for u in res.get("result", []):
                last_id = u["update_id"]
                if u.get("message", {}).get("text") == "/analiz":
                    ajani_calistir()
        except: time.sleep(5)
            
