#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Leaflow 多账号自动签到（最终稳定版）
方案：Selenium 真浏览器 + 前端点击签到
环境：GitHub Actions / VPS / Docker / 本地
"""

import os
import time
import logging
import requests
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains


# ================= 日志 =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ================= 单账号 =================
class LeaflowAutoCheckin:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.driver = None
        self.setup_driver()

    def setup_driver(self):
        options = Options()

        # ===== GitHub Actions / VPS 必须参数 =====
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-features=VizDisplayCompositor")
        options.add_argument("--single-process")
        options.add_argument("--user-data-dir=/tmp/chrome-profile")

        # 反自动化
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )

    def safe_click_blank(self):
        try:
            ActionChains(self.driver).move_by_offset(10, 10).click().perform()
            time.sleep(1)
        except:
            pass

    # ================= 登录 =================
    def login(self):
        logger.info("开始登录")
        self.driver.get("https://leaflow.net/login")
        time.sleep(6)
        self.safe_click_blank()

        email_input = WebDriverWait(self.driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='email'],input[type='text']"))
        )
        email_input.clear()
        email_input.send_keys(self.email)

        pwd_input = WebDriverWait(self.driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
        )
        pwd_input.clear()
        pwd_input.send_keys(self.password)

        login_btn = WebDriverWait(self.driver, 20).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[@type='submit' or contains(.,'登录') or contains(.,'Login')]")
            )
        )
        login_btn.click()

        WebDriverWait(self.driver, 40).until(
            lambda d: "login" not in d.current_url
        )

        logger.info(f"登录成功：{self.driver.current_url}")

    # ================= 签到 =================
    def checkin(self):
        logger.info("进入签到页面")
        self.driver.get("https://leaflow.net/dashboard")
        time.sleep(6)
        self.safe_click_blank()

        # 找“签到”按钮并点击
        try:
            btn = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//*[contains(text(),'签到')]"
                ))
            )
            btn.click()
            logger.info("已点击签到按钮")
        except:
            logger.warning("未找到签到按钮，尝试 JS 触发")
            self.driver.execute_script("""
                let el=[...document.querySelectorAll('*')]
                .find(e=>e.innerText && e.innerText.includes('签到'));
                if(el) el.click();
            """)

        time.sleep(4)

        body_text = self.driver.find_element(By.TAG_NAME, "body").text
        if any(k in body_text for k in ["已签到", "签到成功", "今日已签到"]):
            return "签到成功"
        return "已尝试签到（请人工确认）"

    # ================= 余额 =================
    def get_balance(self):
        try:
            body = self.driver.find_element(By.TAG_NAME, "body").text
            import re
            m = re.search(r'(\d+(\.\d+)?)\s*(元|¥|￥)', body)
            if m:
                return m.group(0)
        except:
            pass
        return "未知"

    def run(self):
        try:
            self.login()
            result = self.checkin()
            balance = self.get_balance()
            return True, result, balance
        except Exception as e:
            return False, str(e), "未知"
        finally:
            if self.driver:
                self.driver.quit()


# ================= 多账号 =================
class MultiAccountManager:
    def __init__(self):
        self.accounts = self.load_accounts()
        self.bot = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    def load_accounts(self):
        raw = os.getenv("LEAFLOW_ACCOUNTS", "")
        if not raw:
            raise ValueError("未设置 LEAFLOW_ACCOUNTS")

        accounts = []
        for item in raw.split(","):
            email, pwd = item.split(":", 1)
            accounts.append((email.strip(), pwd.strip()))
        return accounts

    def notify(self, results):
        if not self.bot or not self.chat_id:
            return

        date = datetime.now().strftime("%Y-%m-%d")
        msg = f"🎁 Leaflow 自动签到\n📅 {date}\n\n"

        for email, ok, res, bal in results:
            masked = email[:3] + "***" + email[email.find("@"):]
            if ok:
                msg += f"✅ {masked}\n{res}\n💰 {bal}\n\n"
            else:
                msg += f"❌ {masked}\n{res}\n\n"

        requests.post(
            f"https://api.telegram.org/bot{self.bot}/sendMessage",
            data={"chat_id": self.chat_id, "text": msg},
            timeout=10
        )

    def run_all(self):
        results = []
        for i, (email, pwd) in enumerate(self.accounts, 1):
            logger.info(f"处理账号 {i}/{len(self.accounts)}")
            checker = LeaflowAutoCheckin(email, pwd)
            ok, res, bal = checker.run()
            results.append((email, ok, res, bal))
            time.sleep(6)
        self.notify(results)


def main():
    MultiAccountManager().run_all()


if __name__ == "__main__":
    main()
