#!/usr/bin/env python3
"""
Leaflow 多账号自动签到脚本

环境变量：
LEAFLOW_ACCOUNTS = 邮箱1:密码1,邮箱2:密码2,邮箱3:密码3
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


# =======================
# 日志配置
# =======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =======================
# 单账号签到类
# =======================
class LeaflowAutoCheckin:

    def __init__(self, email, password):
        self.email = email
        self.password = password

        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        if not self.email or not self.password:
            raise ValueError("邮箱和密码不能为空")

        self.driver = None
        self.setup_driver()

    def setup_driver(self):
        """设置 Chrome 驱动"""
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
        """关闭初始弹窗"""
        try:
            logger.info("尝试关闭初始弹窗...")
            time.sleep(3)

            actions = ActionChains(self.driver)
            actions.move_by_offset(10, 10).click().perform()

            logger.info("弹窗已关闭")
            time.sleep(2)
            return True
        except Exception as e:
            logger.warning(f"关闭弹窗失败: {e}")
            return False

    def wait_clickable(self, by, value, timeout=10):
        return WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )

    def login(self):
        """登录"""
        logger.info("开始登录")

        self.driver.get("https://leaflow.net/login")
        time.sleep(5)
        self.close_popup()

        # 输入邮箱
        email_selectors = [
            "input[type='email']",
            "input[type='text']",
            "input[name='email']",
            "input[name='username']",
        ]

        email_input = None
        for selector in email_selectors:
            try:
                email_input = self.wait_clickable(By.CSS_SELECTOR, selector, 5)
                break
            except Exception:
                continue

        if not email_input:
            raise Exception("找不到邮箱输入框")

        email_input.clear()
        email_input.send_keys(self.email)

        # 输入密码
        password_input = self.wait_clickable(
            By.CSS_SELECTOR, "input[type='password']", 10
        )
        password_input.clear()
        password_input.send_keys(self.password)

        # 登录按钮
        login_btn = self.wait_clickable(
            By.XPATH, "//button[contains(text(), '登录') or contains(text(), 'Login')]",
            10
        )
        login_btn.click()

        WebDriverWait(self.driver, 20).until(
            lambda d: "login" not in d.current_url
        )

        logger.info("登录成功")
        return True

    def checkin(self):
        """签到"""
        self.driver.get("https://checkin.leaflow.net")
        time.sleep(10)

        try:
            btn = self.driver.find_element(
                By.XPATH, "//button[contains(text(), '签到')]"
            )
            if "已签到" in btn.text:
                return "今日已签到"

            btn.click()
            time.sleep(5)
            return "签到成功"
        except Exception:
            return "签到失败"

    def get_balance(self):
        """获取余额"""
        self.driver.get("https://leaflow.net/dashboard")
        time.sleep(5)

        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            import re
            numbers = re.findall(r"\d+\.?\d*", body_text)
            if numbers:
                return f"{numbers[0]} 元"
        except Exception:
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


# =======================
# 多账号管理
# =======================
class MultiAccountManager:

    def __init__(self):
        self.accounts = self.load_accounts()
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    def load_accounts(self):
        accounts = []
        raw = os.getenv("LEAFLOW_ACCOUNTS", "")

        for item in raw.split(","):
            if ":" in item:
                email, password = item.split(":", 1)
                accounts.append({
                    "email": email.strip(),
                    "password": password.strip()
                })

        if not accounts:
            raise ValueError("未配置 LEAFLOW_ACCOUNTS")

        return accounts

    def run_all(self):
        results = []

        for account in self.accounts:
            checker = LeaflowAutoCheckin(
                account["email"], account["password"]
            )
            results.append(
                (account["email"], *checker.run())
            )
            time.sleep(5)

        return results


# =======================
# 主入口
# =======================
def main():
    manager = MultiAccountManager()
    results = manager.run_all()

    for email, success, result, balance in results:
        logger.info(f"{email} | {success} | {result} | {balance}")


if __name__ == "__main__":
    main()
