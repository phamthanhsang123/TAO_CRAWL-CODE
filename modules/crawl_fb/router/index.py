# src/modules/crawl/route/crawl_route.py
from fastapi import APIRouter, Depends, status,BackgroundTasks
from typing import List,Optional
from pydantic import BaseModel

# 1. Import Schema (để validate dữ liệu đầu vào)
from src.modules.crawl_fb.schemas.crawl_schema import CrawlPayload

# 2. Import Service (chứa logic xử lý)
from src.modules.crawl_fb.services.index import CrawlService



crawl_fb_router = APIRouter(tags=["Crawler Management FB"])


# ── ĐỊNH NGHĨA DEPENDENCY ─────────────────────────────────────────────────────

def get_crawl_service():
    """
    Hàm này chịu trách nhiệm khởi tạo class CrawlService.
    Nhờ có nó, FastAPI sẽ tự động tạo một phiên bản Service mỗi khi có Request tới.
    """
    return CrawlService()



# Route POST để kích hoạt cào dữ liệu
@crawl_fb_router.post("/CrawlDataGroupFB", status_code=status.HTTP_200_OK)
def trigger_crawl_fb_api(
    # FastAPI tự động hiểu payload là một mảng JSON từ request body
    payload: CrawlPayload, 
    background_tasks: BackgroundTasks,
    # FastAPI tự động gọi get_crawl_service() và nhét kết quả vào biến service
    service: CrawlService = Depends(get_crawl_service)
):
    """
    API kích hoạt tiến trình cào dữ liệu Facebook thủ công chạy ngầm.
    """
    # 2. Quăng cái hàm cào dữ liệu vào background task. 
    # Lưu ý: Chỉ truyền tên hàm (không có dấu ngoặc tròn) và tham số theo sau.
    background_tasks.add_task(service.CrawlDataGroupFB, payload)
    
    # 3. Trả về kết quả ngay lập tức cho ngrok và Google Apps Script
    return {
        "status": "success",
        "message": "Đã nhận lệnh! Bot đang tiến hành cào dữ liệu ngầm trên server."
    }

# ── ROUTER 2: FE YÊU CẦU CÀO VÀ TRẢ DỮ LIỆU TRỰC TIẾP ────────────────────────
@crawl_fb_router.post("/CrawlFbForFE", status_code=status.HTTP_200_OK)
def fetch_data_direct_for_fe(
    payload: CrawlPayload, 
    service: CrawlService = Depends(get_crawl_service)
):
    """
    API dành cho Frontend: 
    Nhận tài khoản FB + danh sách group -> Cào dữ liệu -> Trả thẳng kết quả về cho FE.
    """
    # Gọi một hàm mới trong Service chuyên dùng để trả data cho FE
    return service.FetchDataDirectly(payload)
