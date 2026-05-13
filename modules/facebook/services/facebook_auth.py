import os
import re
import json
from pathlib import Path
from playwright.sync_api import Page, BrowserContext
from .human_behavior import HumanBehavior
from src.core.config.env import Config
from src.core.utils.logger import setup_logger

logger = setup_logger(__name__)

class FacebookAuth:
    def __init__(self, config: Config, human: HumanBehavior = None):
        self.config = config
        self.human = human or HumanBehavior()
        self.sessions_dir = Path(config.COOKIE_DIR or "sessions")
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.default_state_path = str(self.sessions_dir / "default_account_cookie.json")

    def login(
        self,
        context: BrowserContext,
        custom_email: str = None,
        custom_pass: str = None
    ) -> Page:
        """
        Đảm bảo đăng nhập, trả về page đã sẵn sàng.
        - Nếu chạy mặc định (Cronjob): Check cookie -> Dùng luôn nếu còn sống -> Chết thì Login & Lưu lại.
        - Nếu có custom_email (Client API): Login thẳng, KHÔNG lưu cookie.
        """
        # Xác định xem luồng này dùng tài khoản mặc định hay tài khoản khách gửi lên
        is_default_account = not (custom_email and custom_pass)
        
        email = custom_email if custom_email else self.config.FB_EMAIL
        password = custom_pass if custom_pass else self.config.FB_PASSWORD
        
        # Chỉ dùng 1 tên file cố định cho tài khoản mặc định để tránh sinh ra nhiều file rác
        cookie_file = Path(self.default_state_path)

        # 1. KIỂM TRA VÀ LOAD COOKIE (CHỈ DÀNH CHO TÀI KHOẢN MẶC ĐỊNH)
        if is_default_account and cookie_file.exists() and not self.config.FORCE_LOGIN:
            try:
                with open(cookie_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    if "cookies" in state:
                        context.add_cookies(state["cookies"])

                page = context.new_page()   # tạo page mới với cookie đã load
                page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
                self.human.gamma_delay(2, 2)
                
                # Kiểm tra cookie còn sống không (Nếu không thấy form login -> Đã vào trong)
                if page.locator(self.config.AUTH_SELECTORS["email"]).count() == 0:
                    logger.info(f"✅ Đã khôi phục phiên từ cookie: {email}. Bỏ qua đăng nhập.")
                    return page
                else:
                    logger.warning("⚠️ Cookie đã hết hạn hoặc bị FB đăng xuất. Tiến hành đăng nhập lại...")
                    cookie_file.unlink() # Xóa file cookie cũ đi
                    page.close()
            except Exception as e:
                logger.warning(f"Không thể load cookie: {e}")

        # 2. ĐĂNG NHẬP MỚI TỪ ĐẦU
        page = context.new_page()
        account_type = "Mặc định (Cronjob)" if is_default_account else "Từ Client (API)"
        logger.info(f"🔑 Bắt đầu đăng nhập: {email} | Nguồn: {account_type}")
        
        page.goto("https://www.facebook.com/login")
        self.human.gamma_delay(2, 3)

        email_input = page.locator(self.config.AUTH_SELECTORS["email"])
        email_input.click()
        self._type_like_human(email_input, email)
        self.human.gamma_delay(0.5, 1.5)

        pass_input = page.locator(self.config.AUTH_SELECTORS["password"])
        pass_input.click()
        self._type_like_human(pass_input, password)
        self.human.gamma_delay(1, 2)

        page.keyboard.press("Enter")

        try:
            # Đợi tải DOM xong sau khi nhấn Enter
            page.wait_for_load_state("domcontentloaded")
            
            # Đợi cho đến khi URL KHÔNG CÒN chứa chữ "/login" nữa
            # Dùng Regex để bypass hoàn toàn CSP
            page.wait_for_url(re.compile(r"^(?!.*\/login).*$"), timeout=30_000)
            
            # Kiểm tra xem có bị kẹt ở bước xác minh không
            if "checkpoint" in page.url:
                logger.error("🚨 Facebook yêu cầu xác minh danh tính hoặc 2FA!")
                raise ValueError("LOGIN_FAILED")

            logger.info("✅ Đăng nhập qua cổng thành công!")

        except Exception as e:
            logger.error(f"Đăng nhập thất bại hoặc timeout: {e}")
            raise ValueError("LOGIN_FAILED")

        # 3. LƯU COOKIE (CHỈ DÀNH CHO TÀI KHOẢN MẶC ĐỊNH)
        if is_default_account:
            try:
                context.storage_state(path=str(cookie_file))
                logger.info(f"💾 Đã lưu phiên làm việc mới vào: {cookie_file}")
            except Exception as e:
                logger.warning(f"Không thể lưu cookie: {e}")
        else:
            logger.info("🚫 Chạy bằng API Client -> Bỏ qua bước lưu cookie.")

        return page

    def _type_like_human(self, element, text: str):
        for char in text:
            element.press_sequentially(char)
            self.human.gamma_delay(mean=0.12, shape=2)

    @staticmethod
    def _safe_email(email: str) -> str:
        return email.replace("@", "_at_").replace(".", "_dot_")