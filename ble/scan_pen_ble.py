"""
scan_pen_ble.py — Phase 2 第一步：唯讀掃描搜狗錄音筆的 BLE GATT 佈局。

目的（對應 results/protocol_ble_timesync.md「待實機驗證」）：
  1. 掃描附近 BLE 廣播，定位錄音筆（名稱含 搜狗/Sogou/录音/C1）
  2. 連線後列舉所有 GATT service / characteristic（UUID + properties）
  3. 比對 UUID 表自動判定裝置走 C1 / C2 / TR2 哪套協定
  4. 找出對時用的 charSyncTime、SN 相關 characteristic 候選

**全程唯讀**：只 discover + connect + 讀 service 結構，不對筆寫入任何位元組。

用法：
  python scan_pen_ble.py                 # 掃描並自動連線最像錄音筆的裝置
  python scan_pen_ble.py --scan-only     # 只列出附近所有 BLE 裝置，不連線
  python scan_pen_ble.py --address <MAC>  # 直接連指定位址（掃描列出後用）
  python scan_pen_ble.py --timeout 15     # 調整掃描秒數（預設 12）
"""
import argparse
import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bleak import BleakScanner, BleakClient

# 錄音筆廣播名稱可能包含的關鍵字（大小寫不敏感）
NAME_HINTS = ("sogou", "搜狗", "录音", "錄音", "recorder", "c1", "teemo")

# 來自 APK 反組譯（protocol_ble_timesync.md）的 UUID 判別表
SVC_MAIN = "00001910"                       # 主自訂 service（三代共用）
C1_ONLY = ("0000cc68", "0000dd68", "0000b001", "0000b002", "0000b003",
           "0000d001", "0000d003", "0000d005", "0000d007", "0000d009", "0000d00a")
C2_CHARS = ("00002bb0", "00002bb1")


def short_uuid(u: str) -> str:
    """把 128-bit 標準基底 UUID 縮成 16-bit 短碼，方便比對。"""
    u = u.lower()
    if u.endswith("-0000-1000-8000-00805f9b34fb"):
        return u.split("-")[0]              # 0000xxxx
    return u


def looks_like_pen(name: str | None, adv_uuids) -> bool:
    if name:
        low = name.lower()
        if any(h in low for h in NAME_HINTS):
            return True
    for u in (adv_uuids or []):
        if short_uuid(u).startswith("00001910"):
            return True
    return False


async def scan(timeout: float):
    print(f"掃描 BLE 廣播中（{timeout:.0f}s）...\n")
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    rows = []
    for addr, (dev, adv) in found.items():
        name = adv.local_name or dev.name
        rows.append((addr, name, adv.rssi, list(adv.service_uuids or [])))
    rows.sort(key=lambda r: (r[2] is None, -(r[2] or -999)))  # RSSI 強的在前
    print(f"共發現 {len(rows)} 個 BLE 裝置：\n")
    candidates = []
    for addr, name, rssi, uuids in rows:
        pen = looks_like_pen(name, uuids)
        mark = "  <== 疑似錄音筆" if pen else ""
        print(f"  {addr}  RSSI={rssi}  name={name!r}{mark}")
        if uuids:
            print(f"      廣播 service UUIDs: {[short_uuid(u) for u in uuids]}")
        if pen:
            candidates.append((addr, name))
    return candidates


def classify(char_shorts: set[str]) -> str:
    if any(c in char_shorts for c in C1_ONLY):
        return "C1（偵測到 C1 專屬 characteristic）"
    if all(c in char_shorts for c in C2_CHARS):
        return "C2（僅見 2bb0/2bb1，無 C1 專屬 characteristic）"
    return "未定（未匹配到已知 C1/C2 特徵，可能是 TR2 或佈局有異）"


async def inspect(address: str):
    print(f"\n連線 {address} ...")
    async with BleakClient(address, timeout=20.0) as client:
        print(f"已連線：{client.is_connected}\n")
        print("=== GATT service / characteristic 列舉（唯讀）===\n")
        all_char_shorts: set[str] = set()
        sync_time_candidates = []
        for svc in client.services:
            print(f"[service] {short_uuid(svc.uuid)}  ({svc.uuid})")
            for ch in svc.characteristics:
                sc = short_uuid(ch.uuid)
                all_char_shorts.add(sc)
                props = ",".join(ch.properties)
                print(f"    [char] {sc}  props={props}")
                # 對時 characteristic 通常具 write 屬性且在主 service 下
                if short_uuid(svc.uuid).startswith("00001910") and (
                    "write" in ch.properties or "write-without-response" in ch.properties
                ):
                    sync_time_candidates.append(sc)
        print("\n=== 判定 ===")
        print(f"協定分類：{classify(all_char_shorts)}")
        print(f"主 service 下可寫 characteristic（對時/指令候選）：{sorted(set(sync_time_candidates))}")
        print(f"全部 characteristic 短碼：{sorted(all_char_shorts)}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-only", action="store_true")
    ap.add_argument("--address", default=None)
    ap.add_argument("--timeout", type=float, default=12.0)
    args = ap.parse_args()

    if args.address:
        await inspect(args.address)
        return

    candidates = await scan(args.timeout)
    if args.scan_only:
        return
    if not candidates:
        print("\n未自動辨識出錄音筆。請確認筆在配對模式（長按 5 秒藍燈閃），"
              "或從上面清單挑位址用 --address <MAC> 手動連線。")
        return
    if len(candidates) > 1:
        print(f"\n發現多個疑似裝置：{candidates}\n請用 --address 指定其一。")
        return
    addr, name = candidates[0]
    print(f"\n自動選定：{name!r} @ {addr}")
    await inspect(addr)


if __name__ == "__main__":
    asyncio.run(main())
