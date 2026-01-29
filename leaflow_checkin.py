#!/usr/bin/env python3
"""
Leaflow 多账号自动签到脚本（稳定版）
模式：Selenium 登录 + requests API 签到
"""

import os
import time
import logging
import requests
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains


# ========== 日志 ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ========== 单账号 ==========
class LeaflowAutoCheckin:
    def __init__(self, email, password):
        self.email = email
        self.password = password

        if not self.email or not self.password:
            raise ValueError("邮箱或密码为空")

        self.driver = None
        self.setup_driver()

    def setup_driver(self):
        chrome_options = Options()

        if os.getenv("GITHUB_ACTIONS"):
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")

        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option(
            "excludeSwitches", ["enable-automation"]
        )
        chrome_options.add_experimental_option(
            "useAutomationExtension", False
        )

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

    def close_popup(self):
        try:
            time.sleep(3)
            ActionChains(self.driver).move_by_offset(10, 10).click().perform()
            time.sleep(1)
        except:
            pass

    def login(self):
        logger.info("开始登录")
        self.driver.get("https://leaflow.net/login")
        time.sleep(5)
        self.close_popup()

        # 邮箱
        email_input = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='text'],input[type='email']"))
        )
        email_input.clear()
        email_input.send_keys(self.email)

        # 密码
        password_input = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
        )
        password_input.clear()
        password_input.send_keys(self.password)

        # 登录按钮
        login_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' or contains(text(),'登录') or contains(text(),'Login')]"))
        )
        login_btn.click()

        WebDriverWait(self.driver, 20).until(
            lambda d: "login" not in d.current_url
        )

        logger.info(f"登录成功：{self.driver.current_url}")
        return True

    # ===== Selenium → Cookie =====
    def get_cookies(self):
        cookies = {}
        for c in self.driver.get_cookies():
            cookies[c["name"]] = c["value"]
        return cookies

    # ===== 构造 requests 会话 =====
    def build_session(self, cookies):
        s = requests.Session()
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://leaflow.net/",
            "Origin": "https://leaflow.net",
        })
        for k, v in cookies.items():
            s.cookies.set(k, v)
        return s

    # ===== API 签到（核心）=====
    def api_checkin(self):
        logger.info("使用 API 进行签到")
        cookies = self.get_cookies()
        session = self.build_session(cookies)

        checkin_urls = [
            "https://leaflow.net/api/checkin",
            "https://leaflow.net/api/user/checkin",
            "https://leaflow.net/api/v1/checkin",
        ]

        for url in checkin_urls:
            try:
                r = session.post(url, timeout=10)
                logger.info(f"{url} → {r.status_code}")

                if r.status_code == 200:
                    text = r.text
                    if any(k in text for k in ["成功", "已签到", "success", "checked"]):
                        return f"签到成功：{text}"

            except Exception as e:
                logger.debug(f"{url} 请求失败：{e}")

        raise Exception("API 签到失败（接口未命中）")

    # ===== 获取余额 =====
    def get_balance(self):
        try:
            self.driver.get("https://leaflow.net/dashboard")
            time.sleep(3)
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
            result = self.api_checkin()
            balance = self.get_balance()
            return True, result, balance
        except Exception as e:
            return False, str(e), "未知"
        finally:
            if self.driver:
                self.driver.quit()


# ========== 多账号 ==========
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
        for p in raw.split(","):
            email, pwd = p.split(":", 1)
            accounts.append({"email": email.strip(), "password": pwd.strip()})
        return accounts

    def send_notification(self, results):
        if not self.bot or not self.chat_id:
            return

        date = datetime.now().strftime("%Y/%m/%d")
        msg = f"🎁 Leaflow 签到通知\n📅 {date}\n\n"

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
        for i, acc in enumerate(self.accounts, 1):
            logger.info(f"处理账号 {i}/{len(self.accounts)}")
            checker = LeaflowAutoCheckin(acc["email"], acc["password"])
            ok, res, bal = checker.run()
            results.append((acc["email"], ok, res, bal))
            time.sleep(5)

        self.send_notification(results)


def main():
    MultiAccountManager().run_all()


if __name__ == "__main__":
    main()
