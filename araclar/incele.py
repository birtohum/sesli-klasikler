"""Bir hikâyenin ilk dakikasını Whisper'a okutup asıl metinle yan yana basar (WER incelemesi)."""
import io, json, subprocess, sys, wave
from pathlib import Path
import imageio_ffmpeg
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import uret

ad = sys.argv[1]
d = json.loads((uret.CIKTI / ad / "metin.json").read_text(encoding="utf-8"))
ham = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(uret.CIKTI / ad / "ses.mp3"), "-f", "s16le", "-ac", "1", "-ar", "22050", "-"],
                     capture_output=True, check=True).stdout
pcm = np.frombuffer(ham, dtype=np.int16)
son = max(c["s"] for s in d["paragraflar"] for c in s if c["s"] <= 60)
ilk = " ".join(c["t"] for s in d["paragraflar"] for c in s if c["s"] <= son)
h = uret.whisper(pcm, 22050, son + 0.1)
print("METİN  :", ilk)
print("WHISPER:", h)
print(uret.wer(ilk, h))
