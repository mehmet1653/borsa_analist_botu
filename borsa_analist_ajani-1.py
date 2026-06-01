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

# ==========================================
# 🛠️ MEHMET REİS BULUT VE HAFIZA YEDEK AYARLARI
# ==========================================
# Sunucu resetlense bile portföyün sıfırlanmaması için ana yedeğin burası:
PORTFOY_YEDEK = {
    "SASA.IS": {"lot": 1000, "maliyet": 45.50},   # Midas'taki gerçek lot ve bölünmüş ortalama maliyetini buraya yaz reis
    "KRDMB.IS": {"lot": 500, "maliyet": 22.10}    # Midas'taki gerçek lot ve bölünmüş ortalama maliyetini buraya yaz reis
}
TAKIP_YEDEK = ["THYAO.IS", "TUPRS.IS", "USDTRY=X", "GC=F", "SASA.IS", "KRDMB.IS"]

# Şifreleri doğrudan Environment Variables (Ortam Değişkenleri) üzerinden çekiyoruz
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Eğer Render şifreyi okuyamazsa veya boşluk kaldıysa diye garantiye alıyoruz
if not GEMINI_API_KEY:
    GEMINI_API_KEY = "AQ.Ab8RN6K_wraDxTNfR-qaqeJHO40gdpJLWp3o8jWYnR3IYgi7PA"

# str() ve .strip() ile şifrenin etrafındaki gizli boşlukları temizleyip metin olarak gönderiyoruz
genai.configure(api_key=str(GEMINI_API_KEY).strip())
model = genai.GenerativeModel('gemini-2.5-flash')

# Verilerin güvenle saklanacağı dosya
DATA_FILE = "ajan_hafizasi.json"

# Hafıza dosyasını yükle veya yoksa yedeklerden otomatik oluştur (Sıfırlanma Koruması)
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        try:
            HAFIZA = json.load(f)
        except:
            HAFIZA = {"takip_listesi": TAKIP_YEDEK, "portfoy": PORTFOY_YEDEK}
else:
    HAFIZA = {
        "takip_listesi": TAKIP_YEDEK,
        "portfoy": PORTFOY_YEDEK
    }

def hafizayi_kaydet():
    with open(DATA_FILE, "w") as f:
        json.dump(HAFIZA, f, indent=4)

# ==========================================
# ⚙️ TELEGRAM İLETİŞİM FONKSİYONLARI
# ==========================================
def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # --- 4096 KARAKTER SINIRI KONTROLÜ VEYA PARÇALAMA ---
    MAX_LEN = 4000  # Güvenli sınır
    if len(mesaj) > MAX_LEN:
        print(f"📦 Rapor çok uzun ({len(mesaj)} karakter). Parçalara bölünerek gönderiliyor...")
        parcalar = [mesaj[i:i+MAX_LEN] for i in range(0, len(mesaj), MAX_LEN)]
        for i, parca in enumerate(parcalar):
            print(f"📩 Parça {i+1} gönderiliyor...")
            telegram_mesaj_gonder(parca)
        return

    # Normal gönderme mantığı
    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}
    try: 
        res = requests.post(url, json=payload, timeout=10).json()
        if res.get("ok"):
            print("📡 Telegram Gönderim Durumu: True (Markdown)")
            return
            
        # Markdown hatası verirse düz metin olarak dene
        payload_duz = {"chat_id": CHAT_ID, "text": mesaj}
        res_duz = requests.post(url, json=payload_duz, timeout=10).json()
        print(f"📡 Telegram Gönderim Durumu: {res_duz.get('ok')} (Düz Metin Modu)")
    except Exception as e: 
        print(f"⚠️ Telegram gönderme hatası: {e}")

def telegram_komutlari_dinle():
    """Telegram'dan gelen komutları anlık tarar ve uygular."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    offset = HAFIZA.get("last_update_id", 0) + 1
    try:
        response = requests.get(url, params={"offset": offset, "timeout": 20}, timeout=25).json()
        if not response.get("result"): return
        
        for update in response["result"]:
            HAFIZA["last_update_id"] = update["update_id"]
            hafizayi_kaydet()
            
            message = update.get("message", {})
            text = message.get("text", "")
            chat_id = str(message.get("chat", {}).get("id", ""))
            
            if chat_id != CHAT_ID: continue # Sadece senin hesabından gelen komutları dinler
            
            parcalar = text.split()
            if not parcalar: continue
            komut = parcalar[0].lower()
            
            # --- KOMUT İŞLEME MANTIĞI ---
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
                telegram_mesaj_gonder("🔄 Anlık talep alındı. Küresel gündem ve indikatörler sentezleniyor, lütfen bekleyin...")
                ajani_calistir(rapor_tipi="KULLANICI TALEBİ ANLIK ANALİZ")

            elif komut == "/takip_ekle" and len(parcalar) > 1:
                hisse = parcalar[1].upper()
                if hisse not in HAFIZA["takip_listesi"]:
                    HAFIZA["takip_listesi"].append(hisse)
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"✅ `{hisse}` takip listesine eklendi.")
                    
            elif komut == "/takip_cikar" and len(parcalar) > 1:
                hisse = parcalar[1].upper()
                if hisse in HAFIZA["takip_listesi"]:
                    HAFIZA["takip_listesi"].remove(hisse)
                    if hisse in HAFIZA["portfoy"]: del HAFIZA["portfoy"][hisse]
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"❌ `{hisse}` takip listesinden ve portföyden çıkarıldı.")
                    
            elif komut == "/portfoy_ekle" and len(parcalar) > 3:
                hisse = parcalar[1].upper()
                try:
                    lot = int(parcalar[2])
                    maliyet = float(parcalar[3])
                    HAFIZA["portfoy"][hisse] = {"lot": lot, "maliyet": maliyet}
                    if hisse not in HAFIZA["takip_listesi"]: HAFIZA["takip_listesi"].append(hisse)
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"💰 Portföy Güncellendi:\n`{hisse}`: {lot} Lot | Maliyet: {maliyet} TL.")
                except:
                    telegram_mesaj_gonder("⚠️ Hatalı format. Örnek: `/portfoy_ekle TUPRS.IS 100 165.50`")
                    
            elif komut == "/yardim":
                telegram_mesaj_gonder("🤖 *Ajan Komutları:*\n\n"
                                      "🚀 `/analiz` - Saatleri beklemeden anlık yapay zeka raporu üretir.\n"
                                      "🔍 `/takip_listesi` - Tüm takip listenizi listeler.\n"
                                      "💰 `/portfoy_goster` - Elinizdeki varlıkları listeler.\n"
                                      "➕ `/takip_ekle HISSE.IS` - Listeye yeni hisse ekler.\n"
                                      "➖ `/takip_cikar HISSE.IS` - Listeden hisse siler.\n"
                                      "👑 `/portfoy_ekle HISSE.IS LOT MALİYET` - Portföye ekleme yapar.")
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
    try:
        # Sunucu limitine takılmamak için yfinance indirme yapısını tekli moda çektik reis
        df = yf.download(sembol, period="1y", group_by="ticker", threads=False, progress=False)
        if df.empty: return None
        
        guncel_fiyat = float(df['Close'].iloc[-1])
        
        # İndikatör hesaplamaları
        close_series = df['Close'].squeeze()
        df['RSI'] = ta.momentum.rsi(close_series, window=14)
        df['SMA_50'] = ta.trend.sma_indicator(close_series, window=50)
        df['SMA_200'] = ta.trend.sma_indicator(close_series, window=200)
        
        ticker = yf.Ticker(sembol)
        info = ticker.info
        
        portfoy_notu = "YOK"
        if sembol in HAFIZA["portfoy"]:
            p = HAFIZA["portfoy"][sembol]
            kar_zarar = ((guncel_fiyat - p['maliyet']) / p['maliyet']) * 100
            portfoy_notu = f"KULLANICININ ELİNDE VAR! Lot: {p['lot']}, Maliyet: {p['maliyet']:.2f}, Güncel Kâr/Zarar: %{kar_zarar:.2f}"

        return {
            "fiyat": guncel_fiyat,
            "rsi": f"{df['RSI'].iloc[-1]:.2f}",
            "sma_50": f"{df['SMA_50'].iloc[-1]:.2f}",
            "sma_200": f"{df['SMA_200'].iloc[-1]:.2f}",
            "fk": info.get('trailingPE', 'Veri Yok'),
            "pddd": info.get('priceToBook', 'Veri Yok'),
            "portfoy_durumu": portfoy_notu
        }
    except Exception as e:
        print(f"⚠️ {sembol} veri toplama hatası: {e}")
        return None

def ajana_sentez_yaptir(gundem, piyasa_ozeti, rapor_tipi):
    prompt = f"""
    Sen rasyonel, titiz ve finans biliminin kurallarına bağlı pratik bir finans ajanısın.
    
    RAPOR TÜRÜ: {rapor_tipi}
    KÜRESEL GÜNDEM: {gundem}
    VERİLER VE PORTFÖY BİLGİSİ: {piyasa_ozeti}
    
    ⚠️ KESİN KURALLAR (BU KURALLARA MİLİMETRİK UYMAK ZORUNDASIN):
    1. ASLA UZUN VE SIKICI METİNLER YAZMA! Genel geçer, yuvarlak cümleler kurarak acemice yorumlar yapma. Sadede gel, net ol.
    2. Her bir enstrümanı (SASA, KRDMB, THYAO vb.) başlıklar halinde ayır. Güncel fiyatını ve RSI değerini net olarak yaz.
    3. Teknik verilere ve hareketli ortalamalara bakarak her hissenin trend yönünü açıkça "TREND: OLUMLU" veya "TREND: OLUMSUZ" şeklinde damgala.
    4. Kullanıcının elindeki hisselerin adını geçirerek küresel risklerin bu şirketlere olası etkisini 1-2 cümleyle doğrudan ve keskin yorumla.
    5. Raporu kısa, vurucu, tek bakışta ne olduğunu anlatan askeri bir disiplinle Türkçe sun.
    """
    try: 
        return model.generate_content(prompt).text
    except Exception as e: 
        print(f"🔄 Birincil model hatası, yedek çağrılıyor... Hata: {e}")
        try:
            # 404 hatası veren o eski sinsi "-latest" model adını buradan sildik reis! Ana modele eşitledik.
            alternatif_model = genai.GenerativeModel('gemini-2.5-flash')
            return alternatif_model.generate_content(prompt).text
        except Exception as ex:
            return f"🤖 Yapay zeka bağlantı hatası: {ex}"

def ajani_calistir(rapor_tipi="GÜNLÜK DEĞERLENDİRME"):
    print(f"🔄 [{rapor_tipi}] başlatıldı. Canlı veriler analiz ediliyor, lütfen bekleyin...")
    gundem = dunya_gundemini_cek()
    piyasa_ozeti = ""
    
    for sembol in HAFIZA["takip_listesi"]:
        veri = finansal_veri_topla(sembol)
        if veri:
            piyasa_ozeti += f"\n📌 {sembol}\n" \
                            f"  - Fiyat: {veri['fiyat']:.2f} | RSI: {veri['rsi']}\n" \
                            f"  - MA50: {veri['sma_50']} | MA200: {veri['sma_200']}\n" \
                            f"  - [YATIRIM DURUMU]: {veri['portfoy_durumu']}\n"
        else:
            portfoy_notu = "TAKİP LİSTESİNDE"
            if sembol in HAFIZA["portfoy"]:
                p = HAFIZA["portfoy"][sembol]
                portfoy_notu = f"KULLANICININ ELİNDE VAR! Lot: {p['lot']}, Maliyet: {p['maliyet']:.2f} TL (Canlı fiyat çekilemedi)"
            
            piyasa_ozeti += f"\n📌 {sembol}\n  - Fiyat/İndikatör: Veri çekilemedi veya piyasa kapalı.\n  - [YATIRIM DURUMU]: {portfoy_notu}\n"
        time.sleep(1) # Sunucu koruma gecikmesi

    ai_raporu = ajana_sentez_yaptir(gundem, piyasa_ozeti, rapor_tipi)
    simdi = datetime.now().strftime('%d/%m/%Y %H:%M')
    
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
    # Sahte sunucuyu arka planda başlatıp Render'ı ayakta tutuyoruz
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    print("🚀 Borsa Ajanı başarıyla başlatıldı. Komutlar anlık dinleniyor...")
    telegram_mesaj_gonder("🤖 *Borsa Analist Ajanı Render Üzerinde Aktif!* \n\nYeni komutları test etmek için hemen `/yardim` yazabilirsiniz.")
    
    # Başlangıç test analizi
    ajani_calistir(rapor_tipi="ANLIK BAĞLANTI VE SİSTEM TESTİ")
    
    while True:
        telegram_komutlari_dinle()
        
        su_an = datetime.now().strftime("%H:%M:%S")
        if su_an == "11:00:00":
            ajani_calistir(rapor_tipi="SABAH AÇILIŞ VE PORTFÖY RİSK KONTROLÜ")
        elif su_an == "18:30:00":
            ajani_calistir(rapor_tipi="AKŞAM KAPANIŞ VE MALİYET DEĞERLENDİRMESİ")
            
        time.sleep(1)
