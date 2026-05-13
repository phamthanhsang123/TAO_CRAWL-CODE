import os
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parents[3] / ".env"

print("ENV PATH:", env_path)

load_dotenv(dotenv_path=env_path)

print("GOOGLE_CREDENTIALS_PATH =", os.getenv("GOOGLE_CREDENTIALS_PATH"))

class Config:
   
    GROUP_URL = os.getenv("FB_GROUP_URL")
    STATE_PATH = "facebook_state.json"
    OUTPUT_FILE = "fb_posts_final.txt"
    OUTPUT_FILE_HOT = "fb_post_hot.txt"
    SCROLL_ATTEMPTS = int(os.getenv("SCROLL_ATTEMPTS", 30))
    SCROLL_DISTANCE = 2000      # Số pixel cuộn chuột mỗi lần
    SCROLL_SLEEP_MIN = 1.5      # Thời gian nghỉ tối thiểu sau khi cuộn (giây)
    SCROLL_SLEEP_MAX = 4.0      # Thời gian nghỉ tối đa sau khi cuộn (giây)
    MAX_OLD_POSTS_LIMIT = 20     # Ngưỡng bài cũ liên tiếp để dừng tool
    SAFE_LIMIT=300                # ngưỡng bài viết tối đa để ngừng nếu không nó sẽ lấy mãi nếu có các bài viết hợp lệ 
    #  trang đăng nhập nếu chưa lấy cookie
    # Tìm đến các ô để nhập dữ liệu login
      # ô email
    AUTH_SELECTORS = {
        "email": 'input[name="email"]',
        "password": 'input[name="pass"]'
    }
    FORCE_LOGIN = False
    #    nhập dữ liệu vào ô e mail
    FB_EMAIL = os.getenv("FB_EMAIL")
    #     nhập dữ liieeuj vào ô mật khẩu
    FB_PASSWORD = os.getenv("FB_PASSWORD")
    # thẻ bài viết
    # Thẻ bao quanh toàn bộ 1 bài viết (thường là div con trực tiếp của feed)
    FB_POST_CONTAINER = 'div[role="feed"] > div'

    # Thẻ chứa nội dung text chính
    FB_POST_CONTENT = 'div[data-ad-comet-preview="message"]'

     # Thẻ chứa link timestamp/URL
    FB_POST_LINK = 'a[role="link"][target="_blank"]'

    
    #  gg sheet
    GOOGLE_CREDENTIALS_PATH=os.getenv("GOOGLE_CREDENTIALS_PATH")
    SPREADSHEET_ID=os.getenv("SPREADSHEET_ID")
    GOOGLE_SHEET_NAME=os.getenv("GOOGLE_SHEET_NAME")


    GOOGLE_SHEET_NAME_APPEND=os.getenv("GOOGLE_SHEET_NAME_APPEND")
  


    # Cấu hình giờ mặt định để chạy mỗi ngày
    CRAWL_HOUR=14   # giờ chạy
    CRAWL_MINUTE=48   # phút chạy


    # cấu hình cho telegram
    TELEGRAM_TOKEN=os.getenv("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID=os.getenv("TELEGRAM_CHAT_ID")

    NAME_URL_GG_SHEET="group_url"
    NAME_GROUP_GG_SHEET="name"

    COOKIE_DIR = "sessions"
    NGROK_AUTH_TOKEN=os.getenv("NGROK_AUTH_TOKEN")