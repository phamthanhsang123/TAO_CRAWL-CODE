import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from src.core.config.env import Config
from src.modules.crawl_fb.models.GroupSummary import GroupSummary
from datetime import datetime
from src.core.config.env import Config
# Khởi tạo logger cho module này
logger = logging.getLogger(__name__)

@dataclass
class GoogleSheetRow:
    ngay_crawl: str
    name_group: str
    tong_bai_viet: int
    link_post: str
    gio_dang: str
    noi_dung: str
    diem: float
    like: int
    binh_luan: int
    chia_se: int
    link_video: str
    link_anh: str

    def to_sheet_dict(self) -> Dict[str, Any]:
        """Hàm này giúp map tên biến thành tên cột có khoảng trắng trên Google Sheet"""
        return {
            "Ngày Crawl": self.ngay_crawl,
            "Name Group": self.name_group,
            "tổng bài viết": self.tong_bai_viet,
            "Link post": self.link_post,
            "Giờ đăng": self.gio_dang,
            "Nội dung": self.noi_dung,
            "Điểm": self.diem,
            "Like": self.like,
            "Bình luận": self.binh_luan,
            "Chia sẽ": self.chia_se,
            "Link video": self.link_video,
            "Link ảnh": self.link_anh
        }


class GoogleApiService:
    SHEET_MIME_TYPE = 'application/vnd.google-apps.spreadsheet'
    DEFAULT_SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive" 
    ]

    def __init__(self, credentials_path: str = Config.GOOGLE_CREDENTIALS_PATH):
        if not credentials_path:
            raise ValueError("Đường dẫn credentials_path không được để trống.")

        try:
            self.creds = Credentials.from_service_account_file(
                credentials_path, 
                scopes=self.DEFAULT_SCOPES
            )
            self.sheets_client = gspread.authorize(self.creds)
            self.drive_service = build("drive", "v3", credentials=self.creds)
            logger.info("Khởi tạo GoogleApiService thành công.")
            
        except Exception as e:
            logger.error(f"Lỗi xác thực Google API: {e}", exc_info=True)
            raise

    def find_sheets_in_folder(self, folder_id: str) -> List[Dict[str, str]]:
        try:
            query = f"'{folder_id}' in parents and mimeType = '{self.SHEET_MIME_TYPE}'"
            results = self.drive_service.files().list(
                q=query, 
                fields="files(id, name)"
            ).execute()
            
            files = results.get("files", [])
            logger.info(f"Tìm thấy {len(files)} file Sheets trong thư mục {folder_id}.")
            return files
            
        except HttpError as e:
            logger.error(f"Lỗi API khi tìm file trong Drive: {e}")
            return []
        except Exception as e:
            logger.error(f"Lỗi hệ thống khi tìm file: {e}")
            return []

    # Đổi Type Hint thành List[Dict[str, Any]] (Danh sách các objects/dictionaries)
    def get_sheet_data(self, spreadsheet_id: str, sheet_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lấy dữ liệu từ một Sheet cụ thể bằng ID.
        Trả về danh sách các Dictionary, với key là tiêu đề cột (dòng 1) và value là giá trị tương ứng.
        """
        try:
            sheet = self.sheets_client.open_by_key(spreadsheet_id)
            worksheet = sheet.worksheet(sheet_name) if sheet_name else sheet.get_worksheet(0)
            
            # SỬ DỤNG get_all_records() THAY VÌ get_all_values()
            # Hàm này tự động lấy dòng đầu làm key: {'STT': 1, 'Tên Group': 'nguyên', 'URL': '...'}
            data = worksheet.get_all_records()
            logger.info(f"Đã tải {len(data)} bản ghi từ Sheet ID: {spreadsheet_id[:10]}...")
            return data
            
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(f"Không tìm thấy Spreadsheet với ID: {spreadsheet_id}")
            return []
        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"Không tìm thấy Tab tên: {sheet_name} trong Spreadsheet.")
            return []
        except Exception as e:
            logger.error(f"Lỗi không xác định khi tải dữ liệu Sheet: {e}", exc_info=True)
            return []
        
    def transform_to_sheet_format(self, scraped_data: List[GroupSummary]) -> List[Dict[str, Any]]:
        """
        Chuyển đổi dữ liệu từ dạng GroupSummary (object) sang dạng chuẩn (Dictionary) cho Google Sheets.
        Hàm này nằm trong class nên có thêm 'self'.
        """
        formatted_data = []
        # Tự động lấy ngày hôm nay làm Ngày Crawl (Format: YYYY-MM-DD)
        current_date = datetime.now().strftime("%Y-%m-%d")

        for item in scraped_data:
            post = item.hot_post
            
            # Xử lý giờ đăng
            post_time = post.date 
            
            # Biến list ảnh thành 1 chuỗi string phân cách bằng dấu phẩy VÀ xuống dòng (\n)
            image_links = ",\n".join(post.images) if post.images else "Không có hình ảnh"

            row = {
                "Ngày Crawl": current_date,
                "Name Group": item.group_name,
                "tổng bài viết": item.total_posts_24h,
                "Link post": post.url,
                "Giờ đăng": post_time,
                "Nội dung": post.content if post.content else "Không có nội dung",
                "Điểm": post.score,
                "Like": post.reactions,
                "Bình luận": post.comments,
                "Chia sẽ": post.shares, # Đúng chính tả "Chia sẽ" của header trên file
                "Link video": post.media_url if post.media_url else "Không có video", 
                "Link ảnh": image_links
            }
            formatted_data.append(row)
            
        return formatted_data
    
    # hàm thêm vào
    def append_data_to_sheet(self, data: List[GroupSummary], spreadsheet_id: str=Config.SPREADSHEET_ID, sheet_name: Optional[str] = Config.GOOGLE_SHEET_NAME_APPEND) -> bool:
        """
        Thêm dữ liệu mới vào dòng trống cuối cùng của Sheet.
        data: Nhận trực tiếp danh sách các object GroupSummary.
        """
        if not data:
            logger.warning("Không có dữ liệu để insert.")
            return False

        try:
            # 1. GỌI HÀM CHUYỂN ĐỔI Ở ĐÂY NÈ
            formatted_data = self.transform_to_sheet_format(data)

            # 2. Mở spreadsheet và worksheet
            sheet = self.sheets_client.open_by_key(spreadsheet_id)
            worksheet = sheet.worksheet(sheet_name) if sheet_name else sheet.get_worksheet(0)
            
            # 3. Lấy dòng tiêu đề (header) từ dòng 1 để map dữ liệu cho đúng thứ tự cột
            headers = worksheet.row_values(1)
            
            if not headers:
                logger.error("Sheet chưa có tiêu đề ở dòng 1. Không thể map dữ liệu.")
                return False

            # 4. Chuyển đổi List[Dict] thành List[List] dựa trên thứ tự của headers trên Sheet
            rows_to_insert = []
            for item in formatted_data: # Nhớ duyệt qua list đã format nhé
                # Nếu dict không có key tương ứng với header, gán giá trị rỗng ("")
                row = [item.get(header, "") for header in headers]
                rows_to_insert.append(row)
            
            # 5. Thực hiện chèn nhiều dòng cùng lúc để tối ưu tốc độ
            worksheet.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
            
            logger.info(f"Đã chèn thành công {len(rows_to_insert)} dòng vào Sheet ID: {spreadsheet_id[:10]}...")
            return 
            
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(f"Không tìm thấy Spreadsheet với ID: {spreadsheet_id}")
            return 
        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"Không tìm thấy Tab tên: {sheet_name} trong Spreadsheet.")
            return 
        except Exception as e:
            logger.error(f"Lỗi khi insert dữ liệu vào Sheet: {e}", exc_info=True)
            return 

     
    

