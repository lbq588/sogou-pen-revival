"""
probe_state_ble.py — 診斷探針：送唯讀查詢指令，判斷 0x2bb1/0x2bb0 通道回應行為。

目的：對時封包送出後收到 0 筆 notify。用「一定會有回應」的唯讀查詢當探針，
區分兩種情況：
  - 查詢有 notify 回應 → 通道正常，對時應已被收下（可能 fire-and-forget）
  - 查詢也無回應       → 筆要求先握手，或 notify 未真正訂閱成功

只送非破壞查詢：APP_GET_STATE_REQ(value=3)、APP_BATT_STATUS_REQ(value=9)、
APP_GET_STORAGE_VOLUME(value=6)。絕不送 depair(5)/factory-reset(102)/對時以外的寫入。
"""
import asyncio, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHAR_CMD = "00002bb1-0000-1000-8000-00805f9b34fb"
CHAR_NTF = "00002bb0-0000-1000-8000-00805f9b34fb"
NAME_HINT = "搜狗"

def cmd(value: int, payload: bytes = b"") -> bytes:
    return bytes([0x01]) + struct.pack("<H", value) + payload

PROBES = [("APP_GET_STATE_REQ", cmd(3)),
          ("APP_BATT_STATUS_REQ", cmd(9)),
          ("APP_GET_STORAGE_VOLUME", cmd(6))]

async def main():
    from bleak import BleakScanner, BleakClient
    found = await BleakScanner.discover(timeout=12.0, return_adv=True)
    addr = None
    for a, (dev, adv) in found.items():
        nm = adv.local_name or dev.name or ""
        if NAME_HINT in nm or "C1 Pro" in nm:
            addr = a; print(f"找到：{nm!r} @ {a}"); break
    if not addr:
        print("找不到錄音筆（確認在配對模式）"); return

    got = []
    def on_ntf(_c, data):
        got.append(bytes(data)); print(f"    ← notify: {bytes(data).hex(' ')}")

    async with BleakClient(addr, timeout=20.0) as client:
        print(f"已連線：{client.is_connected}")
        await client.start_notify(CHAR_NTF, on_ntf)
        print("已訂閱 0x2bb0\n")
        for name, packet in PROBES:
            before = len(got)
            print(f"送 {name}: {packet.hex(' ')}")
            try:
                await client.write_gatt_char(CHAR_CMD, packet, response=False)
            except Exception as e:
                print(f"    寫入失敗：{e}")
            await asyncio.sleep(2.5)
            if len(got) == before:
                print("    （無回應）")
        await client.stop_notify(CHAR_NTF)
    print(f"\n總計 notify 回應 {len(got)} 筆。")
    if got:
        print("→ 通道正常會回應：對時封包應已被筆收下（fire-and-forget 可能已生效）")
    else:
        print("→ 所有查詢皆無回應：筆要求先握手，下一步走「握手→對時」")

if __name__ == "__main__":
    asyncio.run(main())
