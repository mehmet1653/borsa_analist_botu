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
    try: requests.post(url, headers=headers, data=json.dumps(HAFIZA, indent=4), timeout=5)
    except: pass

try: bulut_hafiza_yukle()
except: pass

# ==========================================
# 📡 ALTERNATİF CANLI VERİ KAZIYICI (GOOGLE FINANCE)
# ==========================================
def google_finance_canli_fiyat(sembol):
    """yfinance çökerse Google Finance üzerinden %100 canlı fiyatı çeker"""
    try:
        google_kod = sembol.replace(".IS", "").replace("IST:", "")
        url = f"https://www.google.com/finance/quote/{google_kod}:IST"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            text = res.text
            # Google'ın kaynak kodundan anlık fiyat hücresini cımbızlıyoruz
            marker = f'data-last-price="'
            if marker in text:
                idx = text.find(marker) + len(marker)
                end_idx = text.find('"', idx)
                fiyat = float(text[idx:end_idx].replace(",", ""))
                return f"{fiyat:.2f}"
    except:
        pass
    return None

# ==========================================
# 📊 DERİN VERİ VE İLETİŞİM MOTORU
# ==========================================
def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def derin_finansal_analiz(sembol):
    guncel_fiyat = None
    rsi_degeri = "50.0"
    
    # 1. YÖNTEM: Yahoo Finance ile indirmeyi dene
    try:
        df = yf.download(sembol, period="1mo", progress=False, timeout=4)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): 
                df.columns = df.columns.droplevel(1)
            fiyat_hesap = float(df['Close'].iloc[-1])
            guncel_fiyat = f"{fiyat_hesap:.2f}"
            if len(df) >= 14:
                rsi_hesap = ta.momentum.rsi(df['Close'], window=14).iloc[-1]
                rsi_degeri = f"{rsi_hesap:.1f}"
    except:
        print(f"⚠️ {sembol} için Yahoo kısıtlandı, Google Finance deneniyor...")

    # 2. YÖNTEM: Yahoo patladıysa hemen Google Finance can simidini at
    if not guncel_fiyat:
        guncel_fiyat = google_finance_canli_fiyat(sembol)
        
    # 3. YÖNTEM: İkisi de gelmezse çökme, en kötü şablon fiyatı bas
    if not guncel_fiyat:
        guncel_fiyat = "Bilinmiyor"

    # Temel Rasyoları Buluttan/Hafızadan Çek
    rasyolar = HAFIZA.get("temel_veriler", {}).get(sembol, {"fk": "-", "pddd": "-"})
    
    # Portföy Maliyet Kontrolü
    portfoy = HAFIZA.get("portfoy", {})
    maliyet_notu = "Mevcut Değil"
    if sembol in portfoy and guncel_fiyat != "Bilinmiyor":
        try:
            m_fiyat = portfoy[sembol]["maliyet"]
            lot = portfoy[sembol]["lot"]
            kz = ((float(guncel_fiyat) - m_fiyat) / m_fiyat) * 100
            maliyet_notu = f"Pozisyonda: {lot} Lot var | Maliyet: {m_fiyat} | Anlık K/Z: %{kz:.2f}"
        except: pass

    return {
        "sembol": sembol,
        "fiyat": guncel_fiyat,
        "rsi": rsi_degeri,
        "fk": rasyolar.get("fk", "-"),
        "pddd": rasyolar.get("pddd", "-"),
        "portfoy_durumu": maliyet_notu
    }

def ajani_calistir():
    veriler_paketi = []
    hisseler = HAFIZA.get("takip_listesi", TAKIP_YEDEK)
    
    for s in hisseler:
        res = derin_finansal_analiz(s)
        if res: veriler_paketi.append(res)
        time.sleep(0.5)
        
    try:
        prompt = f"""
        Sen fon yöneten elit bir borsa stratejistisin. Sana gelen şu finansal paketi derinlemesine analiz et:
        Veri İçeriği: {json.dumps(veriler_paketi, indent=2)}
        
        Senden İstenenler:
        1. Her şirketin adını, güncel fiyatını, F/K ve PD/DD değerlerini raporda açıkça belirt.
        2. RSI değerine göre teknik durumu yorumla.
        3. Portföy durumu 'Mevcut Değil' olmayan hissede maliyet analizine göre net bir aksiyon stratejisi kur.
        Raporu profesyonel borsa bülteni formatında, okunaklı emojilerle Telegram'a yaz. Kısa, öz ve stratejik olsun.
        """
        
        if model:
            rapor = model.generate_content(prompt).text
        else:
            rapor = f"Teknik/Temel Paket:\n{json.dumps(veriler_paketi, indent=2)}"
            
        telegram_mesaj_gonder(f"📊 *STRATEJİK BORSA ANALİZ RAPORU*\n\n{rapor}")
        bulut_hafiza_kaydet()
        
    except Exception as e:
        telegram_mesaj_gonder(f"⚠️ Rapor basılırken bir sorun çıktı reis: {e}")

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
                    telegram_mesaj_gonder("⏳ Komut alındı reis! Yahoo engelleri Google Finance yedek hattıyla aşılıyor, derin rapor hazırlanıyor...")
                    threading.Thread(target=ajani_calistir).start()
    except:
        pass

def run_dummy_server(): 
    try: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), SimpleHTTPRequestHandler).serve_forever()
    except: pass

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("Yedek hatlı koruma kalkanı devrede...")
    while True:
        telegram_komutlari_dinle()
        time.sleep(2)
        
