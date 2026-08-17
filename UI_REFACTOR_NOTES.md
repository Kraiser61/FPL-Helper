# FPL Helper — UI/UX Refaktör Notları

## Kapsam

Bu iterasyonda matematiksel karar motoru, veri tabanı şeması ve ingestion sözleşmeleri korunarak PySide6 arayüz katmanı geliştirildi. Değişiklikler ağırlıklı olarak `ui/` altında yapıldı; uygulama başlangıcını engelleyen güvenli credential store fallback'i ve Quick Stats için ViewModel veri alanları ayrıca düzeltildi.

## Öne çıkan geliştirmeler

| Alan | Uygulanan geliştirme |
|---|---|
| Tema | Cam hissi veren yarı saydam yüzey token'ları, yeni analitik/canlı veri vurgu renkleri, hover/pressed mikro-etkileşimleri |
| Ana pencere | Sayfa geçişlerinde `QPropertyAnimation` fade efekti, daha belirgin canlı veri durum etiketi ve motor durumu |
| Dashboard | İkonlu KPI kartları, hover yüzeyleri ve editoryal `Smart Brief` paneli |
| Kadro | Taktik saha gradyanı, kompakt spor kartı görünümü, rol/kaptan/kilit rozetleri ve oyuncu tıklama akışı |
| Quick Stats | xP, xG, xA, FDR, form, sahiplik, fiyat ve bonus/BPS modal özeti; mevcut oyuncu sözleşmesinden güvenli fallback'ler |
| Transfer | Düşük/yüksek risk senaryoları, transfer in/out versus kartı ve altı katmanlı accordion gerekçeleri |
| FDR | Yuvarlatılmış hücreler, yumuşatılmış hover vurgusu, büyüyen metin hissi ve açıklayıcı tooltip'ler |
| Dayanıklılık | Keyring backend bulunmayan ortamlarda ayarlar ve uygulama başlangıcının çökmesini önleyen güvenli fallback |

## Korunan mimari kararlar

`core/` ve `data/` iş mantığı değiştirilmedi. UI, mevcut ViewModel sinyallerini ve `DecisionBundle` veri akışını tüketmeye devam ediyor. Transfer gerekçeleri için mevcut bundle alanlarından türetilen sunum katmanı kullanıldı; optimizasyon modeli veya amaç fonksiyonuna müdahale edilmedi.

## Doğrulama

Aşağıdaki kontroller başarıyla tamamlandı:

1. `python3 -m compileall -q .`
2. Offscreen import/widget smoke test: tema, ana pencere, dashboard, saha, FDR ve fixture bileşenleri.
3. Gelişmiş UI smoke test: TransferView, altı accordion paneli, Quick Stats modalı ve sekme fade animasyonu.
4. Ayarlar/keyring fallback smoke test.
5. `QT_QPA_PLATFORM=offscreen timeout 12s python3 main.py`: uygulama başlatıldı, veriler arka planda işlendi ve son çalıştırma logunda `CRITICAL`, `Traceback`, `AttributeError`, `TypeError` veya `Segmentation` hatası görülmedi. Test, ağ çağrılarının tamamlanmasını beklemek üzere zaman aşımıyla sonlandırılmıştır; kimlik doğrulama yapılmadığında beklenen uyarılar loglanmıştır.

## Çalıştırma

```bash
cd "FPL Helper"
pip install -r requirements.txt
python main.py
```

FPL hesabı kimlik bilgileri yalnızca uygulamanın Ayarlar ekranından girilmelidir. Kaynak koda veya teslim arşivine parola, token ya da cookie eklenmemelidir.
