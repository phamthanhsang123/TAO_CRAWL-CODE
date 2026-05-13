import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from src.core.config.env import Config
from fastapi.middleware.cors import CORSMiddleware  # BƯỚC 1: Import thư viện CORS
from src.jobs.daily_crawl_job import setup_and_start_jobs
from src.modules.api_router.index import api_router

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
   

    setup_and_start_jobs()
    # Quan trọng: Đảm bảo log này hiện ra thì mới được gọi API
    logger.info("🚀 API đã sẵn sàng nhận request!")
    yield
    logger.info("Dọn dẹp hệ thống khi tắt server...")

def create_app() -> FastAPI:
    app = FastAPI(
        title="Crawler Server API",
        version="1.0.0",
        lifespan=lifespan
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"], # Thay đổi port nếu Frontend của bạn chạy cổng khác (hoặc dùng ["*"] để cho phép tất cả)
        allow_credentials=True,
        allow_methods=["*"], # QUAN TRỌNG NHẤT: Dòng này sẽ sửa lỗi 405 OPTIONS
        allow_headers=["*"],
    )

    # Đăng ký toàn bộ API Route vào App
    app.include_router(api_router, prefix="/api/v1")
    
    return app

app = create_app()