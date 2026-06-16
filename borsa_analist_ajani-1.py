import os
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading
import time
import json
import requests
import yfinance as yf
import pandas as pd
import ta
import google.generativeai as genai

# ==========================================
# 🧠 KURUMSAL HAFIZA VE PORTFÖY ŞABLONU
# ==========================================
PORTFOY_YEDEK = {"SASA.IS": {"lot": 19, "maliyet": 3.65}}
TAKIP_YEDEK = ["THYAO.IS", "TUPRS.IS", "SASA.IS", "KCHOL.IS"]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

try:
    genai.configure(api_key=str(GEMINI_API_KEY).strip())
    model = genai.GenerativeModel('gemini-2.5-flash')
except:
    model = None

# Eğer bulut tamamen boşsa ilk kez oluşturulacak şablon veri yapısı
HAFIZA = {
    "takip_listesi": TAKIP_YEDEK,
    "portfoy": PORTFOY_YEDEK,
    "temel_veriler": {
        "THYAO.IS": {"fk": "3.10", "pddd": "0.85"},
        "TUPRS.IS": {"fk": "5.20", "pddd": "1.90"},
        "SASA.IS": {"fk": "22.40", "pddd": "4.10"},
        "KCHOL.IS": {"fk": "4.80", "pddd": "1.30"}
    },
    "last_update_id": 0
}

# ==========================================
# ☁️ SUPABASE BULUT HAFIZA MOTORU
# ==========================================
def bulut_hafiza_yukle():
    global HAFIZA
    if not SUPABASE_URL or not SUPABASE_KEY: return
    url = f"{SUPABASE_URL}/storage/v1/object/ajan_hafizasi/hafiza.json"
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200: 
            yuklenen = res.json()
            for anahtar in ["takip_listesi", "portfoy", "temel_veriler", "last_update_id"]:
                if anahtar in yuklenen: HAFIZA[anahtar] = yuklenen[anahtar]
            print("✅ Bulut hafızası başarıyla eşitlendi.")
    except: pass

def bulut_hafiza_kaydet():
    if not SUPABASE_URL or not SUPABASE_KEY: return
    url = f"{SUPABASE_URL}/storage/v1/object/ajan_hafizasi/hafiza.json"
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY, "Content-Type": "application/json", "x-upsert": "true"}
    try: 
        requests.post(url, headers=headers, data=json.dumps(HAFIZA, indent=4), timeout=5)
        print("💾 Hafıza Supabase kutusuna başarıyla kilitlendi!")
    except: pass

try: bulut_hafiza_yukle()
except: pass

# ==========================================
# 📡 DERİN VERİ VE İLETİŞİM MOTORU
# ==========================================
def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: 
        requests.post(url, json={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}, timeout=5)
    except: 
        pass

def derin_finansal_analiz(sembol):
    try:
        # Teknik Analiz Verisi (Son 1 Ay)
        df = yf.download(sembol, period="1mo", progress=False, timeout=6)
        if df.empty: return None
        
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.droplevel(1)
            
        guncel_fiyat = float(df['Close'].iloc[-1])
        rsi = ta.momentum.rsi(df['Close'], window=14).iloc[-1] if len(df) >= 14 else 50.0
        
        # Temel Rasyoları Buluttan veya Sistemden Çek (yfinance BIST için kararsız çünkü)
        rasyolar = HAFIZA.get("temel_veriler", {}).get(sembol, {"fk": "Bilinmiyor", "pddd": "Bilinmiyor"})
        
        # Portföy Maliyet Kontrolü
        portfoy = HAFIZA.get("portfoy", {})
        maliyet_notu = "Mevcut Değil"
        if sembol in portfoy:
            m_fiyat = portfoy[sembol]["maliyet"]
            lot = portfoy[sembol]["lot"]
            kz = ((guncel_fiyat - m_fiyat) / m_fiyat) * 100
            maliyet_notu = f"Pozisyonda: {lot} Lot var | Maliyet: {m_fiyat} | Anlık K/Z: %{kz:.2f}"

        return {
            "sembol": sembol,
            "fiyat": f"{guncel_fiyat:.2f}",
            "rsi": f"{rsi:.1f}",
            "fk": rasyolar.get("fk", "-"),
            "pddd": rasyolar.get("pddd", "-"),
            "portfoy_durumu": maliyet_notu
        }
    except:
        return None

def ajani_calistir():
    veriler_paketi = []
    hisseler = HAFIZA.get("takip_listesi", TAKIP_YEDEK)
    
    for s in hisseler:
        res = derin_finansal_analiz(s)
        if res: veriler_paketi.append(res)
        time.sleep(0.5)
        
    if not veriler_paketi:
        telegram_mesaj_gonder("❌ Hisse fiyatları çekilemedi reis, internet hattını kontrol et.")
        return

    try:
        prompt = f"""
        Sen fon yöneten elit bir borsa stratejistisin. Sana gelen şu finansal paketi derinlemesine analiz et:
        Veri İçeriği: {json.dumps(veriler_paketi, indent=2)}
        
        Senden İstenenler:
        1. Her şirketin adını, fiyatını, F/K ve PD/DD değerlerini raporda açıkça belirt (Sakın gizleme!).
        2. RSI değerine göre aşırı alım mı satım mı yorumla.
        3. Portföy durumu 'Mevcut Değil' olmayan hissede maliyet analizine göre net bir 'TUT/EKLE/AZALT' stratejisi kur.
        Raporu profesyonel borsa bülteni formatında, okunaklı emojilerle Telegram'a yaz.
        """
        
        if model:
            rapor = model.generate_content(prompt).text
        else:
            rapor = f"Teknik/Temel Paket:\n{json.dumps(veriler_paketi, indent=2)}"
            
        telegram_mesaj_gonder(f"📊 *STRATEJİK BORSA ANALİZ RAPORU*\n\n{rapor}")
        
        # 🔥 Her şey başarıyla bittiği için artık o boş kutuyu dolduruyoruz!
        bulut_hafiza_kaydet()
        
    except Exception as e:
        telegram_mesaj_gonder(f"⚠️ Rapor basılırken yapay zeka adımı çöktü: {e}")

# ==========================================
# ⚙️ TELEGRAM KOMUT DİNLEYİCİSİ
# ==========================================
def telegram_komutlari_dinle():
    global HAFIZA
    offset = HAFIZA.get("last_update_id", 0) + 1
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=10"
    try:
        res = requests.get(url, timeout=12).json()
        for u in res.get("result", []):
            HAFIZA["last_update_id"] = u["update_id"]
            if "message" in u and "text" in u["message"]:
                txt = u["message"]["text"]
                
                if txt.startswith("/analiz"):
                    telegram_mesaj_gonder("⏳ Komut alındı reis! Derin çarpan analizi ve fiyat blokları hesaplanıyor, lütfen bekleyin...")
                    threading.Thread(target=ajani_calistir).start()
    except:
        pass

def run_dummy_server(): 
    try: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), SimpleHTTPRequestHandler).serve_forever()
    except: pass

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("Bot sorunsuzca dinlemede reis...")
    while True:
        telegram_komutlari_dinle()
        time.sleep(2)
        
