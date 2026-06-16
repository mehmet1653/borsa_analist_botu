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

# HAFIZA VE LİSTE
HAFIZA = {}
TAKIP_LISTESI = ["THYAO.IS", "TUPRS.IS", "SASA.IS", "KCHOL.IS", "KRDMB.IS", "ASTOR.IS", "BTC-USD", "NVDA"]

def msg(text):
    try: 
        for i in range(0, len(text), 4000):
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": CHAT_ID, "text": text[i:i+4000], "parse_mode": "Markdown"}, timeout=15)
    except: pass

def analiz_hesapla(s):
    try:
        time.sleep(2)
        df = yf.download(s, period="3mo", progress=False)
        if df.empty: return None
        close = df['Close']
        return {"fiyat": float(close.iloc[-1]), "rsi": float(ta.momentum.rsi(close, window=14).iloc[-1]),
                "macd": "AL" if ta.trend.macd_diff(close).iloc[-1] > 0 else "SAT",
                "ma50": float(close.rolling(window=50).mean().iloc[-1])}
    except: return None

def ajani_calistir():
    msg("🧠 Analiz motoru çalışıyor...")
    guncel_veriler = {s: analiz_hesapla(s) for s in TAKIP_LISTESI if analiz_hesapla(s)}
    
    # FORMATI TAM İSTEDİĞİN GİBİ SABİTLEDİM
    prompt = f"""
    Sen Mehmet'in profesyonel borsa uzmanısın. 
    GEÇMİŞ VERİLER: {json.dumps(HAFIZA)}. 
    GÜNCEL VERİLER: {json.dumps(guncel_veriler)}.
    
    GÖREVİN: Geçmiş tahminlerinle güncel fiyatları kıyasla, hatalarını not et ve yeni stratejini oluştur.
    
    ASLA ŞAŞMAYACAĞIN FORMAT:
    ---
    ### [SEMBOLE]
    * Fiyat: [GÜNCEL FİYAT] | RSI: [RSI] | MACD: [AL/SAT]
    * MA50: [MA50]
    * GEÇMİŞ KIYAS: [Tuttu/Tutmadı - Hatanın Nedeni]
    * TREND: [OLUMLU/OLUMSUZ/TEMKİNLİ]
    * Yorum: [Kısa ve net teknik yorum]
    * 📌 1 HAFTALIK ÖNGÖRÜ: [Tahmin]
    ---
    """
    
    try:
        rapor = model.generate_content(prompt).text
        msg(f"📊 **STRATEJİK ANALİZ RAPORU**\n\n{rapor}")
        HAFIZA.update(guncel_veriler)
    except Exception as e: msg(f"⚠️ Analiz hatası: {str(e)[:50]}")

def komut_isleyici(text):
    global TAKIP_LISTESI
    if text.startswith("/ekle"):
        s = text.split(" ")[1].upper()
        if s not in TAKIP_LISTESI: TAKIP_LISTESI.append(s)
        msg(f"✅ {s} listeye eklendi.")
    elif text.startswith("/cikar"):
        s = text.split(" ")[1].upper()
        if s in TAKIP_LISTESI: TAKIP_LISTESI.remove(s)
        msg(f"❌ {s} listeden çıkarıldı.")
    elif text == "/portfoy":
        msg(f"📋 **PORTFÖYÜN:** " + ", ".join(TAKIP_LISTESI))
    elif text == "/analiz":
        ajani_calistir()

if __name__ == "__main__":
    threading.Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), SimpleHTTPRequestHandler).serve_forever(), daemon=True).start()
    last_id = 0
    while True:
        try:
            res = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id + 1}&timeout=30").json()
            for u in res.get("result", []):
                last_id = u["update_id"]
                if "message" in u: komut_isleyici(u["message"].get("text", ""))
        except: time.sleep(5)
