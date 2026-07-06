# 搜狗 C1 Pro 錄音筆 BLE 協定（社群逆向筆記）

> 本文件為互通性逆向工程的成果整理，供其他同樣受影響的用戶參考。分析對象為原廠
> App（已於 2024-05-30 停止服務），方法為 Dalvik bytecode 靜態反組譯 + `bleak` 實機驗證。
> **本文只描述協定理解（UUID、封包格式、演算法），不含原廠任何二進位檔或程式碼。**
> 文中裝置 MAC、SSN 等個別裝置識別值以佔位符呈現，請替換為你自己裝置掃描到的值。

## 為什麼需要這個

搜狗錄音筆（C2 協定機種，如 C1 Pro）的 WiFi 快傳與雲端轉寫依賴原廠 App 與伺服器。
伺服器關閉後，筆的 BLE 指令通道仍在，但缺少 App 就無法對時、無法觸發傳輸。本文記錄
如何用 PC + BLE 直接跟筆對話，全程不需要任何搜狗伺服器或帳號。

## 裝置分代

原廠 App 內分 C1 / C2 / TR2 三套協定。C1 Pro 經實機掃描判定走 **C2 協定**。判別方式：
掃描筆的 GATT，若主 service 底下只有 `0x2bb0`/`0x2bb1` 兩個 characteristic 即為 C2；
若另有 `0xb00x`/`0xd00x`/`0xcc68`/`0xdd68` 則為 C1（封包格式不同，本文不涵蓋）。

## GATT 佈局（C2，實機確認）

| service | characteristic | properties | 角色 |
| --- | --- | --- | --- |
| `0x1800` Generic Access | `2a00` | read,write | 標準 |
| `0x1801` Generic Attribute | — | — | — |
| **`0x1910`（主自訂 service）** | **`0x2bb1`** | **write, write-without-response** | **App→筆 指令通道** |
| | **`0x2bb0`** | **notify** | **筆→App 回應通道** |
| `0x180f` Battery | `2a19` | read,notify | 電量 |

C2 是**單一指令通道**：所有指令都寫進 `0x2bb1`，所有回應都從 `0x2bb0` notify 出來，
指令由 payload 前綴的碼區分。連線**不需系統級配對綁定（bonding）**。

## 封包框架（建包/解包交叉驗證）

```text
Offset  Size  欄位     編碼
0       1     type     幾乎所有 App→筆 指令固定 = 0x01
1       2     value    little-endian uint16，真正的「指令碼」
3       N     payload  各指令自訂（小端序，無長度框頭、無 CRC）
```

## App→筆 指令碼（value 欄位）

| value | 指令 | value | 指令 |
| --- | --- | --- | --- |
| 1 | HANDSHAKE（握手）| 22 | RECORD_RESUME |
| 3 | GET_STATE | 23 | RECORD_STOP |
| **4** | **TIME_SYNC（對時）** | 26 | GET_REC_SESSIONS |
| 5 | DEPAIR（解除配對）⚠️ | 28 | SYNC_REC_FILE_START |
| 6 | GET_STORAGE_VOLUME | 61 | SYNC_STAT_FILE |
| 9 | BATT_STATUS | 101 | BLE_RATE_TEST |
| 20/21 | RECORD_START/PAUSE | **102** | **RESTORE_FACTORY_SETTINGS ⚠️** |

⚠️ 標記者為破壞性指令（解除配對／恢復出廠），本專案工具不送這些。

## 對時封包

```text
01  04 00  <4-byte little-endian unix 秒>
│   │      └ payload：時間戳（unix 秒，非毫秒）
│   └ value = 4（TIME_SYNC）
└ type = 1
寫入 0x2bb1，回應聽 0x2bb0
```

## 握手（兩段式，全程本地、無伺服器）

筆要求先握手才處理其他指令（未握手時對時/查詢皆無回應）。

**第一段** `01 01 00 | 02 03 00 | <token>`：
- `02 03 00` = 固定參數 a=2, b=3, c=0
- `token` = `MD5(sgUnionId)` 前 16 個十六進位字元的 UTF-8 bytes。未登入用空字串，
  token = `d41d8cd98f00b204`（即 `MD5("")[:16]`）。原廠 App 本就支援空帳號握手。

筆回應（value=2，實為 SSN 回傳）：`01 02 00 | "<version>,<base64 SSN>"`。
即筆回傳其 56-byte 裝置加密序號（SSN）。**原廠 App 對 SSN 的驗證函式直接回傳 true——
SSN 不設防、不需伺服器核對。**

**第二段**：以本地 MD5 導出的 token 再送一次握手（`sendSecondHandshake` 反組譯確認同為本地
運算、無網路呼叫）。第二段 token 的確切 input 推導仍在進行中（見專案 issue）。

→ 整條握手鏈無任何伺服器依賴環節：token 本地 MD5、SSN 不驗證、第二段本地 MD5。

## 工具

`ble/` 目錄下（皆為 Python + [bleak](https://github.com/hbldh/bleak)）：

| 腳本 | 用途 | 是否寫入 |
| --- | --- | --- |
| `scan_pen_ble.py` | 掃描並列舉 GATT、判定 C1/C2 | 唯讀 |
| `probe_state_ble.py` | 送唯讀查詢，測通道回應行為 | 唯讀查詢 |
| `set_time_ble.py` | 送對時封包（預設 dry-run）| `--commit` 才寫 |
| `handshake_time_ble.py` | 送握手→對時 | 寫入 |

```bash
pip install bleak
python ble/scan_pen_ble.py              # 先掃描，確認裝置與 GATT
python ble/set_time_ble.py              # dry-run 預覽對時封包
python ble/set_time_ble.py --commit     # 實際送出（筆需在配對模式）
```

## 免責

本專案為互通性逆向工程，針對使用者自有硬體、且原廠已停止服務。工具只送非破壞性指令
（握手、對時、唯讀查詢），不送解除配對/恢復出廠。對筆寫入有未知風險，使用者自負。
與搜狗／騰訊無任何關聯，非官方專案。
