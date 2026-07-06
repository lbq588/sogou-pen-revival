# sogou-pen-revival

讓搜狗錄音筆在雲端服務關閉後復活：用本地 faster-whisper 取代已停運的雲端轉寫。

> **English**: Sogou (搜狗) smart recording pens lost their core speech-to-text
> feature when the cloud transcription service shut down on **2024-05-30**.
> This tool revives the pen by transcribing its recordings locally with
> [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — no cloud, no
> account, fully offline.

## 背景

搜狗錄音筆（C1 / C1 Pro 等）的語音轉文字依賴搜狗雲端服務，該服務已於
**2024-05-30 關閉**。筆本身仍能正常錄音，且以 USB 隨身碟形式掛載，
錄音檔可直接讀取——缺的只是轉寫。本工具補上這一塊，全程本地執行。

## 功能

- **自動偵測錄音筆磁碟機**：掃描 `Guide.txt` + `RECORD/` 內容特徵，
  不寫死磁碟機代號（多硬碟環境下代號會漂移）
- **增量轉寫**：已處理清單記在 `_processed.json`，重複執行只轉新錄音
- **Markdown 輸出**：帶時間戳與 YAML frontmatter，可直接放進 Obsidian 等筆記軟體
- **完全離線**：faster-whisper 本地推論，錄音不離開你的電腦

## 安裝

```bash
pip install faster-whisper
```

## 使用

把錄音筆插上電腦後：

```bash
python transcribe_pen.py                    # 轉寫筆上所有新錄音到 ./transcripts
python transcribe_pen.py --limit 1          # 只轉最舊的 1 段（測試用）
python transcribe_pen.py --output D:/notes  # 指定輸出資料夾
python transcribe_pen.py --model small      # 換模型（快但辨識率較低）
python transcribe_pen.py --language zh      # 指定語言（預設 zh）
python transcribe_pen.py --archive          # 轉寫並複製 WAV 備份
```

首次執行會自動下載 Whisper 模型（`medium` 約 1.5 GB）。CPU 推論速度
約為錄音長度的 1/2 ~ 1x（視硬體而定）；追求速度可改用 `--model small`。

## 筆內檔案格式（逆向筆記）

錄音筆掛載後的磁碟結構：

| 路徑 | 內容 |
| --- | --- |
| `RECORD/<YYYYMMDD>/<HH_MM_SS>.WAV` | 試聽錄音，**16 kHz / 16 bit / mono**，可直接餵 ASR |
| `RECORD/.../*.AVO` | 原始錄音，搜狗私有格式，原本供雲端轉寫用（未逆向，見下） |
| `MICTEST.PCM` | 出廠麥克風測試檔，raw PCM（16 kHz / 16 bit / mono，無檔頭） |
| `Guide.txt` | 出廠說明（含序號，勿公開） |
| `Log/app.log` | 韌體日誌（藍牙握手、重置紀錄等） |
| `STAT/*.DAT` | 使用統計 |

本工具轉寫 `WAV`。`AVO` 為私有格式尚未逆向；若同一段錄音同時有 WAV 與
AVO，WAV 已足夠轉寫使用。

## 限制

- 僅在 **C1 Pro** 上實測；其他搜狗筆型號若磁碟結構相同（`Guide.txt` +
  `RECORD/`）應可直接使用，歡迎回報
- `AVO` 原始格式未支援
- Windows 開發測試；macOS/Linux 理論上可用（磁碟偵測邏輯掃描代號
  A–Z，非 Windows 環境需把筆的掛載點直接放進 `candidates`），歡迎 PR

## License

MIT
