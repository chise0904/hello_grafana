-- ============================================================
--  Lab 初始化 Schema
--  模擬金融/保險業務場景：訂單、用戶、交易紀錄
-- ============================================================

-- 用戶表
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(50) NOT NULL UNIQUE,
    email       VARCHAR(100) NOT NULL,
    region      VARCHAR(20) NOT NULL DEFAULT 'north',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 訂單表
CREATE TABLE IF NOT EXISTS orders (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    product     VARCHAR(50) NOT NULL,
    amount      NUMERIC(12,2) NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending / success / failed
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- API 請求日誌
CREATE TABLE IF NOT EXISTS api_logs (
    id           SERIAL PRIMARY KEY,
    endpoint     VARCHAR(100) NOT NULL,
    method       VARCHAR(10) NOT NULL,
    status_code  INTEGER NOT NULL,
    response_ms  INTEGER NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 系統告警事件
CREATE TABLE IF NOT EXISTS alert_events (
    id          SERIAL PRIMARY KEY,
    severity    VARCHAR(10) NOT NULL,  -- info / warning / critical
    service     VARCHAR(50) NOT NULL,
    message     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ──────────────────────────────────────────
-- 建立 Read-only 監控用帳號（供 Grafana 直接 SQL 用）
-- ──────────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_ro') THEN
    CREATE ROLE grafana_ro LOGIN PASSWORD 'grafana_ro_pass';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE labdb TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;

-- ──────────────────────────────────────────
-- 預塞一些初始資料
-- ──────────────────────────────────────────
INSERT INTO users (username, email, region) VALUES
  ('alice',   'alice@example.com',   'north'),
  ('bob',     'bob@example.com',     'south'),
  ('charlie', 'charlie@example.com', 'east'),
  ('diana',   'diana@example.com',   'west'),
  ('eve',     'eve@example.com',     'north')
ON CONFLICT DO NOTHING;
