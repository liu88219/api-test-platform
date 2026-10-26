# 📊 PulseAPI 自動化測試週期紀錄總表 (Periodic QA Execution Ledger)

> 本檔案由 GitHub Actions 排程（每日定時巡檢與 CI Quality Gate）自動執行 [`backend/cli_runner.py`](../backend/cli_runner.py) 後更新，完整留存每次自動化回歸測試的週期紀錄。

## 🗓️ 歷史週期巡檢紀錄 (Chronological Run History)

| 執行時間 (UTC) | 總體結果 | 場景通過數 | API 步驟數 | 斷言驗證數 | 總耗時 | 觸發來源 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `2026-10-26 02:32 UTC` | ✅ PASS (100%) | `8/8` 場景 | `27` 步 | `60/60` 斷言 | `0.41 ms` | `CI Scheduled / Gate` |
| `2026-10-25 02:28 UTC` | ✅ PASS (100%) | `8/8` 場景 | `27` 步 | `60/60` 斷言 | `0.48 ms` | `CI Scheduled / Gate` |
| `2026-10-24 02:28 UTC` | ✅ PASS (100%) | `8/8` 場景 | `27` 步 | `60/60` 斷言 | `0.36 ms` | `CI Scheduled / Gate` |
| `2026-10-23 02:29 UTC` | ✅ PASS (100%) | `8/8` 場景 | `27` 步 | `60/60` 斷言 | `0.41 ms` | `CI Scheduled / Gate` |
| `2026-10-22 02:30 UTC` | ✅ PASS (100%) | `8/8` 場景 | `27` 步 | `60/60` 斷言 | `0.38 ms` | `CI Scheduled / Gate` |
| `2026-10-21 08:24 UTC` | ✅ PASS (100%) | `8/8` 場景 | `27` 步 | `60/60` 斷言 | `0.45 ms` | `CI Scheduled / Gate` |
| `2026-10-21 08:23 UTC` | ✅ PASS (100%) | `8/8` 場景 | `27` 步 | `60/60` 斷言 | `1.38 ms` | `CI Scheduled / Gate` |

---

## 🔍 最新一次執行明細報告 (Latest Run Breakdown)

## ⚡ PulseAPI 每日自動化測試巡檢報告 (2026-10-26 02:32:11 UTC)

- **總體狀態 (Quality Gate)**：**✅ PASSED** (通過率 `100.0%`)
- **執行統計**：`8/8` 測試場景 ｜ `27/27` API 步驟 ｜ `60/60` 斷言驗證
- **總執行耗時**：`0.41 ms` ｜ **靶機模式**：`none`

| # | 測試場景名稱 | 狀態 | 步驟數 | 斷言通過 | 耗時 (ms) | 診斷與備註 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #1 | 🛒 電商金流完整下單鏈路 (E2E Checkout Flow) | ✅ PASS | `4/4` | `12/12` | `0.08` | 全數斷言通過 |
| #2 | 🔒 權限防護與邊界負向測試 (Auth & Negative Boundary Suite) | ✅ PASS | `3/3` | `6/6` | `0.03` | 全數斷言通過 |
| #3 | ⚡ 核心服務健康度與 SLA 耗時巡檢 (Health & Latency SLA Probe) | ✅ PASS | `2/2` | `6/6` | `0.02` | 全數斷言通過 |
| #4 | 💳 金流冪等性與防重複扣款測試 (Idempotency & Duplicate Checkout Guard) | ✅ PASS | `4/4` | `7/7` | `0.1` | 全數斷言通過 |
| #5 | 📦 庫存超賣防護與完整邊界值分析 (Inventory Overselling & Full BVA) | ✅ PASS | `3/3` | `7/7` | `0.03` | 全數斷言通過 |
| #6 | 🎟️ 優惠券折抵與計價邏輯決策表 (Coupon & Pricing Decision Matrix) | ✅ PASS | `4/4` | `9/9` | `0.06` | 全數斷言通過 |
| #7 | 🔐 越權存取與角色權限防護 (OWASP API Security: BOLA & RBAC) | ✅ PASS | `3/3` | `6/6` | `0.03` | 全數斷言通過 |
| #8 | 🔄 訂單狀態機生命週期測試 (Order State Machine Transition) | ✅ PASS | `4/4` | `7/7` | `0.06` | 全數斷言通過 |
