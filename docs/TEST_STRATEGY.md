# 📋 Test Strategy & Test Case Design Matrix (測試策略與案例設計文件)

本文件展示 **PulseAPI 自動化測試平台** 針對電商核心交易與金流微服務所制定的 **8 大自動化測試場景（共 27 個 API 步驟、60 條斷言規則）**，涵蓋正向 E2E 鏈路、邊界值分析（BVA）、決策表測試（Decision Table）、狀態機轉換（State Transition）、金流冪等性防呆（Idempotency）與 OWASP API 資安防護（BOLA & RBAC）。

---

## 1. 八大自動化測試場景總覽 (8 Automated Test Suites Matrix)

| 場景編號 | 場景名稱 | 測試設計方法論 | 步驟數 | 斷言數 | 驗證重點與預期行為 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **#1** | **🛒 電商金流完整下單鏈路** | E2E 業務鏈路 + 變數傳遞 | `4` | `12` | 登入取 Token $\rightarrow$ 查庫存 $\rightarrow$ 加購物車 $\rightarrow$ 結帳扣款 (`2598` 元) |
| **#2** | **🔒 權限防護與邊界負向測試** | 負向測試 (Negative Testing) | `3` | `6` | 未帶 Token 攔截 (`401`)、負數數量 `-5` (`400`)、不存在商品 (`404`) |
| **#3** | **⚡ 核心服務健康度與 SLA 巡檢** | 煙霧測試與效能 SLO | `2` | `6` | `/mock/health` 與商品目錄回應耗時 `< 200ms` |
| **#4** | **💳 金流冪等性與防重複扣款測試** | 冪等性防護 (Idempotency) | `4` | `7` | 同一購物車首次結帳 `201 PAID`，二次重複提交攔截回傳 `409 DUPLICATE_CHECKOUT` |
| **#5** | **📦 庫存超賣防護與完整邊界值分析** | 邊界值分析法 (Full BVA) | `3` | `7` | 零值 `0` (`400`)、超出上限 `100 > 99` (`400`)、超買 `50 > 現貨 42` (`409 INSUFFICIENT_STOCK`) |
| **#6** | **🎟️ 優惠券折抵與計價邏輯決策表** | 決策表測試 (Decision Table) | `4` | `9` | 有效券 `VIP200` 折抵後 `2398` 元 (`201`)、過期券 (`400 COUPON_EXPIRED`)、偽造券 (`400 INVALID_COUPON`) |
| **#7** | **🔐 越權存取與角色權限防護** | OWASP API Security (BOLA/RBAC) | `3` | `6` | 密碼錯誤 (`401`)、買家偷打管理員刪商品 API (`403 ADMIN_ONLY`)、跨帳號偷看他人訂單 (`403 BOLA`) |
| **#8** | **🔄 訂單狀態機生命週期測試** | 狀態轉換測試 (State Machine) | `4` | `7` | 訂單建立 (`PAID`) $\rightarrow$ 首次退款 (`200 REFUNDED`) $\rightarrow$ 禁止二次重複退款 (`409 ORDER_ALREADY_REFUNDED`) |

---

## 2. 週期巡檢紀錄與每日自動報表 (Periodic QA Execution Ledger)

每天由 GitHub Actions 定時排程執行全量 8 大測試場景，並自動將測試結果寫入：
* 📊 **[`reports/DAILY_TEST_LEDGER.md`](../reports/DAILY_TEST_LEDGER.md)**：按時間軸留存每次執行的通過率、耗時與場景明細表。
* 📋 **GitHub Actions Job Summary**：在每次 CI Workflow 頁面直接渲染視覺化 Markdown 測試報告。
