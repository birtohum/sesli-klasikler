# Sesli Klasikler

**Dinle:** https://birtohum.github.io/sesli-klasikler/

Ömer Seyfettin'in 18 hikâyesi, ücretsiz sesli kitap (yaklaşık 4,4 saat). Dinlerken okunan cümle metinde vurgulanır, bir cümleye dokununca oradan devam eder, kaldığın yer hatırlanır.

## Nasıl üretildi

`araclar/uret.py`:
1. Metin [Vikikaynak](https://tr.wikisource.org/)'tan API ile alınır, viki işaretlerinden temizlenir. Ömer Seyfettin 1920'de öldü; eserleri kamu malı. Her hikâyenin `metin.json` dosyasında alındığı sürümün kalıcı bağlantısı var.
2. Her cümle [Piper](https://github.com/rhasspy/piper) ile ayrı ayrı seslendirilir (`tr_TR-dfki-medium`). Cümle başlangıç/bitiş zamanları kaydedilir; site vurgulamayı bunlarla yapar.
3. **Anlaşılırlık ölçümü:** her hikâyenin ilk dakikası Whisper large-v3 (Groq) ile geri yazıya çevrilir ve asıl metne göre kelime hata oranı (WER) hesaplanır. 18 hikâyede toplam **%11,2** (209/1863 kelime). Modern dilli hikâyelerde %3–4; “guzzât, ikdâm, cevânib-i erbaa” gibi eski kelimelerin yoğun olduğu hikâyelerde daha yüksek. Bu hataların bir kısmı Whisper'ın, yani ölçüm bir üst sınır.

Ölçüm iki sorun yakaladı ve düzeltildi: Vikikaynak'taki “And” metnine eklenmiş dilbilgisi notları (“görmediğim(-me,isim fiil)”) sesle okunuyordu; ilk ölçüm penceresi cümle sınırına hizalı olmadığı için WER'i olduğundan yüksek gösteriyordu.

Seçim: okul çağına uygun, iyi bilinen hikâyeler. Etnik düşmanlık ya da yetişkin içeriği öne çıkan hikâyeler alınmadı.

```bash
pip install piper-tts imageio-ffmpeg numpy
# ses modeli: huggingface.co/rhasspy/piper-voices  tr/tr_TR/dfki/medium  → araclar/
python araclar/uret.py --whisper     # GROQ_API_KEY gerekir (yalnız ölçüm için)
```

## Lisans

- Kod: MIT.
- Ses kayıtları: ses modeli DFKI'nin [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) lisanslı verisiyle eğitildiği için kayıtlar da **CC BY-NC-SA 4.0**: atıf vererek, ticari olmayan amaçla ve aynı lisansla paylaşılabilir.
- Metinler: kamu malı (Vikikaynak).
