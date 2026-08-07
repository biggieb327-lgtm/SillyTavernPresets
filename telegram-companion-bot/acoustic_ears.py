# Vendored from menelly/AI_Ears (https://github.com/menelly/AI_Ears, MIT license) --
# analyze_acoustic() and its key-detection helpers, unmodified. This is the offline half only:
# pure NumPy FFT analysis of a WAV file, no network calls. The STT/voice-profile half of that
# project (Inworld/ElevenLabs/local-Whisper transcription) is intentionally NOT included here --
# bot.py already transcribes voice notes via its own NanoGPT call; this module only adds a read
# on *how* a voice note sounded (pace, tone, pauses) alongside that existing transcript.

import wave
import numpy as np

KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def read_wav_mono(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    return x, sr


def analyze_acoustic(wav_path):
    x, sr = read_wav_mono(wav_path)
    dur = len(x) / sr
    if len(x) == 0:
        return {"error": "empty audio"}

    win, hop = 2048, 512
    n_frames = max(1, 1 + (len(x) - win) // hop) if len(x) >= win else 1
    frames = np.zeros((n_frames, win))
    for i in range(n_frames):
        seg = x[i * hop:i * hop + win]
        frames[i, :len(seg)] = seg
    window = np.hanning(win)
    spec = np.abs(np.fft.rfft(frames * window, axis=1))
    freqs = np.fft.rfftfreq(win, 1 / sr)

    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    rms_db = 20 * np.log10(rms + 1e-9)

    mag = spec + 1e-9
    centroid = float(np.sum(freqs * mag.mean(axis=0)) / np.sum(mag.mean(axis=0)))
    bright_label = ("very bright" if centroid > 4000 else "bright" if centroid > 2500
                    else "warm" if centroid > 1200 else "dark")

    peak = float(np.max(np.abs(x)))
    peak_dbfs = 20 * np.log10(peak + 1e-9)
    rms_overall = float(np.sqrt(np.mean(x ** 2)))
    crest = 20 * np.log10((peak + 1e-9) / (rms_overall + 1e-9))
    voiced = rms_db[rms_db > (rms_db.max() - 60)]
    if voiced.size < 4:
        voiced = rms_db
    loud = float(np.percentile(voiced, 95))
    quiet = float(np.percentile(voiced, 5))
    dyn_range = loud - quiet
    dyn_label = ("very dynamic" if dyn_range > 25 else "dynamic" if dyn_range > 14
                 else "even" if dyn_range > 7 else "flat/compressed")

    chroma = np.zeros(12)
    avg_mag = mag.mean(axis=0)
    for f, m in zip(freqs, avg_mag):
        if f < 55 or f > 5000:
            continue
        midi = 69 + 12 * np.log2(f / 440.0)
        pc = int(round(midi)) % 12
        chroma[pc] += m
    chroma = chroma / (chroma.sum() + 1e-9)
    best = (-2, None, None)
    for shift in range(12):
        cr = np.roll(chroma, -shift)
        maj = np.corrcoef(cr, KS_MAJOR)[0, 1]
        minr = np.corrcoef(cr, KS_MINOR)[0, 1]
        if maj > best[0]:
            best = (maj, NOTES[shift], "major")
        if minr > best[0]:
            best = (minr, NOTES[shift], "minor")
    key_conf, key_root, key_mode = best

    flux = np.maximum(0, np.diff(spec, axis=0)).sum(axis=1)
    tempo_bpm = None
    if len(flux) > 8:
        flux = flux - flux.mean()
        ac = np.correlate(flux, flux, mode="full")[len(flux) - 1:]
        fps = sr / hop
        lo, hi = int(fps * 60 / 240), int(fps * 60 / 50)
        if hi < len(ac) and hi > lo:
            lag = lo + int(np.argmax(ac[lo:hi]))
            if lag > 0:
                tempo_bpm = 60.0 * fps / lag

    thresh = np.percentile(rms_db, 30)
    floor = max(thresh, quiet + 6)
    quiet_mask = rms_db < floor
    events = []
    i = 0
    while i < len(quiet_mask):
        if quiet_mask[i]:
            j = i
            while j < len(quiet_mask) and quiet_mask[j]:
                j += 1
            t0, t1 = i * hop / sr, j * hop / sr
            if (t1 - t0) >= 0.18 and t0 > 0.05 and t1 < dur - 0.05:
                events.append((round(t0, 2), round(t1, 2), round(t1 - t0, 2)))
            i = j
        else:
            i += 1
    events.sort(key=lambda e: -e[2])

    return {
        "duration_s": round(dur, 2),
        "sample_rate": sr,
        "brightness_hz": round(centroid),
        "brightness_label": bright_label,
        "key": f"{key_root} {key_mode}" if key_root else "unclear",
        "key_confidence": round(float(key_conf), 2),
        "tempo_bpm": round(tempo_bpm, 1) if tempo_bpm else None,
        "peak_dbfs": round(peak_dbfs, 1),
        "crest_db": round(float(crest), 1),
        "loud_dbfs": round(loud, 1),
        "quiet_dbfs": round(quiet, 1),
        "dynamic_range_db": round(dyn_range, 1),
        "dynamics_label": dyn_label,
        "pauses": events[:6],
    }


def describe_acoustic(a, word_count=None):
    """Translate an analyze_acoustic() dict into a short natural-language note for a prompt."""
    if not a or "error" in a:
        return None
    bits = []
    if word_count and a.get("duration_s"):
        bits.append(f"~{round(word_count / (a['duration_s'] / 60))} wpm")
    bits.append(f"{a['dynamics_label']} volume")
    bits.append(f"{a['brightness_label']} tone")
    if a.get("pauses"):
        bits.append(f"{len(a['pauses'])} notable pause(s)")
    return ", ".join(bits)
