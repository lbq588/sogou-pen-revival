# WiFi/WebSocket 協定分析結果（Action 1）

分析方式：Python `androguard` 反組譯 `SogouAIRecorder.apk` 的 Dalvik bytecode（`scripts/dump_dex_class.py`），無使用 IDA/Ghidra。

## 架構總覽

- 手機 App 在**本機（連上錄音筆熱點後）開啟 WebSocket Server，port = 8081**（`ServerSocketManager` 反組譯確認 `const/16 v1, 8081`）
- Server 建構在開源函式庫 `org.java_websocket` 之上，不是自訂 socket
- **錄音筆是 WebSocket Client，主動連線到手機**（推測：錄音筆的 DHCP server 知道連線裝置的 IP，收到手機連上熱點後主動發起連線）
- 應用層 payload 是 **JSON**（`com.google.gson.Gson` 序列化），不是自訂二進位編碼——大幅降低重建難度

## 封包格式（雙向對稱，已交叉驗證）

```
Offset  Size(bytes)  欄位              編碼
0       3            total_length      little-endian uint24（= payload 長度 + 8）
3       1            const = 1         固定值（版本號或 magic byte，意義未知）
4       2            command_type      little-endian uint16（對應 StickWifiProtocol.TYPE_*）
6       2            payload_length    little-endian uint16（JSON payload 的 byte 長度）
8       N            payload           UTF-8 編碼的 JSON 字串
```

**驗證依據**：
- 建包端：`WifiActionCreater.getFileList()` 反組譯出的 `ByteUtil$IntParam` 序列，欄位順序與長度逐一對應上表
- 解包端：`WifiActionParser.onAction([B, WifiEvent)` 對輸入 byte array 做 `copyOfRange(data, 4, 6)` 取出 command type，與建包端 offset 4 完全一致
- 位元組序：`ByteUtil.toByteArray(value, size)` 的反組譯邏輯為 `bytes[i] = (value >> (i*8)) & 0xFF`，確認為 little-endian

## 指令集（`StickWifiProtocol` 定義，共 12 種）

`TYPE_COMMON_ERROR`、`TYPE_FILE_CONTENT`、`TYPE_FILE_DELETE`、`TYPE_FILE_DOWN`、`TYPE_FILE_LIST`、`TYPE_HANDSHAKE`、`TYPE_POWNER`、`TYPE_SAYHELLO`、`TYPE_STOP_FILE_DOWN`、`TYPE_WIFI_CLOSE`、`TYPE_WIFI_RECORD`、`TYPE_WIFI_SPEED_TEST`

實際整數值尚未逐一提取（`StickWifiProtocol$Companion` 的 getter 方法在 bytecode 中回傳欄位值，需再對照 `<clinit>` 找出每個常數實際賦值——留待需要時補查，目前透過 `sget-object ... Companion` + `invoke-virtual ... getTYPE_FILE_LIST()I` 呼叫模式即可在建包/解包程式碼中識別使用了哪個指令，不影響協定重建可行性）。

## Handshake 細節

`WifiActionCreater.handShake(includeUser: Boolean): [B` ——當參數為 `true` 時傳送空字串 `""` 作為使用者識別碼；為 `false` 時才查詢本機資料庫（`UserDao.getLoginUser().getSgunionid()`）取得 Sogou 帳號 ID 並做 MD5。

**這代表官方 App 本身就支援「無登入帳號」的 handshake 模式**——我們的替代工具理論上可以直接送空字串，不需要偽造有效的 Sogou 帳號憑證。

## WiFi 熱點 SSID

**已確認確切字串**：`WIFI_HOTSPOT_SSID = "搜狗AI录音笔C1 Pro-"`（`WifiControlManager` 建構子反組譯直接找到 `const-string`）

完整 SSID = `搜狗AI录音笔C1 Pro-` + 裝置序號（SN）第 13 碼起的子字串。SN 透過藍牙連線取得（`BlueManager.getLastConnectSN()`），代表**必須先完成藍牙配對才能知道要掃描哪個 WiFi SSID**（對應 Action 2 為 Action 3 前置依賴的設計）。

## 藍牙觸發 WiFi 模式：初步證據，待實機驗證

`BlueManager` 內查無任何「enable wifi」/「trigger wifi」語意的方法名稱，只有 `getConnectSN`/`setConnectSN` 等單純的狀態存取方法。初步假設：

**開啟 WiFi 傳輸模式是純粹的實體按鍵動作（電源鍵短按），手機 App 的角色只是維持背景 BLE 連線讓錄音筆能查到「已配對裝置」，並透過這個連線取得 SN 用來組出正確的 SSID。**

若此假設成立，PC 替代工具需要的最小藍牙互動可能只是：完成一次標準 BLE 連線/配對、讀取裝置序號。尚未找到 SN 具體是透過哪個 GATT characteristic 讀取（`setConnectSN` 呼叫點在 `setState`/`clear` 這類狀態管理方法內，尚未追到真正賦值的來源方法）——**此為 Action 2 實機測試前，仍待確認的最後一塊拼圖**，也是唯一大機率需要真實裝置才能驗證、無法純靠再多靜態分析解決的問題。

## 待辦（銜接 Action 2）

- [ ] 追出 SN 究竟透過哪個 GATT characteristic 讀取（繼續反組譯 `StickProtocol` 的 GATT callback）
- [ ] 實機測試：純 BLE 連線（不送任何自訂指令）+ 手動按電源鍵，是否足以讓筆進入 WiFi 模式
- [ ] 若上述失敗，再逐步嘗試送出 handshake/sayhello 指令
