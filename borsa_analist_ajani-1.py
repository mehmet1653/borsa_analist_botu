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
from datetime import datetime

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
    "gecmis_ongoruler": {}, 
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
            for anahtar in ["takip_listesi", "portfoy", "temel_veriler", "gecmis_ongoruler", "last_update_id"]:
                if anahtar in yuklenen: HAFIZA[anahtar] = yuklenen[anahtar]
            print("✅ Küresel derin hafıza buluttan senkronize edildi, Mehmet.")
    except: pass

def bulut_hafiza_kaydet():
    if not SUPABASE_URL or not SUPABASE_KEY: return
    url = f"{SUPABASE_URL}/storage/v1/object/ajan_hafizasi/hafiza.json"
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY, "Content-Type": "application/json", "x-upsert": "true"}
    try: requests.post(url, headers=headers, data=json.dumps(HAFIZA, indent=4), timeout=5)
    except: pass

def hafizayi_budat():
    """Hafızayı sadece son 1 haftalık veriye indirger, şişmeyi engeller."""
    global HAFIZA
    if "gecmis_ongoruler" in HAFIZA:
        tarih_siniri = time.time() - (7 * 86400)
        yeni_gecmis = {}
        for hisse, veri in HAFIZA["gecmis_ongoruler"].items():
            try:
                t = time.mktime(time.strptime(veri["analiz_tarihi"], "%Y-%m-%d"))
                if t > tarih_siniri: yeni_gecmis[hisse] = veri
            except: continue
        HAFIZA["gecmis_ongoruler"] = yeni_gecmis

try: bulut_hafiza_yukle()
except: pass

# ==========================================
# 📡 KÜRESEL VERİ VE FİYAT TOPLAMA MOTORU
# ==========================================
def google_finance_canli_fiyat(sembol):
    try:
        google_kod = sembol.replace(".IS", "")
        url = f"https://www.google.com/finance/quote/{google_kod}:IST"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            text = res.text
            marker = 'data-last-price="'
            if marker in text:
                idx = text.find(marker) + len(marker)
                end_idx = text.find('"', idx)
                return f"{float(text[idx:end_idx].replace(',', '')):.2f}"
    except: pass
    return None

def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def derin_finansal_analiz(sembol):
    guncel_fiyat = None
    rsi_degeri = "50.0"
    
    try:
        df = yf.download(sembol, period="1mo", progress=False, timeout=4)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
            guncel_fiyat = f"{float(df['Close'].iloc[-1]):.2f}"
            if len(df) >= 14: rsi_degeri = f"{ta.momentum.rsi(df['Close'], window=14).iloc[-1]:.1f}"
    except: pass

    if not guncel_fiyat: guncel_fiyat = google_finance_canli_fiyat(sembol)
    if not guncel_fiyat: guncel_fiyat = "Bilinmiyor"

    rasyolar = HAFIZA.get("temel_veriler", {}).get(sembol, {"fk": "-", "pddd": "-"})
    portfoy = HAFIZA.get("portfoy", {})
    maliyet_notu = "Mevcut Değil"
    if sembol in portfoy and guncel_fiyat != "Bilinmiyor":
        try:
            m_fiyat = portfoy[sembol]["maliyet"]
            lot = portfoy[sembol]["lot"]
            kz = ((float(guncel_fiyat) - m_fiyat) / m_fiyat) * 100
            maliyet_notu = f"{lot} Lot | Maliyet: {m_fiyat} | K/Z: %{kz:.2f}"
        except: pass

    return {
        "sembol": sembol,
        "fiyat": guncel_fiyat,
        "rsi": rsi_degeri,
        "fk": rasyolar.get("fk", "-"),
        "pddd": rasyolar.get("pddd", "-"),
        "portfoy_durumu": maliyet_notu
    }

# ==========================================
# 🧠 KENDİ KENDİNİ KALİBRE EDEN ÇALIŞMA MOTORU
# ==========================================
def ajani_calistir(is_otomatik_kapanis=False):
    hafizayi_budat()
    veriler_paketi = []
    hisseler = HAFIZA.get("takip_listesi", TAKIP_YEDEK)
    
    for s in hisseler:
        res = derin_finansal_analiz(s)
        if res: veriler_paketi.append(res)
        time.sleep(0.5)

    küresel_haberler = [
        "Küresel merkez bankalarının faiz politikaları ve enflasyon baskıları emtia ve borsaları baskılıyor.",
        "Borsa İstanbul genelinde yabancı giriş-çıkış hareketleri ve hacim daralması/genişlemesi takip ediliyor."
    ]

    try:
        prompt = f"""
        Sen Mehmet'in özel fon yöneticisisin. {'Bu bir GÜN SONU KAPANIŞ analizidir.' if is_otomatik_kapanis else ''}
        Sen HATALARINDAN DERS ÇIKARAN bir yapay zekasın. Mehmet'e hitap et, 'reis' deme.
        
        Sana sunulan veriler:
        1. Güncel Hisse Verileri: {json.dumps(veriler_paketi, indent=2)}
        2. Küresel Haberler: {json.dumps(küresel_haberler, indent=2)}
        3. Geçmiş Tahminler: {json.dumps(HAFIZA.get("gecmis_ongoruler", {}), indent=2)}
        
        [ADIM 1: BACKTEST] Geçmiş tahminlerini bugünle kıyasla. Yanıldıysan nedenini açıkla.
        [ADIM 2: DURUM ETİKETLERİ] [OLUMLU], [OLUMSUZ] veya [TEMKİNLİ] etiketle ve nedenini yaz.
        [ADIM 3: ÖNGÖRÜ] Önümüzdeki hafta için yön tahmini bırak.
        """
        
        if model:
            rapor = model.generate_content(prompt).text
            
            yeni_ongoruler = {}
            for v in veriler_paketi:
                yeni_ongoruler[v["sembol"]] = {
                    "eski_fiyat": v["fiyat"],
                    "analiz_tarihi": time.strftime("%Y-%m-%d")
                }
            HAFIZA["gecmis_ongoruler"] = yeni_ongoruler
        else:
            rapor = "Analiz motoru aktif."
            
        telegram_mesaj_gonder(f"📊 *STRATEJİK BORSA ANALİZ RAPORU*\n\n{rapor}")
        bulut_hafiza_kaydet()
    except Exception as e:
        telegram_mesaj_gonder(f"⚠️ Hata: {e}")

# ==========================================
# ⚙️ OTOMATİK ZAMANLAYICI VE DİNLEYİCİ
# ==========================================
def zamanlayici_motoru():
    while True:
        simdi = datetime.now()
        if simdi.hour == 17 and 55 <= simdi.minute <= 59:
            ajani_calistir(is_otomatik_kapanis=True)
            time.sleep(600)
        time.sleep(60)

def telegram_komutlari_dinle():
    global HAFIZA
    offset = HAFIZA.get("last_update_id", 0) + 1
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=10"
    try:
        res = requests.get(url, timeout=12).json()
        for u in res.get("result", []):
            HAFIZA["last_update_id"] = u["update_id"]
            if "message" in u and "text" in u["message"]:
                if u["message"]["text"].startswith("/analiz"):
                    threading.Thread(target=ajani_calistir).start()
    except: pass

def run_dummy_server(): 
    try: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), SimpleHTTPRequestHandler).serve_forever()
    except: pass

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    threading.Thread(target=zamanlayici_motoru, daemon=True).start()
    while True:
        telegram_komutlari_dinle()
        time.sleep(2)
        
