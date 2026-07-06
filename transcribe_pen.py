"""
transcribe_pen.py — 搜狗錄音筆（C1/C1 Pro 等）本地轉寫工具

搜狗雲端轉寫服務已於 2024-05-30 關閉，錄音筆的核心功能（語音轉文字）隨之失效。
此腳本用本地 faster-whisper 取代雲端轉寫，讓筆「復活」：

  1. 自動偵測錄音筆磁碟機（掃描 Guide.txt + RECORD/ 內容特徵，
     不寫死磁碟機代號——代號在多硬碟環境下會漂移）
  2. 找出尚未轉寫的 WAV（筆內格式為 16kHz/16bit/mono，可直接餵 ASR）
  3. faster-whisper 本地轉寫（帶時間戳），輸出 Markdown（含 YAML frontmatter，
     可直接放進 Obsidian 等筆記軟體）
  4. 已處理清單記在輸出資料夾的 _processed.json，重複執行只做新檔案

用法：
  python transcribe_pen.py                          # 轉寫筆上所有新錄音
  python transcribe_pen.py --limit 1                # 只轉最舊的 1 段（測試用）
  python transcribe_pen.py --output D:/my/notes     # 指定輸出資料夾
  python transcribe_pen.py --model small            # 換模型（快但辨識率較低）
  python transcribe_pen.py --language zh            # 指定語言
  python transcribe_pen.py --archive                # 轉寫並複製 WAV 備份

需求：pip install faster-whisper
"""

import argparse
import json
import string
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def find_pen_drive() -> Path | None:
    """用內容特徵找錄音筆，不依賴磁碟機代號。
    本腳本若放在筆的根目錄執行，優先用自己所在的磁碟機。"""
    self_root = Path(__file__).resolve().anchor  # 例 F:\
    candidates = [Path(self_root)] + [
        Path(f"{letter}:/") for letter in string.ascii_uppercase
    ]
    for root in candidates:
        try:
            if (root / "Guide.txt").exists() and (root / "RECORD").is_dir():
                return root
        except OSError:
            continue
    return None


def load_processed(processed_file: Path) -> set:
    if processed_file.exists():
        return set(json.loads(processed_file.read_text(encoding="utf-8")))
    return set()


def save_processed(processed_file: Path, done: set):
    processed_file.write_text(
        json.dumps(sorted(done), ensure_ascii=False, indent=1), encoding="utf-8"
    )


def recording_key(wav: Path) -> str:
    return f"{wav.parent.name}/{wav.name}"          # 例 20211123/09_46_25.WAV


def transcribe(model, wav: Path, language: str) -> tuple[str, float]:
    segments, info = model.transcribe(
        str(wav), language=language, beam_size=5, vad_filter=True,
    )
    lines = []
    for seg in segments:
        m, s = divmod(int(seg.start), 60)
        lines.append(f"- `{m:02d}:{s:02d}` {seg.text.strip()}")
    return "\n".join(lines), info.duration


def main():
    ap = argparse.ArgumentParser(description="搜狗錄音筆本地轉寫工具")
    ap.add_argument("--output", type=Path, default=Path("transcripts"),
                    help="轉寫結果輸出資料夾（預設 ./transcripts）")
    ap.add_argument("--model", default="medium",
                    help="faster-whisper 模型大小（預設 medium）")
    ap.add_argument("--language", default="zh", help="語言代碼（預設 zh）")
    ap.add_argument("--limit", type=int, default=0, help="最多處理幾段（0=全部）")
    ap.add_argument("--archive", action="store_true",
                    help="同時複製 WAV 到輸出資料夾備份")
    args = ap.parse_args()

    pen = find_pen_drive()
    if not pen:
        print("找不到錄音筆（掃描所有磁碟機，無 Guide.txt + RECORD/ 特徵），請確認已插上")
        sys.exit(1)
    print(f"錄音筆：{pen}")

    processed_file = args.output / "_processed.json"
    done = load_processed(processed_file)
    wavs = sorted(pen.glob("RECORD/*/*.WAV"))
    todo = [w for w in wavs if recording_key(w) not in done]
    print(f"筆上共 {len(wavs)} 段錄音，待轉寫 {len(todo)} 段")
    if not todo:
        return
    if args.limit:
        todo = todo[: args.limit]

    args.output.mkdir(parents=True, exist_ok=True)
    print(f"載入 faster-whisper（{args.model}，首次會下載模型）...")
    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device="cpu", compute_type="int8")

    for wav in todo:
        date_s = wav.parent.name                     # 20211123
        time_s = wav.stem.replace("_", ":")          # 09:46:25
        title = f"{date_s[:4]}-{date_s[4:6]}-{date_s[6:]} {wav.stem.replace('_', '-')}"
        print(f"轉寫 {recording_key(wav)} ...", flush=True)
        t0 = time.time()
        try:
            body, dur = transcribe(model, wav, args.language)
        except Exception as e:
            print(f"  失敗：{e}")
            continue
        md = args.output / f"{title}.md"
        md.write_text(
            f"---\nsource: 搜狗錄音筆 {recording_key(wav)}\n"
            f"recorded: {date_s[:4]}-{date_s[4:6]}-{date_s[6:]} {time_s}\n"
            f"duration_sec: {dur:.0f}\n"
            f"transcribed: {datetime.now():%Y-%m-%d %H:%M}\n"
            f"model: faster-whisper {args.model}\n---\n\n{body}\n",
            encoding="utf-8",
        )
        if args.archive:
            dst = args.output / "audio" / date_s
            dst.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(wav, dst / wav.name)
        done.add(recording_key(wav))
        save_processed(processed_file, done)
        print(f"  完成（音檔 {dur:.0f}s / 花費 {time.time()-t0:.0f}s）→ {md.name}")

    print("全部完成")


if __name__ == "__main__":
    main()
