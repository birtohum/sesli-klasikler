"""Uzun eserleri (roman) kısımlara bölüp seslendirir. Hikâyelerle aynı biçim: site/kitap/<kisim>/ses.mp3 + metin.json
ve site/kitap/romanlar.json (eser → kısımlar).

Kürk Mantolu Madonna: Vikikaynak'ta 1943 Remzi Kitabevi ilk baskısının taranmış sayfalarından yazılmış metin
(Sabahattin Ali 1948'de öldü; 5846 sayılı FSEK md. 27'ye göre eser 2019'dan beri kamu malı).
Bölüm başlığı yok: ilk kısım anlatıcının hikâyesi, defter "20 Haziran 1933." ile başlar; defter paragraf
sınırlarından yaklaşık eşit kısımlara bölünür.

    piperenv/Scripts/python araclar/roman.py [--whisper]
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import uret  # noqa: E402

ESERLER = [{
    "ad": "kurk-mantolu-madonna", "baslik": "Kürk Mantolu Madonna", "yazar": "Sabahattin Ali", "yil": 1943,
    "sayfa": "Kürk Mantolu Madonna", "atla": 8, "kirilma": "20 Haziran 1933.", "kisim_karakter": 30000,
    "tanitim": "Ankara'da bir bürodaki silik memur Raif Efendi'nin defterinden çıkan, 1920'lerin Berlin'inde bir ressamla yaşanmış bir aşk.",
}]


def html_al(sayfa):
    u = "https://tr.wikisource.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "parse", "page": sayfa, "prop": "text|revid", "format": "json"})
    for _ in range(6):
        try:
            d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=uret.UA), timeout=120))["parse"]
            return d["text"]["*"], d.get("revid")
        except urllib.error.HTTPError as h:
            if h.code != 429:
                raise
            time.sleep(30)
    raise RuntimeError("Vikikaynak cevap vermedi")


def paragraflar(h):
    a, b = h.index('class="prp-pages-output"'), h.index("licenseContainer")
    g = re.sub(r'<span[^>]*class="[^"]*pagenum[^"]*"[^>]*>.*?</span>', "", h[a:b], flags=re.S)
    g = re.sub(r"<(sup|ref)[^>]*>.*?</\1>", "", g, flags=re.S)
    out = []
    for p in re.split(r"</p>|<br\s*/?>|</div>", g):
        p = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", p)).replace("­", "")).strip()
        if p and not p.startswith('class="') and p != '<div class="':
            out.append(p)
    return out


DUZELT = {"Simdiye kadar": "Şimdiye kadar", "başladım.İkinciteşrin": "başladım. İkinciteşrin"}


def _esit(par, hedef):
    toplam = sum(len(p) for p in par)
    n = max(1, round(toplam / hedef))
    hedef = toplam / n
    out, simdi, boy = [], [], 0
    for p in par:
        simdi.append(p); boy += len(p)
        # kısım cümle ortasında ya da iki noktayla (konuşma girişi) bitmesin
        if boy >= hedef and len(out) < n - 1 and not p.rstrip().endswith(":"):
            out.append(simdi); simdi, boy = [], 0
    return out + ([simdi] if simdi else [])


def bol(par, eser):
    """Anlatıcının bölümü ve defter ayrı ayrı, yaklaşık eşit kısımlara bölünür."""
    par = list(par)
    for i, p in enumerate(par):
        for a, b in DUZELT.items():
            par[i] = par[i].replace(a, b)
    k = par.index(eser["kirilma"])
    return _esit(par[eser["atla"]:k], eser["kisim_karakter"]) + _esit(par[k:], eser["kisim_karakter"])


def seslendir(ses, paragraflar_, hedef_klasor, baslik, yazar, kaynak, olcum):
    hz = ses.config.sample_rate
    parcalar, zaman, cikti = [], 0.0, []
    for p in paragraflar_:
        satir = []
        for c in uret.cumlelere(p):
            pcm, hz = uret.oku(ses, c)
            b = zaman
            parcalar.append(pcm); zaman += len(pcm) / hz
            satir.append({"t": c, "b": round(b, 2), "s": round(zaman, 2)})
            parcalar.append(np.zeros(int(hz * uret.CUMLE_ARA), dtype=np.int16)); zaman += uret.CUMLE_ARA
        if satir:
            cikti.append(satir)
            ek = uret.PARAGRAF_ARA - uret.CUMLE_ARA
            parcalar.append(np.zeros(int(hz * ek), dtype=np.int16)); zaman += ek
    pcm = np.concatenate(parcalar)
    hedef_klasor.mkdir(parents=True, exist_ok=True)
    uret.mp3(pcm, hz, hedef_klasor / "ses.mp3")
    sure = round(len(pcm) / hz, 1)
    (hedef_klasor / "metin.json").write_text(json.dumps({"baslik": baslik, "yazar": yazar, "kaynak": kaynak, "sure": sure,
                                                         "paragraflar": cikti}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kayit = {"ad": hedef_klasor.name, "baslik": baslik, "sure": sure,
             "kelime": sum(len(uret.kelimeler(c["t"])) for s in cikti for c in s),
             "ilk": cikti[0][0]["t"][:140] if cikti else ""}
    if olcum:
        son = max(c["s"] for s in cikti for c in s if c["s"] <= 60)
        ilk = " ".join(c["t"] for s in cikti for c in s if c["s"] <= son)
        h, n = uret.wer(ilk, uret.whisper(pcm, hz, son + 0.1))
        kayit["wer"] = {"hata": h, "kelime": n}
    return kayit


def main():
    olcum = "--whisper" in sys.argv
    from piper import PiperVoice
    ses = PiperVoice.load(str(uret.MODEL))
    romanlar = []
    for e in ESERLER:
        h, revid = html_al(e["sayfa"])
        kaynak = f"https://tr.wikisource.org/w/index.php?oldid={revid}"
        kisimlar = bol(paragraflar(h), e)
        liste = []
        for i, kp in enumerate(kisimlar, 1):
            t = time.time()
            k = seslendir(ses, kp, uret.CIKTI / f"{e['ad']}-{i:02d}", f"{e['baslik']} · {i}. kısım", e["yazar"], kaynak, olcum)
            k["no"] = i
            liste.append(k)
            print(f"{e['baslik']} {i}/{len(kisimlar)}: {k['sure'] / 60:.1f} dk" + (f", WER {k['wer']['hata']}/{k['wer']['kelime']}" if "wer" in k else "")
                  + f" ({time.time() - t:.0f} sn)", flush=True)
        r = {k: e[k] for k in ("ad", "baslik", "yazar", "yil", "tanitim")} | {"kaynak": kaynak, "kisimlar": liste,
                                                                             "sure": round(sum(k["sure"] for k in liste), 1)}
        if olcum:
            r["wer"] = {"hata": sum(k["wer"]["hata"] for k in liste), "kelime": sum(k["wer"]["kelime"] for k in liste)}
        romanlar.append(r)
    (uret.CIKTI / "romanlar.json").write_text(json.dumps(romanlar, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
