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

# Küresel yapıyı ve haftalık öngörüleri saklayan zırhlı hafıza şablonu
HAFIZA = {
    "takip_listesi": TAKIP_YEDEK,
    "portfoy": PORTFOY_YEDEK,
    "gecmis_ongoruler": {}, # Haftalık öngörülerin kontrolü için (Backtest)
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
            print("✅ Küresel hafıza buluttan senkronize edildi.")
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
# 📡 KÜRESEL HABER VE VERİ TOPLAMA MOTORU
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

    if not guncel_fiyat:
        guncel_fiyat = google_finance_canli_fiyat(sembol)
    if not guncel_fiyat:
        guncel_fiyat = "Bilinmiyor"

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
# 🧠 AJAN ÇALIŞMA VE KARAR MOTORU
# ==========================================
def ajani_calistir():
    veriler_paketi = []
    hisseler = HAFIZA.get("takip_listesi", TAKIP_YEDEK)
    
    for s in hisseler:
        res = derin_finansal_analiz(s)
        if res: veriler_paketi.append(res)
        time.sleep(0.5)

    # Küresel makro haberleri simüle eden dinamik kontekst paketi
    küresel_haberler = [
        "Küresel piyasalarda enflasyon ve faiz patikası takibi sürüyor.",
        "Borsa İstanbul'da yabancı takas oranları ve hacim değişimleri yakından izleniyor.",
        "Enerji ve sanayi sektörlerinde küresel tedarik zinciri ve emtia fiyatları hareketli."
    ]

    try:
        prompt = f"""
        Sen küresel makro gelişmeleri ve teknik/temel indikatörleri harmanlayan elit bir borsa stratejistisin.
        Aşağıdaki finansal paketi ve küresel haber başlıklarını kullanarak bizim o meşhur, derin ve taktiksel raporumuzu hazırla.
        
        Mevcut Veriler: {json.dumps(veriler_paketi, indent=2)}
        Küresel Gelişmeler: {json.dumps(küresel_haberler, indent=2)}
        Hafızadaki Geçmiş Haftalık Öngörüler: {json.dumps(HAFIZA.get("gecmis_ongoruler", {}), indent=2)}
        
        Sizden İstisnasız İstenen Format Kuralları:
        1. BAŞARI TESTİ (BACKTEST): Hafızada 'gecmis_ongoruler' varsa, o öngörülerin bugünkü fiyatlarla tutup tutmadığını kontrol et, net bir şekilde raporun başına yaz.
        2. DURUM ETİKETLERİ: Her hissenin yanına kesinlikle durumunu belirt: [OLUMLU], [OLUMSUZ] veya [TEMKİNLİ].
        3. KÜRESEL ENTEGRASYON: Küresel makro haberlerin ve indikatörlerin (RSI, F/K, PD/DD) hisseler üzerindeki etkisini derinlemesine bağdaştır.
        4. 1 HAFTALIK ÖNGÖRÜ: Her hisse için önümüzdeki 1 haftaya dair net bir fiyat koridoru veya yön öngörüsü bırak (Biz bunu sonraki hafta hafızadan kontrol edeceğiz).
        5. PORTFÖY stratejisini (özellikle maliyet zararda olan hisseler için) net tavsiyelerle yönet.
        
        Raporu o eski zengin, emojili, profesyonel fon analisti üslubuyla Telegram'a bas.
        """
        
        if model:
            rapor = model.generate_content(prompt).text
            
            # Gelecek hafta kontrol etmek üzere bu haftanın fiyatlarını ve öngörü ipuçlarını hafızaya kaydet
            yeni_ongoruler = {}
            for v in veriler_paketi:
                yeni_ongoruler[v["sembol"]] = {"ongoru_fiyati": v["fiyat"], "tarih": time.strftime("%Y-%m-%d")}
            HAFIZA["gecmis_ongoruler"] = yeni_ongoruler
        else:
            rapor = f"Zengin Analiz Blokları:\n{json.dumps(veriler_paketi, indent=2)}"
            
        telegram_mesaj_gonder(f"📊 *STRATEJİK BORSA ANALİZ RAPORU*\n\n{rapor}")
        bulut_hafiza_kaydet()
        
    except Exception as e:
        telegram_mesaj_gonder(f"⚠️ Raporlama motorunda hata oluştu reis: {e}")

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
                    telegram_mesaj_gonder("⏳ Komut alındı reis! Küresel makro haberler, indikatörler ve haftalık backtest motoru çalıştırılıyor, derin rapor hazırlanıyor...")
                    threading.Thread(target=ajani_calistir).start()
    except: pass

def run_dummy_server(): 
    try: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), SimpleHTTPRequestHandler).serve_forever()
    except: pass

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("Vizyoner Borsa Ajanı aktif...")
    while True:
        telegram_komutlari_dinle()
        time.sleep(2)
        
