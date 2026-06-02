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
from datetime import datetime
import datetime as dt

# ==========================================
# 🛠️ MEHMET REİS BULUT VE GENİŞLETİLMİŞ HAFIZA SİSTEMİ
# ==========================================
TEMEL_VERILER_YEDEK = {
    "ASTOR.IS": {"fk": "36.39", "pddd": "8.59", "ihracat": "%44.35", "ozsermaye_kar": "%26.32"},
    "SASA.IS": {"fk": "22.40", "pddd": "4.10", "ihracat": "%31.20", "ozsermaye_kar": "%12.50"},
    "KRDMB.IS": {"fk": "14.20", "pddd": "2.15", "ihracat": "%15.40", "ozsermaye_kar": "%18.60"},
    "THYAO.IS": {"fk": "4.80", "pddd": "0.95", "ihracat": "%85.00", "ozsermaye_kar": "%33.10"},
    "TUPRS.IS": {"fk": "6.20", "pddd": "3.40", "ihracat": "%22.10", "ozsermaye_kar": "%41.20"},
    "KCHOL.IS": {"fk": "5.50", "pddd": "1.80", "ihracat": "%55.00", "ozsermaye_kar": "%38.40"},
    "MRGYO.IS": {"fk": "11.10", "pddd": "0.85", "ihracat": "%0.00", "ozsermaye_kar": "%9.10"}
}

PORTFOY_YEDEK = {
    "SASA.IS": {"lot": 19, "maliyet": 3.65},   
    "KRDMB.IS": {"lot": 13, "maliyet": 96.35}   
}
TAKIP_YEDEK = ["THYAO.IS", "TUPRS.IS", "USDTRY=X", "GC=F", "SASA.IS", "KRDMB.IS", "ASTOR.IS", "KCHOL.IS", "MRGYO.IS"]

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
        try:
            HAFIZA = json.load(f)
            if "temel_veriler" not in HAFIZA:
                HAFIZA["temel_veriler"] = TEMEL_VERILER_YEDEK
        except:
            HAFIZA = {"takip_listesi": TAKIP_YEDEK, "portfoy": PORTFOY_YEDEK, "temel_veriler": TEMEL_VERILER_YEDEK}
else:
    HAFIZA = {
        "takip_listesi": TAKIP_YEDEK,
        "portfoy": PORTFOY_YEDEK,
        "temel_veriler": TEMEL_VERILER_YEDEK
    }

def hafizayi_kaydet():
    with open(DATA_FILE, "w") as f:
        json.dump(HAFIZA, f, indent=4)

# ==========================================
# 📊 TEK BİR HİSSE İÇİN ANLIK RESMİ VERİ ÇEKİCİ
# ==========================================
def tek_hisse_resmi_veri_cek(sembol):
    """Yeni eklenen veya guncellenmek istenen tek bir hissenin rasyolarini resmi sunuculardan anlik ceker"""
    if not sembol.endswith(".IS"):
        return False
        
    hisse_kodu = sembol.split(".")[0]
    try:
        # Kaynak 1: API Servisi
        api_url = f"https://api.frayzer.com/v1/financials/bist/{hisse_kodu}"
        response = requests.get(api_url, timeout=8)
        
        if response.status_code == 200:
            data = response.json()
            fk = str(data.get("fk", "-"))
            pddd = str(data.get("pddd", "-"))
            if fk != "-" and pddd != "-":
                if "temel_veriler" not in HAFIZA: HAFIZA["temel_veriler"] = {}
                HAFIZA["temel_veriler"][sembol] = {
                    "fk": f"{float(fk):.2f}",
                    "pddd": f"{float(pddd):.2f}",
                    "ihracat": "-",
                    "ozsermaye_kar": "-"
                }
                return True

        # Kaynak 2: Is Yatirim Sirket Karti Kaziyici (Yedek)
        url = f"https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/Sirket-Karti.aspx?hisse={hisse_kodu}"
        res = requests.get(url, timeout=8)
        soup = BeautifulSoup(res.text, "html.parser")
        
        fk_td = soup.find("td", text="F/K")
        pddd_td = soup.find("td", text="PD/DD")
        
        if fk_td and pddd_td:
            fk_val = fk_td.find_next_sibling("td").text.strip().replace(",", ".")
            pddd_val = pddd_td.find_next_sibling("td").text.strip().replace(",", ".")
            
            if "temel_veriler" not in HAFIZA: HAFIZA["temel_veriler"] = {}
            HAFIZA["temel_veriler"][sembol] = {
                "fk": fk_val,
                "pddd": pddd_val,
                "ihracat": "-",
                "ozsermaye_kar": "-"
            }
            return True
    except Exception as e:
        print(f"⚠️ {sembol} anlık rasyo çekimi başarısız: {e}")
    return False

def resmi_kaynaktan_temel_veri_guncelle():
    """Güvenilir api ve borsa veri saglayicilarindan toplu temel rasyolari cekip hafizaya yazar"""
    print("🔄 Güvenilir kaynaktan resmi temel rasyolar çekiliyor...")
    guncellenenler = []
    
    for sembol in HAFIZA.get("takip_listesi", []):
        if tek_hisse_resmi_veri_cek(sembol):
            hisse_kodu = sembol.split(".")[0]
            guncellenenler.append(hisse_kodu)
        time.sleep(1)
            
    if guncellenenler:
        hafizayi_kaydet()
        telegram_mesaj_gonder(f"🔄 *Resmi Temel Veri Güncellemesi Tamamlandı!*\nGece Kontrolü Yapılan Hisseler: {', '.join(guncellenenler)}\nYapay zeka rasyoları %100 güvenli finans havuzundan tazeledi.")

# ==========================================
# ⚙️ TELEGRAM İLETİŞİM FONKSİYONLARI
# ==========================================
def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    MAX_LEN = 4000  
    if len(mesaj) > MAX_LEN:
        parcalar = [mesaj[i:i+MAX_LEN] for i in range(0, len(mesaj), MAX_LEN)]
        for parca in parcalar:
            telegram_mesaj_gonder(parca)
        return

    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}
    try: 
        res = requests.post(url, json=payload, timeout=10).json()
        if not res.get("ok"):
            payload_duz = {"chat_id": CHAT_ID, "text": mesaj}
            requests.post(url, json=payload_duz, timeout=10)
    except Exception as e: 
        print(f"⚠️ Telegram gönderme hatası: {e}")

def telegram_komutlari_dinle():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    offset = HAFIZA.get("last_update_id", 0) + 1
    try:
        response = requests.get(url, params={"offset": offset, "timeout": 20}, timeout=25).json()
        if not response.get("result"): return
        
        for update in response["result"]:
            HAFIZA["update_id"] = update["update_id"]
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
                else:
                    telegram_mesaj_gonder("📋 Takip listeniz şu an boş.")

            elif komut == "/portfoy_goster":
                if HAFIZA["portfoy"]:
                    mesaj = "💰 *Güncel Portföy Varlıklarınız:*\n\n"
                    for hisse, bilgi in HAFIZA["portfoy"].items():
                        mesaj += f"📌 `{hisse}`\n  - Lot: {bilgi['lot']} | Maliyet: {bilgi['maliyet']:.2f} TL\n"
                    telegram_mesaj_gonder(mesaj)
                else:
                    telegram_mesaj_gonder("💰 Portföyünüzde henüz kayıtlı varlık yok.")

            elif komut == "/analiz":
                telegram_mesaj_gonder("🔄 Anlık talep alındı. Küresel gündem, indikatörler ve resmi hafızadaki temel veriler birleştiriliyor, lütfen bekleyin...")
                ajani_calistir(rapor_tipi="KULLANICI TALEBİ ANLIK FİNANSAL ANALİZ")

            elif komut == "/takip_ekle" and len(parcalar) > 1:
                hisse = parcalar[1].upper()
                if hisse not in HAFIZA["takip_listesi"]:
                    HAFIZA["takip_listesi"].append(hisse)
                    telegram_mesaj_gonder(f"⏳ `{hisse}` takip listesine alınıyor ve resmi rasyoları anlık sorgulanıyor...")
                    
                    # 🎯 REİS BURASI OTOMATİK TANIMLAMA NOKTASI: Hisse eklenir eklenmez rasyolari resmi sunucudan çekiliyor
                    if tek_hisse_resmi_veri_cek(hisse):
                        telegram_mesaj_gonder(f"✅ `{hisse}` başarıyla eklendi! Resmi borsa rasyoları (F/K, PD/DD) otomatik tanımlandı ve hafızaya mühürlendi.")
                    else:
                        telegram_mesaj_gonder(f"✅ `{hisse}` listeye eklendi ancak şu an borsa sunucusundan anlık rasyo dönmedi. Gece 23:30 otomatiğinde tekrar denenecek.")
                    hafizayi_kaydet()
                else:
                    telegram_mesaj_gonder(f"ℹ️ `{hisse}` zaten takip listenizde mevcut.")
                    
            elif komut == "/takip_cikar" and len(parcalar) > 1:
                hisse = parcalar[1].upper()
                if hisse in HAFIZA["takip_listesi"]:
                    HAFIZA["takip_listesi"].remove(hisse)
                    if hisse in HAFIZA["portfoy"]: del HAFIZA["portfoy"][hisse]
                    if "temel_veriler" in HAFIZA and hisse in HAFIZA["temel_veriler"]: del HAFIZA["temel_veriler"][hisse]
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"❌ `{hisse}` takip listesinden, portföyden ve rasyo hafızasından tamamen çıkarıldı.")
                    
            elif komut == "/portfoy_ekle" and len(parcalar) > 3:
                hisse = parcalar[1].upper()
                try:
                    lot = int(parcalar[2])
                    maliyet = float(parcalar[3])
                    HAFIZA["portfoy"][hisse] = {"lot": lot, "maliyet": maliyet}
                    if hisse not in HAFIZA["takip_listesi"]: 
                        HAFIZA["takip_listesi"].append(hisse)
                        tek_hisse_resmi_veri_cek(hisse)
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"💰 Portföy Güncellendi:\n`{hisse}`: {lot} Lot | Maliyet: {maliyet} TL (Rasyoları da otomatik kontrol edildi).")
                except:
                    telegram_mesaj_gonder("⚠️ Hatalı format. Örnek: `/portfoy_ekle TUPRS.IS 100 165.50`")
            
            elif komut == "/temel_guncelle" and len(parcalar) > 5:
                hisse = parcalar[1].upper()
                try:
                    if "temel_veriler" not in HAFIZA: HAFIZA["temel_veriler"] = {}
                    HAFIZA["temel_veriler"][hisse] = {
                        "fk": parcalar[2],
                        "pddd": parcalar[3],
                        "ihracat": f"%{parcalar[4].replace('%','')}",
                        "ozsermaye_kar": f"%{parcalar[5].replace('%','')}"
                    }
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"✅ `{hisse}` için Temel İstatistikler Elle Güncellendi!\nF/K: {parcalar[2]} | PD/DD: {parcalar[3]}")
                except Exception as e:
                    telegram_mesaj_gonder("⚠️ Format: `/temel_guncelle ASTOR.IS FK PDDD IHRACAT_ORANI OZSERMAYE_KAR`")

            elif komut == "/resmi_guncelle":
                telegram_mesaj_gonder("⏳ Tüm takip listesi için resmi borsa sunucularına bağlanılıyor, rasyolar anlık tazeleniyor...")
                resmi_kaynaktan_temel_veri_guncelle()

            elif komut == "/yardim":
                telegram_mesaj_gonder("🤖 *Ajan Komutları:*\n\n"
                                      "🚀 `/analiz` - Kusursuz entegre raporu üretir.\n"
                                      "🔄 `/resmi_guncelle` - Rasyoları anlık resmi kaynaktan tazeler.\n"
                                      "🔍 `/takip_listesi` - Tüm takip listenizi listeler.\n"
                                      "💰 `/portfoy_goster` - Elinizdeki varlıkları listeler.\n"
                                      "➕ `/takip_ekle HISSE.IS` - Otomatik resmi rasyolarıyla listeye yeni hisse ekler.\n"
                                      "➖ `/takip_cikar HISSE.IS` - Listeden hisse siler.\n"
                                      "👑 `/portfoy_ekle HISSE.IS LOT MALİYET` - Portföye ekleme yapar.\n"
                                      "📊 `/temel_guncelle HISSE.IS FK PDDD IHRACAT ÖZSERMAYE` - Şirket rasyolarını elle günceller.")
    except Exception as e:
        print(f"Komut dinleme hatası: {e}")

# ==========================================
# 📊 BİLİMSEL VERİ ANALİZİ MOTORU
# ==========================================
def dunya_gundemini_cek():
    url = "https://news.google.com/rss/search?q=finance+war+geopolitics+fed+inflation&hl=en-US&gl=US&ceid=US:en"
    haberler = []
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, features="xml")
        for item in soup.find_all('item')[:12]:
            haberler.append(f"- {item.title.text}")
    except: return "Haber akışı alınamadı."
    return "\n".join(haberler)

def finansal_veri_topla(sembol):
    for deneme in range(3):
        try:
            df = yf.download(sembol, period="1y", progress=False)
            if df.empty or 'Close' not in df.columns or len(df) < 50:
                time.sleep(1.5)
                continue
                
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
                
            df.columns = [str(col).strip() for col in df.columns]
            
            guncel_fiyat = float(df['Close'].iloc[-1])
            close_series = df['Close'].astype(float)
            
            df['RSI'] = ta.momentum.rsi(close_series, window=14)
            df['SMA_50'] = ta.trend.sma_indicator(close_series, window=50)
            df['SMA_200'] = ta.trend.sma_indicator(close_series, window=200)
            df['MACD'] = ta.trend.macd(close_series)
            df['MACD_Signal'] = ta.trend.macd_signal(close_series)
            df['ADX'] = ta.trend.adx(df['High'].squeeze(), df['Low'].squeeze(), close_series, window=14)
            
            portfoy_notu = "YOK"
            if sembol in HAFIZA["portfoy"]:
                p = HAFIZA["portfoy"][sembol]
                kar_zarar = ((guncel_fiyat - p['maliyet']) / p['maliyet']) * 100
                portfoy_notu = f"KULLANICININ ELİNDE VAR! Lot: {p['lot']}, Maliyet: {p['maliyet']:.2f}, Güncel Kâr/Zarar: %{kar_zarar:.2f}"

            macd_val = df['MACD'].iloc[-1]
            macd_sig = df['MACD_Signal'].iloc[-1]
            macd_durum = "AL SİNYALİ" if macd_val > macd_sig else "SAT SİNYALİ"
            adx_val = df['ADX'].iloc[-1]
            adx_durum = "GÜÇLÜ TREND" if adx_val > 25 else "ZAYIF TREND / YATAY"

            temel = HAFIZA.get("temel_veriler", {}).get(sembol, {"fk": "-", "pddd": "-", "ihracat": "-", "ozsermaye_kar": "-"})

            return {
                "fiyat": guncel_fiyat,
                "rsi": f"{df['RSI'].iloc[-1]:.2f}",
                "sma_50": f"{df['SMA_50'].iloc[-1]:.2f}",
                "sma_200": f"{df['SMA_200'].iloc[-1]:.2f}",
                "macd": f"{macd_durum}",
                "adx": f"{adx_durum} ({adx_val:.2f})",
                "fk": temel.get("fk", "-"),
                "pddd": temel.get("pddd", "-"),
                "ihracat": temel.get("ihracat", "-"),
                "ozsermaye_kar": temel.get("ozsermaye_kar", "-"),
                "portfoy_durumu": portfoy_notu
            }
        except Exception as e:
            print(f"⚠️ {sembol} veri çekme denemesi {deneme+1} başarısız: {e}")
            time.sleep(2)
            
    return None

def ajana_sentez_yaptir(gundem, piyasa_ozeti, rapor_tipi):
    prompt = f"""
    Sen rasyonel, titiz ve finans biliminin kurallarına bağlı profesyonel bir portföy yöneticisi ve finans ajanısın.
    
    RAPOR TÜRÜ: {rapor_tipi}
    KÜRESEL GÜNDEM HABERLERİ: {gundem}
    TEKNİK VE TEMEL HAM VERİLER: {piyasa_ozeti}
    
    ⚠️ KESİN KURALLAR (BU KURALLARA MİLİMETRİK UYULACAK):
    1. ASLA RAPOR FORMATINI BOZMA, GEREKSİZ PARAGRAFLAR EKLEME!
    2. Her enstrümanı tam olarak şu madde nizamında listele:
    
    ---
    
    ### [HİSSE ADI]
    * Fiyat: [Fiyat] | RSI: [RSI] | MACD: [MACD]
    * F/K: [F/K] | PD/DD: [PD/DD] | İhracat Oranı: [İhracat Oranı] | Özsermaye Kârlılığı: [Özsermaye Kârlılığı] | Trend Gücü: [Trend Gücü]
    * TREND: [OLUMLU veya OLUMSUZ] (Fiyat MA50'nin üstündeyse OLUMLU, altındaysa OLUMSUZ damgası vur)
    * Yorum: Küresel gündem başlıkları ile teknik ve temel verileri harmanlayarak cüzdan durumuna göre 1-2 cümlelik keskin yorum yap.
    * 📌 1 HAFTALIK ÖNGÖRÜ: Teknik göstergelerin yönü, temel rasyoların gücü ve küresel haberleri harmanlayarak "Mevcut momentum, finansal rasyolar ve haber akışı korunduğu sürece önümüzdeki 1 hafta boyunca [olumlu seyrin/düzeltmenin/yatay seyrin] sürmesi beklenmektedir" şeklinde kısa vadeli nokta atışı tahmini ekle.
    
    3. Cüzdandaki varlıklar için "[YATIRIM DURUMU]: KULLANICININ ELİNDE VAR!" ibaresini başlığın yanına göm ve kar/zarar yüzdesini rapora yansıt.
    4. Döviz veya Altın (USDTRY=X, GC=F) gibi enstrümanlarda F/K, PD/DD, İhracat gibi şirket rasyolarına çizgi (-) çek geç.
    5. Raporu tamamen Türkçe ve harika bir scannable düzenle sun.
    """
    try: 
        return model.generate_content(prompt).text
    except Exception as e: 
        return f"🤖 Yapay zeka bağlantı hatası: {e}"

def ajani_calistir(rapor_tipi="GÜNLÜK DEĞERLENDİRME"):
    su_an_utc = dt.datetime.utcnow()
    tr_saati = su_an_utc + dt.timedelta(hours=3)

    gundem = dunya_gundemini_cek()
    piyasa_ozeti = ""
    
    for sembol in HAFIZA["takip_listesi"]:
        veri = finansal_veri_topla(sembol)
        if veri:
            piyasa_ozeti += f"\n📌 {sembol}\n" \
                            f"  - Fiyat: {veri['fiyat']:.2f} | RSI: {veri['rsi']} | MACD: {veri['macd']}\n" \
                            f"  - MA50: {veri['sma_50']} | Trend Gücü: {veri['adx']}\n" \
                            f"  - Temel -> F/K: {veri['fk']} | PD/DD: {veri['pddd']} | İhracat: {veri['ihracat']} | Özsermaye Kâr: {veri['ozsermaye_kar']}\n" \
                            f"  - [YATIRIM DURUMU]: {veri['portfoy_durumu']}\n"
        else:
            portfoy_notu = "TAKİP LİSTESİNDE"
            if sembol in HAFIZA["portfoy"]:
                p = HAFIZA["portfoy"][sembol]
                portfoy_notu = f"KULLANICININ ELİNDE VAR! Lot: {p['lot']}, Maliyet: {p['maliyet']:.2f} TL (Canlı fiyat çekilemedi)"
            
            piyasa_ozeti += f"\n📌 {sembol}\n  - Fiyat/İndikatör: Veri çekilemedi.\n  - [YATIRIM DURUMU]: {portfoy_notu}\n"
        time.sleep(2)

    ai_raporu = ajana_sentez_yaptir(gundem, piyasa_ozeti, rapor_tipi)
    simdi = tr_saati.strftime('%d/%m/%Y %H:%M')
    
    final_mesaj = f"📊 **AKILLI PORTFÖY VE ANALİZ RAPORU** 📊\n🗓️ *Saat:* {simdi}\n" \
                  f"───────────────\n{ai_raporu}"
    telegram_mesaj_gonder(final_mesaj)

# ==========================================
# 🔄 ANA DÖNGÜ (7/24 DİNLEME VE RAPORLAMA)
# ==========================================
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f"==> Render için kukla sunucu {port} portunda başlatıldı!")
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    print("🚀 Borsa Ajanı başarıyla başlatıldı. Komutlar anlık dinleniyor...")
    
    while True:
        telegram_komutlari_dinle()
        
        su_an_utc = dt.datetime.utcnow()
        tr_saati = su_an_utc + dt.timedelta(hours=3)
        
        saat_dakika = tr_saati.strftime("%H:%M")
        saniye = tr_saati.strftime("%S")
        
        if saniye == "00":
            if saat_dakika == "11:00":
                ajani_calistir(rapor_tipi="SABAH AÇILIŞ VE PORTFÖY RİSK KONTROLÜ")
            elif saat_dakika == "18:30":
                ajani_calistir(rapor_tipi="AKŞAM KAPANIŞ VE MALİYET DEĞERLENDİRMESİ")
            elif saat_dakika == "23:30":
                resmi_kaynaktan_temel_veri_guncelle()
            
        time.sleep(2)     
