# src/modules/crawl/service/crawl_service.py
from src.modules.crawl_fb.schemas.crawl_schema import CrawlTriggerRequest, CrawlPayload
from typing import List
from src.modules.facebook.services.facebook_scraper import FacebookScraper
from src.core.config.env import Config
from src.modules.crawl_fb.models.GroupSummary import GroupSummary
from src.modules.telegram.services.telegram_service import TelegramService
from fastapi import HTTPException, status 
import logging
from src.modules.gg_sheet.services.google_sheets import GoogleApiService
logger = logging.getLogger(__name__)

class CrawlService:
    def CrawlDataGroupFB(self, payload: CrawlPayload):
        scraper = FacebookScraper(Config)
        telegram = TelegramService()
        ggSheet=GoogleApiService()
        
        try:
            # 1. BẮT ĐẦU CÀO DỮ LIỆU
            daily_summary_report: List[GroupSummary] = scraper.scrape_groups(
                groups=payload.groups,
                custom_email=payload.tkFB.useName,
                custom_pass=payload.tkFB.password
            )
             
            # 2. XỬ LÝ TRƯỜNG HỢP: LOGIN THÀNH CÔNG (Không bị văng lỗi)
            if daily_summary_report:
                # CÓ DỮ LIỆU: Gửi báo cáo bình thường
                ggSheet.append_data_to_sheet(data=daily_summary_report)
                mes = telegram.format_daily_telegram_report(summaries=daily_summary_report)
                telegram.send_message(mes)
                return {"status": "success", "message": "Cào dữ liệu hoàn tất."}
            else:
                # KHÔNG CÓ DỮ LIỆU (Do group chết, không có bài mới...)
                empty_message = (
                    "ℹ️ *Báo cáo Crawler*\n"
                    "Đăng nhập thành công, nhưng không thu được bài viết nào "
                    "đạt tiêu chuẩn trong các group này."
                )
                telegram.send_message(empty_message)
                return {"status": "success", "message": "Hoàn tất nhưng không có dữ liệu."}
                
        # 3. XỬ LÝ TRƯỜNG HỢP: SAI MẬT KHẨU HOẶC CHECKPOINT
        except ValueError as e:
            if str(e) == "LOGIN_FAILED":
                alert_msg = (
                    "🚨 *CẢNH BÁO CRAWLER: LỖI ĐĂNG NHẬP*\n"
                    f"Tài khoản: `{payload.tkFB.useName if payload.tkFB else 'mặc định'}`\n"
                    "Nguyên nhân: Sai mật khẩu, dính Checkpoint hoặc yêu cầu mã 2FA. "
                    "Vui lòng kiểm tra lại tài khoản này!"
                )
                telegram.send_message(alert_msg)
                return {"status": "error", "message": "Đăng nhập thất bại."}
            else:
                raise e # Nếu là ValueError khác thì ném tiếp

        # 4. XỬ LÝ TRƯỜNG HỢP: CRASH, MẤT MẠNG, CHẾT TRÌNH DUYỆT BẤT THỜ
        except Exception as e:
            logger.error(f"Lỗi hệ thống bất ngờ: {e}")
            error_msg = f"❌ *Lỗi hệ thống Crawler*\nNgoại lệ không xác định: {str(e)[:100]}..."
            telegram.send_message(error_msg)
            return {"status": "error", "message": "Lỗi hệ thống."}



    def FetchDataDirectly(self, payload: CrawlPayload):
        scraper = FacebookScraper(Config)
        ggSheet=GoogleApiService()
        try:
            scraped_data: List[GroupSummary] = scraper.scrape_groups(
                groups=payload.groups,
                custom_email=payload.tkFB.useName,
                custom_pass=payload.tkFB.password
            )
             
            # Trường hợp 1: Chạy trót lọt (Có hoặc Không có data đều trả về 200 OK)
            # Lưu ý: Trả mảng rỗng [] không phải là lỗi 404 (Not Found). Resource vẫn tồn tại, chỉ là không có phần tử nào.
            if scraped_data:
                ggSheet.append_data_to_sheet(data=scraped_data)
                return {"status": "success", "message": "Cào thành công.", "data": scraped_data}
            else:
                return {"status": "success", "message": "Không có bài viết mới.", "data": []}

        # Trường hợp 2: Lỗi Đăng nhập -> Trả về mã 401 (Unauthorized)
        except ValueError as e:
            if str(e) == "LOGIN_FAILED":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Sai tài khoản, mật khẩu hoặc dính Checkpoint."
                )
            
            # Nếu là ValueError khác do user gửi sai data -> Trả về 400 (Bad Request)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

        # Trường hợp 3: Lỗi hệ thống bất ngờ -> Trả về mã 500 (Internal Server Error)
        except Exception as e:
            logger.error(f"Lỗi hệ thống: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Hệ thống Crawler gặp sự cố: {str(e)}"
            )