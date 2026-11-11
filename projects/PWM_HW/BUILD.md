# 匯入與建置

## 歷史工具鏈

- CCS 21.0.1，TI C2000 CGT 25.11.1.LTS。
- C2000Ware 5.00.00.00，裝置 F280049C，C28xx_CPU1。
- XDS110，RAM linker `280049C_RAM_lnk.cmd`，COFF ABI，`-g`，未指定 `-O`。

公開副本尚未重新建置或下載到硬體。歷史建置成功是來源專案的紀錄，不能據此宣稱本次搬移後已驗證匯入及建置。

## 步驟

1. 安裝上述工具鏈及 C2000Ware。
2. 在 CCS 定義 `C2000WARE_ROOT` 為本機 C2000Ware 5.00.00.00 的安裝根目錄。公開 `.cproject` 已把原固定安裝路徑改成 `${C2000WARE_ROOT}`，include 路徑保留 `device_support/f28004x/common/include` 與 `headers/include`。
3. 匯入 `firmware/PWM_HW`，或擇一匯入兩個 `PWM_3CH_*`。三個專案的 `.project` 名稱分別保留，避免互相覆寫。
4. 原專案於 `Init.h` 選擇 `HW_PART=1…5`；補測專案保留其 Up-Count／Up-Down 設定。
5. 執行 clean build。歷史曾遇到修改標頭卻回報 up to date；需確認版本設定與新輸出對應。公開副本未包含 `Debug/` 或 `.out`。
6. 要操作板子前，先依根目錄 [AGENTS.md](../../AGENTS.md) 閱讀 JEV 操作規則、確認當前工具及接線，再載入新建置輸出；不要把歷史紀錄當成目前板上狀態。

## 保留與省略

保留 `.project`、`.cproject`、`.ccsproject`、C／H／ASM／linker command 及通用 XDS110 target configuration。TI 支援檔與授權聲明保留。私人 launch 設定、IDE 本機狀態、舊 Timer 專案的殘留 loader／驗算腳本、編譯輸出與安裝包不公開。

本次只將 C2000Ware include 路徑改為變數，未修改韌體的控制邏輯或常數。版本對照可使用 [PUBLICATION_MANIFEST.json](PUBLICATION_MANIFEST.json) 的公開／來源雜湊。
