import requests
import logging
from datetime import datetime
from typing import List

from src.core.config.env import Config
from src.modules.crawl_fb.models.GroupSummary import GroupSummary  # Import model để gợi ý code

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self):
        self.token = getattr(Config, "TELEGRAM_TOKEN", None)
        self.chat_id = getattr(Config, "TELEGRAM_CHAT_ID", None)
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_message(self, text: str):
        if not self.token or not self.chat_id:
            logger.warning("⚠️ Chưa cấu hình Telegram Token hoặc Chat ID.")
            return

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            # Nên để True để tin nhắn không bị load khung preview hình ảnh dài ngoằng
            "disable_web_page_preview": True 
        }

        try:
            response = requests.post(self.api_url, json=payload)
            if response.status_code == 200:
                logger.info("✅ Đã gửi báo cáo qua Telegram.")
            else:
                logger.error(f"❌ Lỗi Telegram: {response.text}")
        except Exception as e:
            logger.error(f"❌ Không thể kết nối tới Telegram API: {e}")

    def format_daily_telegram_report(self, summaries: List[GroupSummary]) -> str:
        """
        Hàm biến đổi danh sách GroupSummary thành chuỗi tin nhắn HTML chuẩn Telegram.
        """
        if not summaries:
            return "ℹ️ <b>Tổng hợp báo cáo CRAWL FB</b>\nHôm nay không có dữ liệu bài viết nào được thu thập."

        # Tạo ngày tháng hiện tại cho Header
        today_str = datetime.now().strftime("%d/%m/%Y")
        
        # ── HEADER ────────────────────────────────────────────────────────
        msg = f"🏆 <b>Tổng hợp báo cáo CRAWL FB - {today_str}</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"

        # ── BODY (Duyệt qua từng Group) ───────────────────────────────────
        for idx, summary in enumerate(summaries, 1):
            # Thông tin Group
            msg += f" <b>{idx}. Tên group {summary.group_name}</b>\n"
            msg += f"📊 Tổng bài viết (dưới 24h): <code>{summary.total_posts_24h}</code> bài\n"
            
            # Lấy bài viết hot nhất ra xử lý
            hot = summary.hot_post
            
            msg += f"🔥 <b>BÀI VIẾT HOT NHẤT ({hot.score} điểm)</b>\n"
            msg += f" Đăng lúc: {hot.date}\n"
            msg += f" Tương tác: 👍 {hot.reactions} | 💬 {hot.comments} | 🔄 {hot.shares}\n"
            
            # Link bài viết chính
            msg += f"link bài viết: <a href='{hot.url}'>Xem bài viết gốc</a>\n"
            
            # Xử lý Media (Video/Ảnh) nếu có
            if hot.media_url:
                msg += f"link video: <a href='{hot.media_url}'>Xem Video đính kèm</a>\n"
            
            if hot.images:
                # Hiển thị số lượng ảnh và link ảnh đầu tiên
               
                msg += f"🖼 <b>Hình ảnh đính kèm ({len(hot.images)} tấm):</b>\n"
                
                # Giới hạn số lượng ảnh in ra để tránh spam (Ví dụ: Tối đa 5 ảnh)
                max_images_to_show = 5 
                
                for img_idx, img_url in enumerate(hot.images[:max_images_to_show], 1):
                    msg += f"   ├─ <a href='{img_url}'>Ảnh số {img_idx}</a>\n"
                
                # Nếu số ảnh thực tế nhiều hơn số ảnh in ra, thêm dòng thông báo
                if len(hot.images) > max_images_to_show:
                    msg += f"   └─ <i>... và {len(hot.images) - max_images_to_show} ảnh khác.</i>\n"
                
            # Trích dẫn một đoạn nội dung (Cắt ngắn khoảng 100 ký tự để không bị quá dài)
            content_snippet = hot.content[:100] + "..." if len(hot.content) > 100 else hot.content
            # Escape các ký tự HTML có thể gây lỗi trong nội dung text (như <, >)
            content_snippet = content_snippet.replace("<", "&lt;").replace(">", "&gt;")
            
            if content_snippet.strip():
                msg += f"nội dung: <i>\"{content_snippet}\"</i>\n"
                
            msg += "─────────────────────\n\n"

        # Thêm footer nhỏ (tùy chọn)
        msg += "🤖 <i>Báo cáo được gửi tự động từ hệ thống Crawl.</i>"
        
        return msg