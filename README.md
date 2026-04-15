# SpeedZone Data — Windows Kurulum Rehberi

Bu klasör, SpeedZonePro iOS app'inin kullandığı hız koridoru verilerini toplayan Python scraper'ını içeriyor. Scraper YolRadar.com'daki 200 güzergah sayfasını gezer, koridorları çıkarır, Nominatim ile koordinatlara çevirir ve `zones.json` üretir. Dosya GitHub Pages'e push edilir, iOS app oradan çeker.

## Tek seferlik kurulum (ilk kurulum, 20-30 dakika)

### 1. Python kur

**Windows Store'dan kurmak en kolay:**
1. Başlat menüsüne `Microsoft Store` yaz ve aç
2. Arama kutusuna `Python 3.12` yaz
3. İlk sonuca (Python Software Foundation yapımı) tıkla → **Get** / **Al** butonuna bas
4. Kurulum bitince Windows terminalini aç (Başlat → `cmd`) ve test et:
   ```
   python --version
   ```
   `Python 3.12.x` gibi bir çıktı görmelisin.

**Alternatif:** https://www.python.org/downloads/windows/ adresinden indirebilirsin. Installer'ı açtığında **"Add Python to PATH"** kutucuğunu **mutlaka işaretle**, sonra "Install Now" tıkla.

### 2. Git kur

1. https://git-scm.com/download/win adresine git
2. İndirmeyi başlat (otomatik başlar)
3. Installer'ı çalıştır. Tüm seçenekleri **varsayılan** bırak, sadece Next Next Next...
4. Kurulum bitince terminalde test et:
   ```
   git --version
   ```
   `git version 2.xx.x.windows.x` gibi bir çıktı görmelisin.

### 3. GitHub hesabı aç (zaten varsa atla)

https://github.com/signup adresinden ücretsiz hesap aç. E-posta doğrulamayı tamamla.

### 4. Yeni repo oluştur

1. https://github.com/new adresine git
2. **Repository name**: `speedzone-data`
3. **Public** seç (Private'da GitHub Pages sınırlı, sen public yap)
4. Hiçbir şey ekleme (README, .gitignore, license tümü boş kalsın)
5. **Create repository** butonuna bas
6. Açılan sayfada URL'yi göreceksin, örn: `https://github.com/kullaniciadin/speedzone-data.git` — **bunu not al**

### 5. Bu klasörü Git ile bağla

Windows terminalini aç, bu klasöre git:
```
cd C:\yolun\SpeedZoneData
```

(Eğer klasör Downloads altındaysa `cd %USERPROFILE%\Downloads\SpeedZoneData` gibi bir şey olur.)

Şu komutları sırayla çalıştır (örnek URL'yi kendi URL'inle değiştir):
```
git init
git branch -M main
git remote add origin https://github.com/kullaniciadin/speedzone-data.git
git add .
git commit -m "Initial setup"
git push -u origin main
```

İlk push'ta GitHub kullanıcı adı ve şifre/token isteyebilir. Git Credential Manager açılırsa tarayıcıdan GitHub'a giriş yap, onaylayıp kapat — bir daha sormaz.

### 6. GitHub Pages'i aç

1. GitHub'da repo sayfana git (`https://github.com/kullaniciadin/speedzone-data`)
2. Üstten **Settings** sekmesine tıkla
3. Sol menüden **Pages** seç
4. **Source** bölümünde: **Deploy from a branch** seçili
5. **Branch**: `main`, folder: `/ (root)`
6. **Save**
7. 2-3 dakika bekle. Sayfa yenileyince üstte yeşil bir kutuda şu URL'yi göreceksin:
   ```
   https://kullaniciadin.github.io/speedzone-data/
   ```
   **Bu URL'yi not al**, iOS app'e koyacaksın.

### 7. Scraper'ı ilk kez çalıştır

`run-scraper.bat` dosyasına **çift tıkla**.

Siyah bir pencere açılır. İçinde:
- `[setup] Checking Python packages...` → pip ile paketler kurulur
- `[1/3] Discovering routes from https://yolradar.com/radar-noktalari/` → index çekilir
- `[2/3] Scraping 200 route pages` → her sayfa çekilir (her biri yarım saniye)
- `[3/3] Geocoding 300 corridors via Nominatim` → her koridor için 2 geocoding istek (saniyede 1)
- `[git] Committing and pushing to GitHub...` → otomatik push

**İlk çalıştırmada 15-30 dakika sürer** çünkü 600+ geocoding isteği yapılıyor ve Nominatim saniyede 1 istek kabul ediyor.

Sonraki çalıştırmalarda `geocode-cache.json` sayesinde sadece **yeni** koridorlar geocode edilir — 3-5 dakika.

Pencerede `Done. Wrote N zones to zones.json` çıktısını gördüğünde iş bitmiştir.

### 8. Doğrulama

Tarayıcını aç, şu URL'yi ziyaret et:
```
https://kullaniciadin.github.io/speedzone-data/zones.json
```

JSON formatında bir çıktı görmelisin:
```json
{
  "version": "2026-04-14",
  "generated_at": "2026-04-14T19:55:00+00:00",
  "source": "yolradar.com + Nominatim (OSM) geocoding",
  "count": 234,
  "zones": [
    {
      "id": "yr-pursaklar-baglantisi-batikent-cikisi",
      "name": "Pursaklar Bağlantısı - Batıkent Çıkışı",
      "entryLat": 40.0345,
      "entryLon": 32.8423,
      "exitLat": 39.9651,
      "exitLon": 32.7311,
      "lengthMeters": 17000,
      "speedLimitKph": 130
    },
    ...
  ]
}
```

Eğer bu gözükürse **kurulum başarılı**. iOS app artık bu URL'den veri çekebilir.

---

## Periyodik kullanım (ayda bir, 5 dakika)

1. `run-scraper.bat` dosyasına çift tıkla
2. Bekle (3-5 dakika, çoğunlukla cache kullanılır)
3. Pencere `Done.` yazdığında kapan
4. Hepsi bu kadar. iOS app kullanıcıları bir sonraki açılışta güncel veriyi otomatik çeker.

---

## iOS app tarafında ne yapman gerek

Bu kısım iOS projesinde. `YolRadarLoader.swift`'te bir constant var:
```swift
private static let feedURL = URL(string: "https://BURAYI_KENDI_URLIN_ILE_DEGISTIR.github.io/speedzone-data/zones.json")!
```

Bu satırı kendi GitHub Pages URL'inle değiştir. Sonra build et.

---

## Sorun giderme

### "python: command not found" (cmd penceresinde)
Python PATH'e eklenmemiş. Python'u Microsoft Store'dan kurduysan terminali kapat aç, veya bilgisayarı yeniden başlat. Python.org'dan kurduysan ve "Add to PATH" işaretini atladıysan, Python'u kaldırıp yeniden kur.

### "git: command not found"
Git kurulmamış veya PATH'te değil. git-scm.com'dan tekrar kurmayı dene.

### Scraper çok yavaş
İlk çalıştırma için normal — 600+ Nominatim isteği var, saniyede 1 yapılabiliyor. 15-30 dakika bekle, bir daha ilk kez sürmeyecek.

### YolRadar sayfası değişti, scraper çalışmıyor
`parse_route_page` fonksiyonunda HTML pattern'ı güncellenmesi gerek. Hata mesajını yapıştırırsan parser'ı düzeltirim.

### GitHub push hatası "permission denied"
İlk push'ta GitHub auth lazım. Windows'ta Git Credential Manager otomatik tarayıcı açar. Açılmazsa: https://github.com/settings/tokens → **Generate new token** → scope'lardan `repo` işaretli → token'ı kopyala → git push'ta şifre yerine bu token'ı yapıştır.

### `zones.json` boş çıkıyor
`--no-geocode` flag'iyle test et: `python scraper.py --no-geocode` → scraper kısmı çalışıyor mu? Çalışıyorsa Nominatim bloke etmiş olabilir, 1 saat bekle tekrar dene.

### Nominatim "403 Forbidden" veya "429 Too Many Requests"
User-Agent'ı fark ettiler veya rate limit'i aştın. `scraper.py` içinde `NOMINATIM_DELAY_SEC` değerini 1.1'den 2.0'a çıkar.
