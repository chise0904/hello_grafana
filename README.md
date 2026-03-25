# Grafana + PostgreSQL 監控測試環境

## 架構

```
假資料產生器
    │
    ▼
PostgreSQL ──► postgres_exporter ──► Prometheus ──► Grafana
    │                                                  ▲
    └──────────────── 直接 SQL Query ──────────────────┘
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
| postgres_exporter metrics | http://localhost:9187/metrics | - |

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

## 停止環境

```bash
docker compose down          # 保留資料
docker compose down -v       # 連資料一起清除
```
