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
from bs4 import BeautifulSoup
import datetime as dt

# ==========================================
# 🧠 KORUMA KALKANI: ESKİ ÖĞRENİLEN DERSLER (SABİT HAFIZA)
# ==========================================
SABIT_GECHMIS_DERSLER = [
    {"tarih": "2026-06-15", "ders": "ÖĞRENİLEN DERS: Makro haber akışlarındaki abartılı risk senaryoları fiyatlara doğrudan yansımayabilir. Analizlerde jeopolitik spekülasyonlar yerine tamamen matematiksel rasyolara ve teknik indikatörlere odaklanılmalıdır."},
    {"tarih": "2026-06-16", "ders": "ÖĞRENİLEN DERS: Borsa İstanbul hisselerinde aracı kurum verileri geciktiğinde eski yedek verileri kullanmak hatalı çarpan analizine yol açar. Canlı veri yoksa analiz temkinli kalmalıdır."}
]

PORTFOY_YEDEK = {
    "SASA.IS": {"lot": 19, "maliyet": 3.65}
}
TAKIP_YEDEK = ["THYAO.IS", "TUPRS.IS", "USDTRY=X", "GC=F", "SASA.IS", "KRDMB.IS", "ASTOR.IS", "KCHOL.IS", "MRGYO.IS", "BTC-USD", "NVDA", "INTC", "ONDS"]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    GEMINI_API_KEY = "AQ.Ab8RN6K_wraDxTNfR-qaqeJHO40gdpJLWp3o8jWYnR3IYgi7PA"

genai.configure(api_key=str(GEMINI_API_KEY).strip())
model = genai.GenerativeModel('gemini-2.5-flash')

DATA_FILE = "ajan_hafizasi.json"

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        try: HAFIZA = json.load(f)
        except: HAFIZA = {}
else:
    HAFIZA = {}

if "takip_listesi" not in HAFIZA: HAFIZA["takip_listesi"] = TAKIP_YEDEK
if "portfoy" not in HAFIZA: HAFIZA["portfoy"] = PORTFOY_YEDEK
if "temel_veriler" not in HAFIZA: HAFIZA["temel_veriler"] = {}
if "tahmin_gunlugu" not in HAFIZA: HAFIZA["tahmin_gunlugu"] = {}
if "ogrenilen_dersler" not in HAFIZA or len(HAFIZA["ogrenilen_dersler"]) == 0: 
    HAFIZA["ogrenilen_dersler"] = SABIT_GECHMIS_DERSLER

RAPOR_KILITLERI = {"sabah": False, "aksam": False, "gece": False, "son_gun": ""}

def hafizayi_kaydet():
    with open(DATA_FILE, "w") as f:
        json.dump(HAFIZA, f, indent=4)

# ==========================================
# 📊 CANLI TEMEL RASYOLAR (BIST VE YABANCI)
# ==========================================
def tek_hisse_resmi_veri_cek(sembol):
    # Küresel/Yabancı Varlıklar veya Pariteler İçin Veri Çekme
    if not sembol.endswith(".IS"):
        if "=" in sembol or "-" in sembol or "GC=" in sembol:
            HAFIZA["temel_veriler"][sembol] = {"fk": "N/A", "pddd": "N/A", "ihracat": "-", "ozsermaye_kar": "-"}
            return True
        try:
            ticker = yf.Ticker(sembol)
            info = ticker.info
            fk = info.get("trailingPE", info.get("forwardPE", "-"))
            pddd = info.get("priceToBook", "-")
            fk_str = f"{float(fk):.2f}" if (fk and fk != "-") else "-"
            pddd_str = f"{float(pddd):.2f}" if (pddd and pddd != "-") else "-"
            HAFIZA["temel_veriler"][sembol] = {"fk": fk_str, "pddd": pddd_str, "ihracat": "-", "ozsermaye_kar": "-"}
            return True
        except:
            HAFIZA["temel_veriler"][sembol] = {"fk": "-", "pddd": "-", "ihracat": "-", "ozsermaye_kar": "-"}
            return False

    # BIST Hisseleri İçin Veri Çekme
    hisse_kodu = sembol.split(".")[0]
    try:
        api_url = f"https://api.frayzer.com/v1/financials/bist/{hisse_kodu}"
        response = requests.get(api_url, timeout=4)
        if response.status_code == 200:
            data = response.json()
            fk = data.get("fk")
            pddd = data.get("pddd")
            if fk and pddd and fk != "-" and pddd != "-":
                HAFIZA["temel_veriler"][sembol] = {
                    "fk": f"{float(fk):.2f}", "pddd": f"{float(pddd):.2f}",
                    "ihracat": f"%{data.get('export_ratio', '-')}", "ozsermaye_kar": f"%{data.get('roe', '-')}"
                }
                return True

        url = f"https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/Sirket-Karti.aspx?hisse={hisse_kodu}"
        res = requests.get(url, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        fk_td = soup.find("td", text="F/K")
        pddd_td = soup.find("td", text="PD/DD")
        if fk_td and pddd_td:
            fk_val = fk_td.find_next_sibling("td").text.strip().replace(",", ".")
            pddd_val = pddd_td.find_next_sibling("td").text.strip().replace(",", ".")
            HAFIZA["temel_veriler"][sembol] = {"fk": fk_val, "pddd": pddd_val, "ihracat": "-", "ozsermaye_kar": "-"}
            return True
    except:
        pass
    
    if sembol not in HAFIZA["temel_veriler"]:
        HAFIZA["temel_veriler"][sembol] = {"fk": "-", "pddd": "-", "ihracat": "-", "ozsermaye_kar": "-"}
    return False

# ==========================================
# ⚙️ TELEGRAM İLETİŞİM MOTORU
# ==========================================
def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    MAX_LEN = 3500  
    if len(mesaj) > MAX_LEN:
        parcalar = [mesaj[i:i+MAX_LEN] for i in range(0, len(mesaj), MAX_LEN)]
        for parca in parcalar: 
            telegram_mesaj_gonder(parca)
            time.sleep(0.5)
        return
    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}
    try: 
        res = requests.post(url, json=payload, timeout=10).json()
        if not res.get("ok"): requests.post(url, json={"chat_id": CHAT_ID, "text": mesaj}, timeout=10)
    except Exception as e: print(f"⚠️ Telegram gönderme hatası: {e}")

def telegram_komutlari_dinle():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    offset = HAFIZA.get("last_update_id", 0) + 1
    try:
        response = requests.get(url, params={"offset": offset, "timeout": 5}, timeout=10).json()
        if not response.get("result"): return
        for update in response["result"]:
            HAFIZA["last_update_id"] = update["update_id"]
            hafizayi_kaydet()
            message = update.get("message", {})
            text = message.get("text", "")
            chat_id = str(message.get("chat", {}).get("id", ""))
            if chat_id != CHAT_ID: continue 
            parcalar = text.split()
            if not parcalar: continue
            komut = parcalar[0].lower()
            
            if komut == "/takip_listesi":
                if HAFIZA["takip_listesi"]:
                    liste = "\n".join([f"• `{h}`" for h in HAFIZA["takip_listesi"]])
                    telegram_mesaj_gonder(f"📋 *Güncel Takip Listeniz:*\n\n{liste}")
                else: telegram_mesaj_gonder("📋 Takip listeniz boş.")
                
            elif komut == "/portfoy_goster":
                if HAFIZA["portfoy"]:
                    mesaj = "💰 *Güncel Portföy Varlıklarınız:*\n\n"
                    for hisse, bilgi in HAFIZA["portfoy"].items():
                        mesaj += f"📌 `{hisse}`\n  - Lot: {bilgi['lot']} | Maliyet: {bilgi['maliyet']:.2f} TL\n"
                    telegram_mesaj_gonder(mesaj)
                else: telegram_mesaj_gonder("💰 Portföyünüz şu an boş, maliyet takibi yapılmıyor.")
                
            elif komut == "/analiz":
                telegram_mesaj_gonder("🔄 Gerçek zamanlı fiyatlar ve rasyolar analiz ediliyor...")
                ajani_calistir(rapor_tipi="KULLANICI TALEBİ ANLIK FİNANSAL ANALİZ")
                
            elif komut == "/takip_ekle" and len(parcalar) > 1:
                girdi = parcalar[1].upper()
                if girdi not in HAFIZA["takip_listesi"]:
                    HAFIZA["takip_listesi"].append(girdi)
                    tek_hisse_resmi_veri_cek(girdi)
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"✅ `{girdi}` başarıyla takip listesine eklendi!")
                    
            elif komut == "/takip_cikar" and len(parcalar) > 1:
                hisse = parcalar[1].upper()
                if hisse in HAFIZA["takip_listesi"]: HAFIZA["takip_listesi"].remove(hisse)
                hafizayi_kaydet()
                telegram_mesaj_gonder(f"❌ `{hisse}` takip listesinden çıkarıldı.")

            elif komut == "/portfoy_ekle" and len(parcalar) > 3:
                hisse = parcalar[1].upper()
                try:
                    lot = int(parcalar[2])
                    maliyet = float(parcalar[3].replace(",", "."))
                    HAFIZA["portfoy"][hisse] = {"lot": lot, "maliyet": maliyet}
                    if hisse not in HAFIZA["takip_listesi"]:
                        HAFIZA["takip_listesi"].append(hisse)
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"💰 *Portföy Güncellendi!*\n`{hisse}`: {lot} Lot | Maliyet: {maliyet:.2f} TL")
                except:
                    telegram_mesaj_gonder("⚠️ Hatalı kullanım! Örnek: `/portfoy_ekle THYAO.IS 10 325.50`")

            elif komut == "/portfoy_cikar" and len(parcalar) > 1:
                hisse = parcalar[1].upper()
                if hisse in HAFIZA["portfoy"]:
                    del HAFIZA["portfoy"][hisse]
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"✅ `{hisse}` portföyünüzden tamamen silindi.")
                else:
                    telegram_mesaj_gonder(f"❓ `{hisse}` zaten portföyünüzde kayıtlı değil.")
    except: pass

def finansal_veri_topla(sembol):
    try:
        df = yf.download(sembol, period="5d", interval="1m", progress=False)
        if df.empty: df = yf.download(sembol, period="1y", interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
        df.columns = [str(col).strip() for col in df.columns]
        guncel_fiyat = float(df['Close'].iloc[-1])
        
        df_daily = yf.download(sembol, period="1y", interval="1d", progress=False)
        if isinstance(df_daily.columns, pd.MultiIndex): df_daily.columns = df_daily.columns.droplevel(1)
        close_series = df_daily['Close'].astype(float)
        df_daily['RSI'] = ta.momentum.rsi(close_series, window=14)
        df_daily['SMA_50'] = ta.trend.sma_indicator(close_series, window=50)
        df_daily['MACD'] = ta.trend.macd(close_series)
        df_daily['MACD_Signal'] = ta.trend.macd_signal(close_series)
        
        tek_hisse_resmi_veri_cek(sembol)
        temel = HAFIZA.get("temel_veriler", {}).get(sembol, {"fk": "-", "pddd": "-"})
        
        portfoy_notu = "YOK"
        if sembol in HAFIZA["portfoy"]:
            p = HAFIZA["portfoy"][sembol]
            kar_zarar = ((guncel_fiyat - p['maliyet']) / p['maliyet']) * 100
            portfoy_notu = f"Kullanıcı Pozisyonu -> Lot: {p['lot']}, Maliyet: {p['maliyet']:.2f}, Güncel Kâr/Zarar: %{kar_zarar:.2f}"

        return {
            "fiyat": guncel_fiyat, "rsi": f"{df_daily['RSI'].iloc[-1]:.2f}", "sma_50": f"{df_daily['SMA_50'].iloc[-1]:.2f}",
            "macd": "AL SİNYALİ" if df_daily['MACD'].iloc[-1] > df_daily['MACD_Signal'].iloc[-1] else "SAT SİNYALİ",
            "fk": temel.get("fk", "-"), "pddd": temel.get("pddd", "-"), 
            "portfoy_durumu": portfoy_notu
        }
    except: return None

# ==========================================
# 🧠 YAPAY ZEKA RAPORLAMA MOTORU
# ==========================================
def ajani_calistir(rapor_tipi="GÜNLÜK DEĞERLENDİRME"):
    tr_saati = dt.datetime.utcnow() + dt.timedelta(hours=3)
    piyasa_ozeti = ""
    
    for sembol in HAFIZA["takip_listesi"]:
        veri = finansal_veri_topla(sembol)
        if veri:
            piyasa_ozeti += f"\n📌 {sembol}\n  - Fiyat: {veri['fiyat']:.2f} | RSI: {veri['rsi']} | MACD: {veri['macd']} | MA50: {veri['sma_50']}\n" \
                            f"  - Temel Çarpanlar -> F/K: {veri['fk']} | PD/DD: {veri['pddd']}\n" \
                            f"  - [YATIRIM DURUMU]: {veri['portfoy_durumu']}\n"
        time.sleep(0.3)

    tecrubeler_metni = "\n🧠 GEÇMİŞ TECRÜBELER VE KURALLAR:\n"
    for d in HAFIZA["ogrenilen_dersler"]: tecrubeler_metni += f"- {d['ders']}\n"

    prompt = f"""
    Sen rasyonel ve sadece MATEMATİKSEL VERİLERLE konuşan kıdemli bir finans yapay zekasısın.
    Asla kanıtlanmamış spekülasyonları, abartılı felaket senaryolarını rapora dahil etme. 
    Açıklamalarını kısa, net, okunabilir tut. Destan yazma, Telegram karakter sınırını aşma.
    
    RAPOR TÜRÜ: {rapor_tipi}
    FİNANSAL VERİLER: {piyasa_ozeti}
    {tecrubeler_metni}
    
    Aşağıdaki şablona HARFİYEN uyarak ve her maddeyi kısa tutarak analiz et:
    ---
    ### [HİSSE ADI]
    * Fiyat: [Fiyat] | RSI: [RSI] | MACD: [MACD] | MA50: [MA50]
    * F/K: [F/K] | PD/DD: [PD/DD]
    * TREND: [OLUMLU / OLUMSUZ / TEMKİNLİ]
    * Yorum: [Teknik ve temel durumu en fazla 2 kısa cümlede özetle.]
    * 📌 1 HAFTALIK ÖNGÖRÜ: "Mevcut momentum, financial rasyolar ve haber akışı korunduğu sürece önümüzdeki 1 hafta boyunca [olumlu seyrin/düzeltmenin/yatay seyrin] sürmesi beklenmektedir" kalıbına sadık kal.
    """
    try: 
        ai_raporu = model.generate_content(prompt).text
        simdi = tr_saati.strftime('%d/%m/%Y %H:%M')
        telegram_mesaj_gonder(f"📊 **AKILLI PORTFÖY VE ANALİZ RAPORU** 📊\n🗓 *Saat:* {simdi}\n───────────────\n{ai_raporu}")
    except Exception as e: print(f"Hata: {e}")

# ==========================================
# 🔄 ANA DÖNGÜ (7/24 DÖNGÜ)
# ==========================================
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler).serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("🚀 Akıllı Hassas Borsa Ajanı Başlatıldı.")
    
    while True:
        telegram_komutlari_dinle()
        tr_saati = dt.datetime.utcnow() + dt.timedelta(hours=3)
        bugun = tr_saati.strftime("%Y-%m-%d")
        saat_dakika = tr_saati.strftime("%H:%M")
        
        if RAPOR_KILITLERI["son_gun"] != bugun:
            RAPOR_KILITLERI["sabah"] = False
            RAPOR_KILITLERI["aksam"] = False
            RAPOR_KILITLERI["gece"] = False
            RAPOR_KILITLERI["son_gun"] = bugun
            
        if "11:00" <= saat_dakika <= "11:05" and not RAPOR_KILITLERI["sabah"]:
            ajani_calistir(rapor_tipi="SABAH AÇILIŞ VE PORTFÖY RİSK KONTROLÜ")
            RAPOR_KILITLERI["sabah"] = True
            
        elif "18:30" <= saat_dakika <= "18:35" and not RAPOR_KILITLERI["aksam"]:
            ajani_calistir(rapor_tipi="AKŞAM KAPANIŞ VE MALİYET DEĞERLENDİRMESİ")
            RAPOR_KILITLERI["aksam"] = True
            
        elif "23:30" <= saat_dakika <= "23:35" and not RAPOR_KILITLERI["gece"]:
            for s in HAFIZA["takip_listesi"]: tek_hisse_resmi_veri_cek(s)
            RAPOR_KILITLERI["gece"] = True
            print("💾 Gece tüm küresel ve yerel hafıza senkronizasyonu tamamlandı.")
            
        time.sleep(2)
        
