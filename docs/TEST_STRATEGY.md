# 📋 Test Strategy & Test Case Design Matrix (測試策略與案例設計文件)

本文件展示 **PulseAPI 自動化測試平台** 針對電商核心交易鏈路（E-Commerce Checkout API）所制定的測試策略、測試設計方法論（等價劃分與邊界值分析），以及自動化斷言規範。

---

## 1. 測試範圍與優先級分層 (Test Scope & Risk-Based Prioritization)

| 優先級 | 測試層級 | 涵蓋場景 | 觸發時機 | SLO / 品質門檻 |
| :--- | :--- | :--- | :--- | :--- |
| **P0 (Blocker)** | E2E 核心業務鏈路 | 登入認證 $\rightarrow$ 商品庫存檢查 $\rightarrow$ 加入購物車 $\rightarrow$ 訂單結帳扣款 | 每次 PR + 部署前 Gate | 通過率 `100%`、單步回應 `< 500ms` |
| **P1 (Critical)** | 權限防護與邊界負向測試 | 未帶 Token 存取攔截 (`401`)、非法負數購買量 (`400`)、不存在商品 (`404`) | 每次 PR + 每日定時巡檢 | 錯誤碼與契約格式 `100%` 符合規範 |
| **P2 (Major)** | 服務健康與效能 SLA 監控 | `/mock/health` 與 `/mock/products` 高頻探針 | 每小時排程 (Cron) | 回應時間 `< 200ms` |

---

## 2. 測試案例設計矩陣 (Equivalence Partitioning & Boundary Value Analysis)

以 **`POST /mock/cart/items`（加入購物車 API）** 為例：

| 測試編號 | 測試設計方法 | 輸入條件 (`product_id`, `quantity`, `Authorization`) | 預期 HTTP 狀態碼 | 預期 JSONPath 斷言結果 |
| :--- | :--- | :--- | :--- | :--- |
| **TC-CART-01** | 有效等價類 (Happy Path) | `PROD-101`, `quantity = 2`, 有效 Bearer Token | `200 OK` | `$.data.cart_total == 2598` |
| **TC-CART-02** | 邊界值分析 (下界 0 / 負數) | `PROD-101`, `quantity = -5`, 有效 Bearer Token | `400 Bad Request` | `$.error.code == "INVALID_QUANTITY"` |
| **TC-CART-03** | 邊界值分析 (超出上限 > 99) | `PROD-101`, `quantity = 100`, 有效 Bearer Token | `400 Bad Request` | `$.error.code == "INVALID_QUANTITY"` |
| **TC-CART-04** | 安全性負向測試 (Auth 缺失) | `PROD-101`, `quantity = 1`, 無 Authorization Header | `401 Unauthorized` | `$.error.code == "UNAUTHORIZED"` |
| **TC-CART-05** | 無效等價類 (資源不存在) | `PROD-99999`, `quantity = 1`, 有效 Bearer Token | `404 Not Found` | `$.error.code == "PRODUCT_NOT_FOUND"` |

---

## 3. 故障注入與根因診斷驗證 (Chaos Engineering & Failure Triage)

為了驗證測試平台具備真實的**缺陷攔截能力 (Defect Detection Effectiveness)**，平台內建兩種故障注入模式：

1. **商業邏輯缺陷 (`pricing_bug`)**：
   * **現象**：結帳 API 回傳 `201 Created`，但 `$.data.order.charged_amount` 錯誤多扣 `500` 元（應為 `2598`，實際回傳 `3098`）。
   * **平台攔截表現**：若僅檢查 `status_code == 201` 會漏抓此嚴重金流 Bug；PulseAPI 透過跨步驟變數 `{{expected_total}}` 比對 `$.data.order.charged_amount`，精準攔截並輸出 `🔍 [資料斷言不符]` 根因診斷。
2. **微服務崩潰 (`server_500_bug`)**：
   * **現象**：結帳時金流資料庫連線池耗盡，回傳 `500 Internal Server Error`。
   * **平台攔截表現**：自動識別為 `💥 [後端服務異常 5xx]`，區分出屬於後端環境異常而非測試腳本問題。
