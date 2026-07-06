"""
handshake_time_ble.py — 送握手 → 對時，拿筆的實際回應。

依 results/protocol_ble_timesync.md + sendFirstHandshake 反組譯：
  握手封包 = 01 01 00 | 02 03 00 | token
             type=1,value=1(APP_HANDSHAKE_REQ); a=2,b=3,c=0; token = MD5(sgUnionId)[:16] 的 UTF-8 bytes
  對時封包 = 01 04 00 | <4-byte LE unix 秒>

sgUnionId 預設空字串（WiFi 層證實 App 支援空 user 握手）。可用 --sgunionid 指定。
只送握手(1)與對時(4)兩個非破壞指令，絕不送 depair(5)/factory-reset(102)。
"""
import argparse, asyncio, hashlib, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHAR_CMD = "00002bb1-0000-1000-8000-00805f9b34fb"
CHAR_NTF = "00002bb0-0000-1000-8000-00805f9b34fb"
NAME_HINT = "搜狗"


def gen_token(sg_union_id: str) -> bytes:
    """genHandshakeToken: MD5(sgUnionId) 十六進位字串前 16 字元，再取 UTF-8 bytes。"""
    md5_hex = hashlib.md5(sg_union_id.encode("utf-8")).hexdigest()   # 32 hex chars
    return md5_hex[:16].encode("utf-8")                              # 16 bytes


def handshake_packet(sg_union_id: str) -> bytes:
    header = bytes([0x01]) + struct.pack("<H", 1)                    # type=1, value=1
    body = bytes([2, 3, 0]) + gen_token(sg_union_id)                # a=2,b=3,c=0,token
    return header + body


def time_packet(unix_sec: int) -> bytes:
    return bytes([0x01]) + struct.pack("<H", 4) + struct.pack("<I", unix_sec)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sgunionid", default="", help="搜狗帳號 union id（預設空字串）")
    ap.add_argument("--address", default=None)
    args = ap.parse_args()

    from bleak import BleakScanner, BleakClient
    addr = args.address
    if not addr:
        found = await BleakScanner.discover(timeout=12.0, return_adv=True)
        for a, (dev, adv) in found.items():
            nm = adv.local_name or dev.name or ""
            if NAME_HINT in nm or "C1 Pro" in nm:
                addr = a; print(f"找到：{nm!r} @ {a}"); break
    if not addr:
        print("找不到錄音筆（確認在配對模式）"); return

    hs = handshake_packet(args.sgunionid)
    now = int(time.time())
    tp = time_packet(now)
    print(f"握手封包：{hs.hex(' ')}  (sgUnionId={args.sgunionid!r}, token={gen_token(args.sgunionid).decode()})")
    print(f"對時封包：{tp.hex(' ')}  (unix={now} {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))})\n")

    got = []
    def on_ntf(_c, data):
        got.append(bytes(data)); print(f"    ← notify: {bytes(data).hex(' ')}")

    async with BleakClient(addr, timeout=20.0) as client:
        print(f"已連線：{client.is_connected}")
        await client.start_notify(CHAR_NTF, on_ntf)
        print("已訂閱 0x2bb0\n")

        print("送握手 ...")
        await client.write_gatt_char(CHAR_CMD, hs, response=False)
        await asyncio.sleep(3.0)
        hs_resp = len(got)
        print(f"  握手後收到 {hs_resp} 筆回應\n")

        print("送對時 ...")
        await client.write_gatt_char(CHAR_CMD, tp, response=False)
        await asyncio.sleep(3.0)
        print(f"  對時後累計 {len(got)} 筆回應\n")

        await client.stop_notify(CHAR_NTF)

    print(f"總計 notify {len(got)} 筆：{[b.hex(' ') for b in got]}")
    if got:
        print("→ 通道開始回應：握手已被筆受理，協定重建成功的強證據")
    else:
        print("→ 仍無回應：token 可能需真實 sgUnionId，或握手另有前置（需再分析）")


if __name__ == "__main__":
    asyncio.run(main())
