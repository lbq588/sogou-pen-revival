"""
set_time_ble.py — Phase 2 試寫：透過 BLE 對搜狗 C1 Pro（C2 協定）本地對時。

依 results/protocol_ble_timesync.md 定死的封包：
    對時封包 = 01 04 00 <4-byte LE unix 秒>
    寫入 characteristic 0x2bb1（write-without-response）
    回應   訂閱 characteristic 0x2bb0（notify）

**安全設計**：預設 dry-run，只組封包並印出、連都不連，不對筆寫入任何位元組。
加 --commit 才會真的連線、訂閱 notify、送出對時封包（第一次對筆寫入）。
本腳本只送「對時」(value=4) 這個非破壞性指令，絕不送 depair(5)/factory-reset(102)。

用法：
  python set_time_ble.py                          # dry-run：印出將送出的封包，不連線
  python set_time_ble.py --commit                 # 實際連線並送對時封包
  python set_time_ble.py --commit --address <MAC>  # 指定裝置位址
"""
import argparse
import asyncio
import struct
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHAR_CMD = "00002bb1-0000-1000-8000-00805f9b34fb"     # App→筆 指令通道（write）
CHAR_NTF = "00002bb0-0000-1000-8000-00805f9b34fb"     # 筆→App 回應通道（notify）
NAME_HINT = "搜狗"


def build_time_sync_packet(unix_sec: int) -> bytes:
    """01 04 00 + 4-byte LE unix 秒。type=1, value=4(APP_TIME_SYNC_REQ)。"""
    header = bytes([0x01]) + struct.pack("<H", 4)      # type=1, value=4 (LE uint16)
    payload = struct.pack("<I", unix_sec)              # 4-byte LE unix 秒
    return header + payload


async def find_address() -> str | None:
    from bleak import BleakScanner
    found = await BleakScanner.discover(timeout=12.0, return_adv=True)
    for addr, (dev, adv) in found.items():
        name = adv.local_name or dev.name or ""
        if NAME_HINT in name or "Sogou" in name or "C1 Pro" in name:
            print(f"找到裝置：{name!r} @ {addr}")
            return addr
    return None


async def commit(address: str | None):
    from bleak import BleakClient
    if not address:
        address = await find_address()
    if not address:
        print("找不到錄音筆，請確認在配對模式，或用 --address 指定。")
        return

    now = int(time.time())
    packet = build_time_sync_packet(now)
    print(f"對時目標：{now}（{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}）")
    print(f"封包：{packet.hex(' ')}")

    responses = []

    def on_notify(_char, data: bytearray):
        responses.append(bytes(data))
        print(f"  ← notify 0x2bb0: {bytes(data).hex(' ')}")

    async with BleakClient(address, timeout=20.0) as client:
        print(f"已連線：{client.is_connected}")
        await client.start_notify(CHAR_NTF, on_notify)
        print(f"已訂閱 0x2bb0，送出對時封包到 0x2bb1 ...")
        await client.write_gatt_char(CHAR_CMD, packet, response=False)
        await asyncio.sleep(3.0)                        # 等筆回應
        await client.stop_notify(CHAR_NTF)
    print(f"\n完成。收到 {len(responses)} 筆 notify 回應。")
    print("下一步：拔下筆按 REC 錄一段，插回電腦看 RECORD/ 是否出現正確日期的新錄音"
          "（若日期正確 → 對時生效；仍是 1970/19700101 → 需先握手或時間戳單位不同）。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="實際連線並寫入（否則僅 dry-run）")
    ap.add_argument("--address", default=None)
    args = ap.parse_args()

    now = int(time.time())
    packet = build_time_sync_packet(now)
    print("=== 對時封包（dry-run 預覽）===")
    print(f"unix 秒：{now}")
    print(f"封包 hex：{packet.hex(' ')}")
    print(f"  type=0x01, value=0x0004(LE), timestamp={now}(4B LE)")
    print(f"寫入 characteristic：{CHAR_CMD}")
    print(f"回應 characteristic：{CHAR_NTF}\n")

    if not args.commit:
        print("dry-run 結束（未連線、未寫入）。加 --commit 才會實際送出。")
        return
    asyncio.run(commit(args.address))


if __name__ == "__main__":
    main()
