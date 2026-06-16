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
import datetime as dt

# ==========================================
# 🧠 FABRİKA AYARLARI (Yedek Hafıza)
# ==========================================
SABIT_GECHMIS_DERSLER = [
    {"tarih": "2026-06-15", "ders": "ÖĞRENİLEN DERS: Jeopolitik spekülasyonlar yerine tamamen matematiksel rasyolara ve teknik indikatörlere odaklanılmalıdır."},
    {"tarih": "2026-06-16", "ders": "ÖĞRENİLEN DERS: Canlı veri kısıtlıysa temel analiz rasyoları elle girilip bulutta saklanmalıdır."}
]

PORTFOY_YEDEK = {"SASA.IS": {"lot": 19, "maliyet": 3.65}}
TAKIP_YEDEK = ["THYAO.IS", "TUPRS.IS", "USDTRY=X", "GC=F", "SASA.IS", "KCHOL.IS", "NVDA", "INTC"]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

genai.configure(api_key=str(GEMINI_API_KEY).strip())
model = genai.GenerativeModel('gemini-2.5-flash')

HAFIZA = {}

# ==========================================
# ☁️ SUPABASE BULUT HAFIZA MOTORU
# ==========================================
def bulut_hafiza_yukle():
    global HAFIZA
    if not SUPABASE_URL or not SUPABASE_KEY:
        HAFIZA = {"takip_listesi": TAKIP_YEDEK, "portfoy": PORTFOY_YEDEK, "temel_veriler": {}, "ogrenilen_dersler": SABIT_GECHMIS_DERSLER, "hisse_tarihcesi": {}}
        return
    url = f"{SUPABASE_URL}/storage/v1/object/ajan_hafizasi/hafiza.json"
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200: 
            HAFIZA = res.json()
            if "hisse_tarihcesi" not in HAFIZA: HAFIZA["hisse_tarihcesi"] = {}
        else: 
            HAFIZA = {"takip_listesi": TAKIP_YEDEK, "portfoy": PORTFOY_YEDEK, "temel_veriler": {}, "ogrenilen_dersler": SABIT_GECHMIS_DERSLER, "hisse_tarihcesi": {}}
    except:
        HAFIZA = {"takip_listesi": TAKIP_YEDEK, "portfoy": PORTFOY_YEDEK, "temel_veriler": {}, "ogrenilen_dersler": SABIT_GECHMIS_DERSLER, "hisse_tarihcesi": {}}

def bulut_hafiza_kaydet():
    if not SUPABASE_URL or not SUPABASE_KEY: return
    url = f"{SUPABASE_URL}/storage/v1/object/ajan_hafizasi/hafiza.json"
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY, "Content-Type": "application/json", "x-upsert": "true"}
    try: requests.post(url, headers=headers, data=json.dumps(HAFIZA, indent=4), timeout=5)
    except: pass

bulut_hafiza_yukle()

# ==========================================
# 📡 KÜRESEL HABER MOTORU
# ==========================================
def son_dakika_haberleri_al():
    try:
        res = requests.get("https://news.google.com/rss/search?q=finance+economy+markets&hl=en-US&gl=US&ceid=US:en", timeout=5)
        if res.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res.content, 'xml')
            return " | ".join([item.title.text for item in soup.find_all('item')[:4]])
    except: pass
    return "Küresel piyasalar dinamik seyrini koruyor."

# ==========================================
# 📊 REİSİN AKILLI KADEMELİ VERİ MOTORU
# ==========================================
def finansal_veri_topla(sembol):
    try:
        bugun = dt.date.today().strftime("%Y-%m-%d")
        tarihce = HAFIZA.get("hisse_tarihcesi", {}).get(sembol, [])
        
        # Eğer hafızada veri varsa ve son veri bugüne aitse direkt hafızadan oku (yfinance'e hiç gitme!)
        if tarihce and tarihce[-1]['tarih'] == bugun:
            df = pd.DataFrame(tarihce)
            df.set_index('tarih', inplace=True)
        else:
            # Hafıza boşsa 1 yıllık indir, varsa sadece eksik olan son 5 günlük veriyi çekip üzerine ekle
            if not tarihce:
                df_yeni = yf.download(sembol, period="1y", progress=False, timeout=5)
            else:
                df_yeni = yf.download(sembol, period="5d", progress=False, timeout=5)
            
            if df_yeni.empty and tarihce:
                df = pd.DataFrame(tarihce).set_index('tarih')
            elif df_yeni.empty:
                return None
            else:
                if isinstance(df_yeni.columns, pd.MultiIndex): 
                    df_yeni.columns = df_yeni.columns.droplevel(1)
                
                # Yeni gelen veriyi sözlük formatına çevir
                yeni_liste = []
                for index, row in df_yeni.iterrows():
                    tstr = index.strftime("%Y-%m-%d")
                    yeni_liste.append({"tarih": tstr, "Close": float(row['Close'])})
                
                # Eski veriyle birleştir (mükerrer kayıtları engelle)
                birlesik_sözlük = {t['tarih']: t['Close'] for t in tarihce}
                for n in yeni_liste:
                    birlesik_sözlük[n['tarih']] = n['Close']
                
                # Sırala ve hafızayı güncelle (Son 250 günü tut, gerisini sil ki bulut şişmesin)
                sirali_tarihler = sorted(birlesik_sözlük.keys())[-250:]
                yeni_tarihce = [{"tarih": k, "Close": birlesik_sözlük[k]} for k in sirali_tarihler]
                
                if "hisse_tarihcesi" not in HAFIZA: HAFIZA["hisse_tarihcesi"] = {}
                HAFIZA["hisse_tarihcesi"][sembol] = yeni_tarihce
                
                df = pd.DataFrame(yeni_tarihce)
                df.set_index('tarih', inplace=True)

        close_series = df['Close'].astype(float)
        guncel_fiyat = float(close_series.iloc[-1])
        
        # 1 yıllık veri üzerinde tam ve sağlıklı indikatör hesabı
        rsi = ta.momentum.rsi(close_series, window=14).iloc[-1] if len(close_series) >= 14 else 50.0
        macd = ta.trend.macd(close_series).iloc[-1] if len(close_series) >= 26 else 0.0
        signal = ta.trend.macd_signal(close_series).iloc[-1] if len(close_series) >= 26 else 0.0
        
        temel = HAFIZA.get("temel_veriler", {}).get(sembol, {"fk": "-", "pddd": "-"})
        portfoy_notu = ""
        if sembol in HAFIZA.get("portfoy", {}):
            p = HAFIZA["portfoy"][sembol]
            kz = ((guncel_fiyat - p['maliyet']) / p['maliyet']) * 100
            portfoy_notu = f"| Pozisyon: %{kz:.1f} Kâr"

        return f"{sembol} (Fiyat: {guncel_fiyat:.2f}, RSI: {rsi:.1f}, MACD: {'AL' if macd > signal else 'SAT'}, F/K: {temel['fk']}, PD/DD: {temel['pddd']} {portfoy_notu})"
    except Exception as e:
        return f"{sembol} (Hata: {str(e)})"

def ajani_calistir():
    veriler = []
    for s in HAFIZA.get("takip_listesi", TAKIP_YEDEK):
        res = finansal_veri_topla(s)
        if res: veriler.append(res)
        time.sleep(0.2)
        
    # Tüm yeni verileri tek seferde buluta kilitle
    bulut_hafiza_kaydet()
    
    guncel_haberler = son_dakika_haberleri_al()
    
    prompt = f"""
    Sen kıdemli bir borsa analistisin. Aşağıdaki verileri yorumlayıp Telegram için rapor yaz.
    Haberler: {guncel_haberler}
    Teknik Veriler: {veriler}
    Format: Girişte 1 cümle piyasa havası, ardından her hisse için maksimum 2 cümle nokta atışı yorum ve net beklenti yaz. Kısa ve vurucu olsun.
    """
    try:
        rapor = model.generate_content(prompt).text
        telegram_mesaj_gonder(f"📊 *PİYASA ANALİZ RAPORU*\n\n{rapor}")
    except Exception as e:
        telegram_mesaj_gonder(f"❌ Yapay zeka adımında hata: {str(e)}")

# ==========================================
# ⚙️ TELEGRAM KOMUT DİNLEYİCİSİ
# ==========================================
def telegram_komutlari_dinle():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={HAFIZA.get('last_update_id', 0) + 1}"
    try:
        res = requests.get(url, timeout=5).json()
        for u in res.get("result", []):
            HAFIZA["last_update_id"] = u["update_id"]
            if "message" in u and "text" in u["message"]:
                txt = u["message"]["text"]
                
                if txt.startswith("/analiz"):
                    telegram_mesaj_gonder("⏳ Reis, sistem akıllı hafızayı devreye alıyor ve verileri işliyor, lütfen bekleyin...")
                    threading.Thread(target=ajani_calistir).start()
                    
                elif txt.startswith("/rasyo_ekle"):
                    try:
                        _, s, fk, pddd = txt.split()
                        if "temel_veriler" not in HAFIZA: HAFIZA["temel_veriler"] = {}
                        HAFIZA["temel_veriler"][s.upper()] = {"fk": fk, "pddd": pddd}
                        bulut_hafiza_kaydet()
                        telegram_mesaj_gonder(f"✅ {s.upper()} rasyoları bulut hafızasına kaydedildi.")
                    except:
                        telegram_mesaj_gonder("❌ Hatalı komut. Örnek: `/rasyo_ekle THYAO.IS 3.20 1.15`")
    except: pass

def run_dummy_server(): 
    HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), SimpleHTTPRequestHandler).serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    while True:
        telegram_komutlari_dinle()
        time.sleep(3)
        
