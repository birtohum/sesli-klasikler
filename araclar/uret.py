"""Vikikaynak'tan telifi düşmüş hikâyeleri alır, Piper ile seslendirir, cümle zamanlarıyla birlikte yazar.

Çıktı (site/kitap/<kisa-ad>/):
  ses.mp3      tek parça okuma (mono, 40 kbps)
  metin.json   {"baslik", "kaynak", "sure", "paragraflar": [[{"t": cümle, "b": başlangıç sn, "s": bitiş sn}, ...], ...]}
ve site/kitap/liste.json (tüm hikâyeler, süre, anlaşılırlık ölçümü).

Anlaşılırlık: her hikâyenin ilk ~60 saniyesi Whisper (Groq) ile geri yazıya çevrilir, kelime hata oranı (WER)
ölçülür. Ses modeli: Piper tr_TR-dfki-medium (CC BY-NC-SA 4.0, MaryTTS DFKI verisi).

    piperenv/Scripts/python araclar/uret.py [--whisper]
"""
from __future__ import annotations

import html
import io
import json
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from piper import PiperVoice

sys.stdout.reconfigure(encoding="utf-8")
KOK = Path(__file__).resolve().parent.parent
CIKTI = KOK / "site" / "kitap"
MODEL = KOK / "araclar" / "tr_TR-dfki-medium.onnx"
UA = {"User-Agent": "sesli-klasikler/0.1 (github.com/birtohum/sesli-klasikler)"}
YAZAR = "Ömer Seyfettin"
HIKAYELER = ["Kaşağı", "Forsa", "Yüksek Ökçeler", "Kurumuş Ağaçlar", "And", "Diyet", "Pembe İncili Kaftan", "Topuz",
             "Başını Vermeyen Şehit", "Perili Köşk", "Kurbağa Duası", "Üç Nasihat", "Niçin Zengin Olmamış?", "Tos",
             "Teke Tek", "Bir Kayışın Tesiri", "Çakmak", "Külah"]
CUMLE_ARA, PARAGRAF_ARA = 0.35, 0.8  # saniye


def kisa_ad(s):
    s = s.replace("ı", "i").replace("İ", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def wikitext(baslik):
    u = "https://tr.wikisource.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "parse", "page": baslik, "prop": "wikitext|revid", "format": "json", "redirects": 1})
    d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60))["parse"]
    return d["wikitext"]["*"], d.get("revid")


def temizle(wt):
    wt = re.sub(r"<ref[^>]*?/>|<ref.*?</ref>", "", wt, flags=re.S)
    wt = re.sub(r"\{\{[^{}]*\}\}", "", wt)
    wt = re.sub(r"\[\[(?:Kategori|Category|Dosya|File):[^\]]*\]\]", "", wt)
    wt = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", wt)
    wt = re.sub(r"'{2,}", "", wt)
    wt = re.sub(r"<[^>]+>", "", wt)
    # Bazı Vikikaynak sayfalarına eklenmiş dilbilgisi notları: "görmediğim(-me,isim fiil)"
    wt = re.sub(r"\(-[^()]*?(?:fiil|isim|sıfat|zarf)[^()]*\)", "", wt)
    wt = html.unescape(wt.replace("&mdash;", "—"))
    paragraflar = []
    for satir in wt.splitlines():
        satir = re.sub(r"^[:*#]+\s*", "", satir.strip())
        if not satir or re.fullmatch(r"=+.*=+", satir) or re.fullmatch(r"[—\-–.\s]+", satir):
            continue
        satir = re.sub(r"\s+", " ", satir)
        paragraflar.append(satir)
    return paragraflar


BOL = re.compile(r"(?<=[.!?…])[\"'”»]?\s+(?=[—\-–\"'“«(]?[A-ZÇĞİÖŞÜÂÎÛ0-9])")


def cumlelere(p):
    return [c.strip() for c in BOL.split(p) if re.search(r"\w", c)]


def oku(ses, metin):
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as w:
        ses.synthesize_wav(metin, w)
    tampon.seek(0)
    with wave.open(tampon) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate()


def mp3(pcm, hz, hedef):
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(hz), "-ac", "1", "-i", "-",
                    "-c:a", "libmp3lame", "-b:a", "40k", "-ar", "22050", str(hedef)], input=pcm.tobytes(), check=True)


def whisper(pcm, hz, sn=60.0):
    """İlk sn saniyeyi Whisper'a gönderir, yazıya çevrilmiş metni döndürür."""
    anahtar = next(s.split("=", 1)[1].strip().strip('"') for s in open(Path.home() / ".pflow-anahtarlar.env", encoding="utf-8")
                   if s.startswith("GROQ_API_KEY="))
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(hz); w.writeframes(pcm[: int(hz * sn)].tobytes())
    sinir = "----sk" + str(int(time.time()))
    govde = (f"--{sinir}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-large-v3\r\n"
             f"--{sinir}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\ntr\r\n"
             f"--{sinir}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n").encode() \
        + tampon.getvalue() + f"\r\n--{sinir}--\r\n".encode()
    r = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", data=govde, headers={
        "Authorization": "Bearer " + anahtar, "Content-Type": f"multipart/form-data; boundary={sinir}", "User-Agent": UA["User-Agent"]})
    for deneme in range(4):
        try:
            return json.load(urllib.request.urlopen(r, timeout=120))["text"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and deneme < 3:
                time.sleep(20); continue
            raise


def kelimeler(s):
    return re.findall(r"\w+", s.replace("İ", "i").replace("I", "ı").lower())


def wer(referans, hipotez):
    a, b = kelimeler(referans), kelimeler(hipotez)
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        o, d[0] = d[0], i
        for j, y in enumerate(b, 1):
            o, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, o + (x != y))
    return d[-1], len(a)


def hikaye(ses, baslik, olcum):
    wt, revid = wikitext(baslik)
    paragraflar = temizle(wt)
    hz = ses.config.sample_rate
    parcalar, zaman, cikti = [], 0.0, []
    for pi, p in enumerate(paragraflar):
        satir = []
        for c in cumlelere(p):
            pcm, hz = oku(ses, c)
            b = zaman
            parcalar.append(pcm); zaman += len(pcm) / hz
            satir.append({"t": c, "b": round(b, 2), "s": round(zaman, 2)})
            ara = CUMLE_ARA
            parcalar.append(np.zeros(int(hz * ara), dtype=np.int16)); zaman += ara
        if satir:
            cikti.append(satir)
            parcalar.append(np.zeros(int(hz * (PARAGRAF_ARA - CUMLE_ARA)), dtype=np.int16)); zaman += PARAGRAF_ARA - CUMLE_ARA
    pcm = np.concatenate(parcalar)
    ad = kisa_ad(baslik)
    hedef = CIKTI / ad
    hedef.mkdir(parents=True, exist_ok=True)
    mp3(pcm, hz, hedef / "ses.mp3")
    kaynak = f"https://tr.wikisource.org/w/index.php?oldid={revid}" if revid else "https://tr.wikisource.org/wiki/" + urllib.parse.quote(baslik)
    sure = round(len(pcm) / hz, 1)
    (hedef / "metin.json").write_text(json.dumps({"baslik": baslik, "yazar": YAZAR, "kaynak": kaynak, "sure": sure,
                                                  "paragraflar": cikti}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kayit = {"ad": ad, "baslik": baslik, "sure": sure, "kelime": sum(len(kelimeler(c["t"])) for s in cikti for c in s)}
    if olcum:
        # Karşılaştırma tam cümlelerle: ses, 60. saniyeden önce biten son cümlenin sonunda kesilir
        son = max(c["s"] for s in cikti for c in s if c["s"] <= 60)
        ilk = " ".join(c["t"] for s in cikti for c in s if c["s"] <= son)
        h, n = wer(ilk, whisper(pcm, hz, son + 0.1))
        kayit["wer"] = {"hata": h, "kelime": n}
    return kayit


def main():
    olcum = "--whisper" in sys.argv
    ses = PiperVoice.load(str(MODEL))
    liste = []
    for b in HIKAYELER:
        t = time.time()
        k = hikaye(ses, b, olcum)
        liste.append(k)
        print(f"{b}: {k['sure'] / 60:.1f} dk, {k['kelime']} kelime" + (f", WER {k['wer']['hata']}/{k['wer']['kelime']}" if "wer" in k else "")
              + f" ({time.time() - t:.0f} sn)", flush=True)
    toplam = {"yazar": YAZAR, "ses": "Piper tr_TR-dfki-medium", "hikayeler": liste}
    if olcum:
        h = sum(k["wer"]["hata"] for k in liste); n = sum(k["wer"]["kelime"] for k in liste)
        toplam["wer"] = {"hata": h, "kelime": n}
        print(f"toplam WER {h}/{n} = {h / n:.3f}")
    (CIKTI / "liste.json").write_text(json.dumps(toplam, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
