#!/usr/bin/env python3
"""
假資料產生器 - 模擬金融業務流量
持續對 PostgreSQL 寫入訂單、API Log、告警事件
"""

import os
import time
import random
import logging
import psycopg2
from faker import Faker
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DataGen] %(message)s"
)

fake = Faker("zh_TW")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "labdb"),
    "user": os.getenv("DB_USER", "labuser"),
    "password": os.getenv("DB_PASS", "labpass123"),
}

PRODUCTS = ["壽險A方案", "壽險B方案", "車險基本型", "車險全險", "房貸壽險", "傷害險", "醫療險"]
ENDPOINTS = ["/api/auth/login", "/api/orders", "/api/users/profile",
             "/api/payment", "/api/reports/monthly", "/api/policy/query"]
SERVICES  = ["payment-service", "auth-service", "order-service", "notification-service"]
REGIONS   = ["north", "south", "east", "west"]


def wait_for_db(max_retries=20):
    for i in range(max_retries):
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            conn.close()
            logging.info("DB 連線成功！")
            return True
        except Exception as e:
            logging.info(f"等待 DB 就緒... ({i+1}/{max_retries})")
            time.sleep(3)
    raise RuntimeError("無法連線 DB，請檢查設定")


def get_user_ids(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users")
        rows = cur.fetchall()
        return [r[0] for r in rows] if rows else [1]


def insert_order(cur, user_ids):
    cur.execute(
        """
        INSERT INTO orders (user_id, product, amount, status, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        """,
        (
            random.choice(user_ids),
            random.choice(PRODUCTS),
            round(random.uniform(500, 150000), 2),
            random.choices(["success", "pending", "failed"], weights=[70, 20, 10])[0],
        ),
    )


def insert_api_log(cur):
    cur.execute(
        """
        INSERT INTO api_logs (endpoint, method, status_code, response_ms, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        """,
        (
            random.choice(ENDPOINTS),
            random.choices(["GET", "POST", "PUT", "DELETE"], weights=[50, 30, 15, 5])[0],
            random.choices([200, 201, 400, 401, 404, 500], weights=[60, 15, 10, 5, 7, 3])[0],
            random.randint(10, 2000),
        ),
    )


def insert_alert(cur):
    """低機率觸發告警，模擬真實場景"""
    if random.random() > 0.05:   # 只有 5% 機率產生告警
        return
    severity = random.choices(["info", "warning", "critical"], weights=[60, 30, 10])[0]
    messages = {
        "info":     "定期健康檢查完成",
        "warning":  f"{random.choice(SERVICES)} 回應時間超過 1s",
        "critical": f"{random.choice(SERVICES)} 連線池耗盡，目前連線數 {random.randint(90,100)}/100",
    }
    cur.execute(
        """
        INSERT INTO alert_events (severity, service, message, created_at)
        VALUES (%s, %s, %s, NOW())
        """,
        (severity, random.choice(SERVICES), messages[severity]),
    )


def maybe_add_user(cur):
    """低機率新增用戶，模擬會員成長"""
    if random.random() > 0.02:
        return
    username = fake.user_name() + str(random.randint(100, 999))
    try:
        cur.execute(
            "INSERT INTO users (username, email, region) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (username, fake.email(), random.choice(REGIONS)),
        )
    except Exception:
        pass


def main():
    wait_for_db()

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    logging.info("開始持續產生測試資料（Ctrl+C 停止）")

    cycle = 0
    while True:
        try:
            user_ids = get_user_ids(conn)

            with conn.cursor() as cur:
                # 每個 cycle 批次寫入，模擬突發流量
                batch = random.randint(1, 8)
                for _ in range(batch):
                    insert_api_log(cur)

                # 訂單頻率比 API log 低
                if random.random() > 0.4:
                    insert_order(cur, user_ids)

                insert_alert(cur)
                maybe_add_user(cur)

            conn.commit()
            cycle += 1

            if cycle % 20 == 0:
                logging.info(f"已完成 {cycle} 個週期，持續寫入中...")

            # 0.5 ~ 2 秒一個週期，模擬真實流量節奏
            time.sleep(random.uniform(0.5, 2.0))

        except KeyboardInterrupt:
            logging.info("收到停止訊號，結束產生器")
            break
        except Exception as e:
            logging.error(f"寫入失敗: {e}")
            conn.rollback()
            time.sleep(5)

    conn.close()


if __name__ == "__main__":
    main()
