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

# HAFIZA (Kalıcı hale gelmesi için ileride Supabase'e bağlayacağız)
HAFIZA = {} 

TAKIP_LISTESI = ["THYAO.IS", "TUPRS.IS", "SASA.IS", "KCHOL.IS", "KRDMB.IS", "ASTOR.IS", "BTC-USD", "NVDA"]

def msg(text):
    try: 
        # Parçalı gönderim (4000 karakter sınırı aşılmasın diye)
        for i in range(0, len(text), 4000):
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": CHAT_ID, "text": text[i:i+4000], "parse_mode": "Markdown"}, timeout=15)
    except: pass

def analiz_hesapla(s):
    try:
        time.sleep(2) # Hata almamak için kritik süre
        df = yf.download(s, period="3mo", progress=False)
        close = df['Close']
        return {
            "fiyat": float(close.iloc[-1]),
            "rsi": float(ta.momentum.rsi(close, window=14).iloc[-1]),
            "macd": "AL" if ta.trend.macd_diff(close).iloc[-1] > 0 else "SAT",
            "ma50": float(close.rolling(window=50).mean().iloc[-1])
        }
    except: return {"fiyat": 0, "rsi": 0, "macd": "-", "ma50": 0}

def ajani_calistir():
    msg("🧠 Geçmiş performans ve güncel piyasa kıyaslanıyor...")
    guncel_veriler = {s: analiz_hesapla(s) for s in TAKIP_LISTESI}
    
    prompt = f"""
    Sen Mehmet'in borsa stratejistisin.
    
    1. GEÇMİŞ HAFIZA: {json.dumps(HAFIZA)}
    2. GÜNCEL VERİLER: {json.dumps(guncel_veriler)}
    
    GÖREV:
    - Geçmiş tahminin gerçekleşen fiyat ile tuttu mu? 
    - Hatandıysa nedenini kısa açıkla ve düzeltme yap.
    - Bu "öğrenme" sürecini kullanarak, yeni hafta için net bir strateji (OLUMLU/OLUMSUZ/TEMKİNLİ) belirle.
    
    FORMATI ASLA BOZMA:
    ---
    ### [SEMBOLE]
    * Fiyat: [GÜNCEL] | Trend: [AL/SAT]
    * GEÇMİŞ ANALİZİM: [Tuttu/Tutmadı - Hatanın Nedeni]
    * YENİ TAHMİNİM: [OLUMLU/OLUMSUZ/TEMKİNLİ]
    * Yorum: [Düzeltilmiş strateji]
    ---
    """
    
    try:
        rapor = model.generate_content(prompt).text
        msg(f"📊 **ÖĞRENEN ANALİZ RAPORU**\n\n{rapor}")
        HAFIZA.update(guncel_veriler) # Öğrenme döngüsü: Veriyi bir sonraki hafta için hafızaya al
    except: msg("⚠️ Analiz hatası.")

if __name__ == "__main__":
    # Render canlılık koruma
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
            
