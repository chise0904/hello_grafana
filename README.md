# Grafana + PostgreSQL 監控測試環境

## 架構

```
假資料產生器
    │
    ▼
PostgreSQL ──► postgres_exporter ──► Prometheus ──► Grafana
    │               ▲                    ▲              ▲
    └── 直接 SQL ───┘                    │              │
                                         │              │
Blackbox Exporter ───────────────────────┘              │
SSL Exporter ────────────────────────────┘              │
Sloth（SLO rules 產生器，one-shot）─────► slo-rules.yml─┘
```

## 快速啟動

```bash
cd grafana-pg-lab
docker compose up -d
```

啟動完成後等約 30 秒讓假資料開始寫入。

## 服務入口

| 服務 | URL | 帳號密碼 |
|------|-----|---------|
| Grafana | http://localhost:3000 | admin / admin123 |
| Prometheus | http://localhost:9090 | - |
| Alertmanager | http://localhost:9093 | - |
| postgres_exporter metrics | http://localhost:9187/metrics | - |
| Blackbox Exporter | http://localhost:9115 | - |
| SSL Exporter | http://localhost:9219 | - |

## 測試場景說明

### 場景 1：DB 效能監控（Prometheus + exporter）
1. 開啟 Grafana → Dashboards → 搜尋 "PostgreSQL"
2. 或 Import Dashboard ID: **9628**（官方 PostgreSQL exporter dashboard）
3. 可看到 connections、transaction/s、buffer hit rate 等指標

### 場景 2：直接 SQL Query
1. Grafana → Explore → 選 Data Source: **PostgreSQL-Direct**
2. 切換到 "Code" 模式，輸入任意 SQL：
   ```sql
   SELECT NOW() AS time, count(*) AS total FROM orders
   WHERE created_at > NOW() - INTERVAL '10 minutes'
   ```

### 場景 3：業務數據 Dashboard
1. Grafana → Dashboards → Lab → **業務數據 Dashboard（直接 SQL）**
2. 可看到即時訂單數、API 請求量、告警事件等

## 資料庫結構

- `users` - 用戶資料（模擬會員成長）
- `orders` - 訂單資料（模擬業務流量）
- `api_logs` - API 請求紀錄（模擬 access log）
- `alert_events` - 系統告警事件

## Read-only 帳號（供 Grafana 直接 SQL）

| 參數 | 值 |
|------|----|
| host | localhost:5432 |
| database | labdb |
| user | grafana_ro |
| password | grafana_ro_pass |

## SLO 監控（Sloth）

[Sloth](https://sloth.dev) 在啟動時以 one-shot 模式讀取 `sloth/slos.yml`，產生符合 Google SRE 標準的 multi-burn-rate alerting rules，輸出至 `prometheus/slo-rules.yml` 後由 Prometheus 載入。

### 已定義的 SLO

| SLO 名稱 | 目標 | 指標來源 | 說明 |
|---------|------|---------|------|
| `postgres-availability` | 99.9% | `pg_up` | PostgreSQL exporter 可用性 |
| `http-probe-availability` | 99.5% | `probe_success{job="blackbox-http"}` | 外部 HTTP 端點可用性 |
| `postgres-tcp-availability` | 99.9% | `probe_success{job="blackbox-tcp"}` | PostgreSQL port 5432 TCP 連線可用性 |

### 查看 SLO 狀態

**Grafana：**
- Dashboards → Lab → **SLO Overview（Sloth）**
- 可看到三個 SLO 的 Error Budget Gauge、Burn Rate Stat 和多 window 趨勢圖

**Prometheus：**
1. 前往 http://localhost:9090/rules → 搜尋 `sloth-slo`，可看到所有 recording rules 和 burn rate alerts
2. 查詢 error budget 剩餘：
   ```
   slo:error_budget:ratio{sloth_service="grafana-pg-lab"}
   ```
3. 查詢當前燃燒率：
   ```
   slo:current_burn_rate:ratio{sloth_service="grafana-pg-lab"}
   ```

### 修改 SLO

編輯 `sloth/slos.yml` 後，重新執行 Sloth 產生新的 rules：

```bash
docker compose run --rm sloth
docker compose kill -s SIGHUP prometheus   # 觸發 Prometheus 熱載入
```

## 停止環境

```bash
docker compose down          # 保留資料
docker compose down -v       # 連資料一起清除
```
