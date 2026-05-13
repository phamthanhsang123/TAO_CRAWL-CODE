import logging
from typing import List
from apscheduler.schedulers.background import BackgroundScheduler

# Import các service
from src.modules.gg_sheet.services.google_sheets import GoogleApiService
from src.modules.facebook.services.facebook_scraper import FacebookScraper, GroupTarget  # Đảm bảo bạn đã import GroupTarget từ file scraper
from src.modules.telegram.services.telegram_service import TelegramService
from src.core.config.env import Config
from src.modules.crawl_fb.models.GroupSummary import GroupSummary
from src.modules.gg_sheet.services.google_sheets import GoogleApiService
logger = logging.getLogger(__name__)

def execute_crawl_workflow():
    """
    Luồng công việc thực tế cào dữ liệu và báo cáo.
    Đã được tối ưu để xử lý hàng loạt thay vì lặp lẻ tẻ.
    """
    logger.info("🚀 BẮT ĐẦU CHẠY TIẾN TRÌNH CÀO DỮ LIỆU TỰ ĐỘNG...")
    telegram = TelegramService()
    ggsheet=GoogleApiService()
    try:
        # 1. Lấy danh sách URL từ Google Sheets
        api_service = GoogleApiService()
        sheet_data = api_service.get_sheet_data(
            spreadsheet_id=Config.SPREADSHEET_ID,
            sheet_name=Config.GOOGLE_SHEET_NAME
        )
        
        # 2. Chuyển đổi dữ liệu thô thành mảng GroupTarget
        target_groups: List[GroupTarget] = []
        for row in sheet_data:
            group_url = row.get(Config.NAME_URL_GG_SHEET, "").strip()
            group_name = row.get(Config.NAME_GROUP_GG_SHEET, "Unknown").strip()
            
            if not group_url:
                logger.debug(f"⚠️ Bỏ qua dòng không có URL (Group: {group_name})")
                continue
                
            target_groups.append(GroupTarget(name=group_name, url=group_url))

        if not target_groups:
            logger.warning("❌ Không tìm thấy danh sách Group hợp lệ để cào.")
            return

        # 3. Bắt đầu cào toàn bộ danh sách Group (mở trình duyệt 1 lần)
        logger.info(f"Tổng cộng có {len(target_groups)} group cần cào dữ liệu.")
        scraper = FacebookScraper(Config)
        
        # Hàm này trả về List[GroupSummary] như bạn đã yêu cầu
        daily_summary_report: List[GroupSummary] = scraper.scrape_groups(target_groups)

        # 4. Gửi báo cáo qua Telegram
        if daily_summary_report:
            ggsheet.append_data_to_sheet(data=daily_summary_report)
            mes = telegram.format_daily_telegram_report(summaries=daily_summary_report)
            telegram.send_message(mes)
            logger.info("✅ GỬI BÁO CÁO TELEGRAM THÀNH CÔNG. TIẾN TRÌNH HOÀN TẤT.")
        else:
            logger.warning("⚠️ Cào xong nhưng không thu được dữ liệu nào hợp lệ để báo cáo.")

    except Exception as e:
        # Ghi log chi tiết lỗi nhưng không làm sập (crash) ứng dụng
        logger.error(f"❌ Tiến trình cào dữ liệu thất bại: {e}", exc_info=True)
        
        # Tự động báo lỗi về Telegram để Admin biết hệ thống có vấn đề
        try:
            telegram.send_message(f"🚨 <b>LỖI HỆ THỐNG CÀO DỮ LIỆU</b> 🚨\n\nChi tiết: <code>{str(e)}</code>")
        except Exception as tele_err:
            logger.error(f"Không thể gửi thông báo lỗi qua Telegram: {tele_err}")


def setup_and_start_jobs():
    """
    Khởi tạo scheduler và gắn lịch chạy.
    """
    scheduler = BackgroundScheduler()

    # Thêm công việc vào lịch
    scheduler.add_job(
        func=execute_crawl_workflow,
        trigger='cron',
        hour=Config.CRAWL_HOUR,          # Giờ chạy (lấy từ biến môi trường)
        minute=Config.CRAWL_MINUTE,      # Phút chạy
        id='daily_facebook_crawl',       # ID để quản lý
        replace_existing=True
    )

    logger.info(f"🕒 Hệ thống đặt lịch đã khởi động (Lịch cào: {Config.CRAWL_HOUR}:{Config.CRAWL_MINUTE:02d} hàng ngày).")
    
    # Bắt đầu bộ đếm thời gian
    scheduler.start()