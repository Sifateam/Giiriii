#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trade Reels - Single File Project
Grok (xAI) -> Article + 5 Keywords -> Pixabay Real Videos -> Edge-TTS English -> Persian Subtitle -> 1080x1920 50s Video -> Telegram
"""
import os, sys, json, re, asyncio, subprocess, shutil
from pathlib import Path
from datetime import datetime, timezone
import requests

try:
    import edge_tts
except ImportError:
    edge_tts = None

# ---------------- CONFIG ----------------
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "").strip()
GROK_API_KEY = os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY", "")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-3-mini").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
FORCE_COUNTRY = os.getenv("FORCE_COUNTRY", "").strip()
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
VIDEO_W, VIDEO_H = 1080, 1920
VOICE = "en-US-ChristopherNeural"  # بهترین صدای رایگان انگلیسی
XFADE = 0.5

COUNTRIES = [
    {"en": "Iraq", "fa": "عراق"},
    {"en": "Oman", "fa": "عمان"},
    {"en": "Qatar", "fa": "قطر"},
    {"en": "China", "fa": "چین"},
    {"en": "Kuwait", "fa": "کویت"},
    {"en": "Georgia", "fa": "گرجستان"},
    {"en": "Armenia", "fa": "ارمنستان"},
    {"en": "Russia", "fa": "روسیه"},
]

TOPICS = [
    {"key": "import_export", "fa": "واردات، صادرات و فرهنگ تجارت", "en": "Import, Export and Trade Culture"},
    {"key": "opportunities", "fa": "فرصت‌های تجاری و تحلیل عمیق بازار و نظرات مردم", "en": "Business Opportunities, Deep Market Analysis and Public Opinions"},
    {"key": "news", "fa": "اخبار معتبر داخلی کشور هدف", "en": "Latest Valid News from Domestic Sources of Target Country"},
]

# ---------------- UTILS ----------------
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def run(cmd):
    log("RUN: " + " ".join(str(c) for c in cmd[:6]) + " ...")
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        log(r.stderr[-2000:])
        raise RuntimeError(f"Command failed: {cmd[0]}")
    return r

def get_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "json", str(path)], stdout=subprocess.PIPE, text=True)
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 10.0

def ts_ass(sec: float) -> str:
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def ts_srt(sec: float) -> str:
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = int(sec % 60); ms = int((sec % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def download_file(url, dest: Path):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
    return dest.stat().st_size

# ---------------- GROK ----------------
def call_grok(country, topic):
    if not GROK_API_KEY or DRY_RUN:
        log("Grok skipped -> fallback article")
        return fallback_data(country, topic)
    today = datetime.now().strftime("%Y-%m-%d")
    system = "You are a professional trade journalist. Return ONLY valid JSON. No markdown, no explanation."
    user = f"""
Country: {country['en']} ({country['fa']})
Topic: {topic['en']}
Date: {today}

Write a summary based on: trade culture, exports, imports, business opportunities, deep market analysis, public opinions on social media, and latest valid domestic news.
Then create a 50-second video script: total 130-150 English words, divided into EXACTLY 5 segments. Each segment 25-30 words.
Each segment must contain ONE clear keyword that will be spoken and shown on video.

Return ONLY this JSON:
{{
  "title_en": "string",
  "title_fa": "string",
  "article_en": "full 130-150 words script",
  "article_fa": "full Persian translation",
  "segments": [
    {{"en": "segment 1 english", "fa": "ترجمه فارسی بخش ۱", "keyword_en": "container port", "keyword_fa": "بندر کانتینری", "pixabay_query": "container port"}},
    {{"en": "segment 2 english", "fa": "ترجمه فارسی بخش ۲", "keyword_en": "cargo ship", "keyword_fa": "کشتی باری", "pixabay_query": "cargo ship"}},
    {{"en": "segment 3 english", "fa": "ترجمه فارسی بخش ۳", "keyword_en": "warehouse trade", "keyword_fa": "انبار تجارت", "pixabay_query": "warehouse"}},
    {{"en": "segment 4 english", "fa": "ترجمه فارسی بخش ۴", "keyword_en": "railway freight", "keyword_fa": "بار ریلی", "pixabay_query": "train cargo"}},
    {{"en": "segment 5 english", "fa": "ترجمه فارسی بخش ۵", "keyword_en": "market business", "keyword_fa": "بازار تجارت", "pixabay_query": "business market"}}
  ]
}}
Keywords queries must be simple English 2-3 words, suitable for Pixabay real stock videos.
"""
    for attempt in range(3):
        try:
            r = requests.post("https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"},
                json={"model": GROK_MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": 0.7},
                timeout=60)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            return parse_grok(text, country, topic)
        except Exception as e:
            log(f"Grok attempt {attempt+1} failed: {e}")
    return fallback_data(country, topic)

def parse_grok(text, country, topic):
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON in Grok response")
    data = json.loads(text[start:end+1])
    if len(data.get("segments", [])) != 5:
        raise ValueError("Segments != 5")
    return data

def fallback_data(country, topic):
    en, fa = country["en"], country["fa"]
    segs = [
        (f"Today we explore {en} trade culture and how local business etiquette shapes import and export deals every day.", f"امروز فرهنگ تجارت {fa} و تاثیر آداب کسب‌وکار محلی بر معاملات واردات و صادرات را بررسی می‌کنیم.", "business meeting", "جلسه کاری"),
        (f"{en} exports are growing through ports and land routes, while imports bring technology and consumer goods.", f"صادرات {fa} از طریق بنادر و مسیرهای زمینی در حال رشد است و واردات کالاهای فناوری و مصرفی می‌آورد.", "cargo ship", "کشتی باری"),
        (f"Market analysis shows strong demand in retail, construction and logistics, with positive public opinions online.", f"تحلیل بازار تقاضای قوی در خرده‌فروشی، ساخت‌وساز و لجستیک را نشان می‌دهد و نظرات مردم در فضای مجازی مثبت است.", "business market", "بازار تجارت"),
        (f"New opportunities appear in e-commerce, warehousing and cross-border trade for Iranian and foreign partners.", f"فرصت‌های جدیدی در تجارت الکترونیک، انبارداری و تجارت فرامرزی برای شرکای ایرانی و خارجی ایجاد شده است.", "warehouse", "انبار"),
        (f"Latest valid news from {en} confirms new trade agreements and faster customs clearance this month.", f"آخرین اخبار معتبر {fa} از توافق‌های تجاری جدید و ترخیص سریع‌تر گمرکی در این ماه خبر می‌دهد.", "container port", "بندر کانتینری"),
    ]
    return {
        "title_en": f"{en} Trade Insight - {topic['en']}",
        "title_fa": f"تحلیل تجارت {fa} - {topic['fa']}",
        "article_en": " ".join(s[0] for s in segs),
        "article_fa": " ".join(s[1] for s in segs),
        "segments": [{"en": s[0], "fa": s[1], "keyword_en": s[2], "keyword_fa": s[3], "pixabay_query": s[2]} for s in segs]
    }

# ---------------- PIXABAY ----------------
def pixabay_search(query):
    if not PIXABAY_API_KEY:
        return None
    for q in [query, f"{query} trade", "container port cargo ship"]:
        try:
            r = requests.get("https://pixabay.com/api/videos/", params={
                "key": PIXABAY_API_KEY, "q": q, "per_page": 10, "safesearch": "true", "order": "popular", "video_type": "film"
            }, timeout=20)
            r.raise_for_status()
            hits = r.json().get("hits", [])
            for hit in hits:
                url = None
                if "video_files" in hit and hit["video_files"]:
                    files = sorted(hit["video_files"], key=lambda x: x.get("width", 0), reverse=True)
                    url = files[0].get("link")
                elif "videos" in hit:
                    for k in ["large", "medium", "small"]:
                        if k in hit["videos"] and hit["videos"][k].get("url"):
                            url = hit["videos"][k]["url"]; break
                if url:
                    return url
        except Exception as e:
            log(f"Pixabay '{q}' failed: {e}")
    return None

def get_video_for_query(query, dest: Path):
    url = pixabay_search(query)
    if url:
        try:
            if download_file(url, dest) > 100000:
                return dest
        except Exception as e:
            log(f"Download failed: {e}")
    log(f"Pixabay fallback for {query}")
    # آخرین راه: ویدیوی گرادیان متحرک (بدون صفحه سیاه/سفید ثابت)
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"gradients=s=1080x1920:d=12:c1=0x87CEEB:c2=0x1E3A5F:speed=0.02",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(dest)])
    return dest

# ---------------- TTS ----------------
async def _tts_async(text, out):
    await edge_tts.Communicate(text, VOICE).save(str(out))

def tts_segment(text, out: Path):
    if edge_tts:
        try:
            asyncio.run(_tts_async(text, out)); return
        except Exception as e:
            log(f"TTS failed: {e}")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "10", "-c:a", "libmp3lame", str(out)])

# ---------------- FONT & SUBTITLE ----------------
def ensure_font():
    fonts = Path("fonts"); fonts.mkdir(exist_ok=True)
    dest = fonts / "Vazirmatn-Bold.ttf"
    if dest.exists() and dest.stat().st_size > 10000:
        return dest
    for url in ["https://github.com/rastikerdar/vazirmatn/raw/master/fonts/ttf/Vazirmatn-Bold.ttf",
                "https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Bold.ttf"]:
        try:
            download_file(url, dest); return dest
        except Exception:
            pass
    return None

def make_subtitles(segments, durations, ass_path: Path, srt_path: Path):
    ass, srt, cur = [], [], 0.0
    ass += ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {VIDEO_W}", f"PlayResY: {VIDEO_H}", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Vazir, Vazirmatn, 62, &H00FFFFFF, &H000019FF, &H00000000, &H66EBCE87, 1, 0, 0, 0, 100, 100, 0, 0, 3, 1, 0, 2, 40, 40, 140, 1", "",
            "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for i, (seg, dur) in enumerate(zip(segments, durations)):
        start, end = cur, cur + dur
        fa = seg["fa"].replace("{", "").replace("}", "").replace("\n", " ")
        ass.append(f"Dialogue: 0,{ts_ass(start)},{ts_ass(end)},Vazir,,0,0,0,,{fa}")
        srt += [str(i+1), f"{ts_srt(start)} --> {ts_srt(end)}", fa, ""]
        cur = end - (XFADE if i < len(segments)-1 else 0)
    ass_path.write_text("\n".join(ass), encoding="utf-8")
    srt_path.write_text("\n".join(srt), encoding="utf-8")

# ---------------- VIDEO BUILD ----------------
def build_segment(video_in, audio_in, out_path, duration):
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(video_in), "-i", str(audio_in),
         "-filter_complex", f"[0:v]scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,crop={VIDEO_W}:{VIDEO_H},setsar=1,fps=30,format=yuv420p[v];[1:a]aresample=44100,apad[a]",
         "-map", "[v]", "-map", "[a]", "-t", str(duration + 0.4), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out_path)])

def concat_xfade(parts, durations, ass_path, out_path):
    n = len(parts)
    offsets, cur = [], durations[0]
    for i in range(1, n):
        offsets.append(cur - XFADE); cur += durations[i] - XFADE
    vf, af, prev_v, prev_a = [], [], "0:v", "0:a"
    for i in range(1, n):
        ov, oa = f"vx{i}", f"ax{i}"
        vf.append(f"[{prev_v}][{i}:v]xfade=transition=fade:duration={XFADE}:offset={offsets[i-1]:.3f}[{ov}]")
        af.append(f"[{prev_a}][{i}:a]acrossfade=d={XFADE}:c1=tri:c2=tri[{oa}]")
        prev_v, prev_a = ov, oa
    inputs = []
    for p in parts: inputs += ["-i", str(p)]
    filt = ";".join(vf + af) + f";[{prev_v}]subtitles='{ass_path}':fontsdir='fonts'[vout]"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", filt, "-map", "[vout]", "-map", f"[{prev_a}]",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out_path)])
    # کنترل حجم برای تلگرام (حد 50MB)
    if out_path.stat().st_size > 45 * 1024 * 1024:
        tmp = out_path.with_suffix(".tmp.mp4")
        run(["ffmpeg", "-y", "-i", str(out_path), "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k", str(tmp)])
        tmp.replace(out_path)

# ---------------- TELEGRAM ----------------
def tg_send_video(path, caption):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or DRY_RUN:
        log("Telegram skipped (DRY_RUN or no token)"); return
    with open(path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo",
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000], "parse_mode": "HTML"},
            files={"video": f}, timeout=180)
    log(f"Telegram video: {r.status_code} {r.text[:200]}")

def tg_send_doc(path, caption):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or DRY_RUN:
        return
    with open(path, "rb") as f:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument",
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000]}, files={"document": f}, timeout=60)

# ---------------- MAIN ----------------
def pick_country_topic():
    slot_env = os.getenv("SLOT", "").strip()
    hour = datetime.now(timezone.utc).hour
    slot = int(slot_env) if slot_env.isdigit() else (0 if hour < 6 else 1 if hour < 12 else 2)
    topic = TOPICS[slot % 3]
    if FORCE_COUNTRY:
        for c in COUNTRIES:
            if FORCE_COUNTRY.lower() in [c["en"].lower(), c["fa"]]:
                return c, topic, slot
    yday = datetime.now(timezone.utc).timetuple().tm_yday
    country = COUNTRIES[(yday * 3 + slot) % len(COUNTRIES)]
    return country, topic, slot

def main():
    country, topic, slot = pick_country_topic()
    log(f"Country={country['en']} Topic={topic['key']} Slot={slot} DRY={DRY_RUN}")
    ensure_font()
    outdir = Path("output"); outdir.mkdir(exist_ok=True)
    data = call_grok(country, topic)
    log(f"Title: {data.get('title_en')}")
    (outdir / "article.txt").write_text(f"{data['title_en']}\n{data['title_fa']}\n\nEN:\n{data['article_en']}\n\nFA:\n{data['article_fa']}\n\nKeywords: " + ", ".join(s['keyword_en'] for s in data['segments']), encoding="utf-8")
    (outdir / "article.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    parts, durations = [], []
    for i, seg in enumerate(data["segments"]):
        audio = outdir / f"audio_{i}.mp3"; raw = outdir / f"raw_{i}.mp4"; part = outdir / f"part_{i}.mp4"
        tts_segment(seg["en"], audio)
        dur = get_duration(audio); durations.append(dur)
        get_video_for_query(seg.get("pixabay_query") or seg["keyword_en"], raw)
        build_segment(raw, audio, part, dur); parts.append(part)
        log(f"Segment {i+1}/5 keyword={seg['keyword_en']} dur={dur:.1f}s")

    ass, srt = outdir / "subtitle.ass", outdir / "subtitle.srt"
    make_subtitles(data["segments"], durations, ass, srt)
    final = outdir / f"{country['en'].lower()}_{topic['key']}_reel.mp4"
    concat_xfade(parts, durations, ass, final)
    log(f"FINAL: {final} size={final.stat().st_size/1024/1024:.1f}MB duration={get_duration(final):.1f}s")

    caption = f"<b>{data.get('title_fa','')}</b>\n{data.get('title_en','')}\n\nکشور: {country['fa']} | موضوع: {topic['fa']}\nکلیدواژه‌ها: " + "، ".join(s['keyword_fa'] for s in data['segments'])
    tg_send_video(final, caption)
    tg_send_doc(outdir / "article.txt", "مقاله کامل")
    tg_send_doc(srt, "زیرنویس فارسی SRT")

if __name__ == "__main__":
    main()
