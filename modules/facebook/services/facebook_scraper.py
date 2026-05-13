import os
import time
import random
from dataclasses import dataclass
from typing import List, Optional
from playwright.sync_api import sync_playwright

from src.modules.crawl_fb.models.post import Post
from src.modules.facebook.services.facebook_auth import FacebookAuth
from src.modules.facebook.services.post_extractor import PostExtractor
from src.core.utils.facebook_parsers import classify_timestamp
from src.core.utils.logger import setup_logger
from src.modules.crawl_fb.models.GroupSummary import GroupSummary
from .human_behavior import HumanBehavior

logger = setup_logger(__name__)

# --- ĐỊNH NGHĨA CÁC CLASS DỮ LIỆU ---

@dataclass
class GroupTarget:
    """Entity để truyền dữ liệu đầu vào cho các Group cần cào"""
    name: str
    url: str


# ------------------------------------

class FacebookScraper:
    def __init__(self, config):
        self.config = config
        self.auth = FacebookAuth(config)
        
    def scrape_groups(
        self, 
        groups: List[GroupTarget], 
        custom_email: Optional[str] = None, 
        custom_pass: Optional[str] = None
    ) -> List[GroupSummary]:
        
        results: List[GroupSummary] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            # ── 1. LOGIC QUẢN LÝ CONTEXT (PHIÊN LÀM VIỆC) ─────────────────────
            if custom_email and custom_pass:
                # Có tài khoản khách -> Tạo phiên ẩn danh (trắng tinh)
                logger.info(f"🚀 Chế độ tài khoản khách ({custom_email}): Mở phiên ẩn danh.")
                context = browser.new_context()
            else:
                # Không có tài khoản khách -> Ưu tiên dùng file cookie mặc định
                logger.info("🚀 Chế độ mặc định: Ưu tiên sử dụng Cookie cũ.")
                default_state = self.auth.default_state_path
                if os.path.exists(default_state):
                    context = browser.new_context(storage_state=default_state)
                else:
                    context = browser.new_context()

            page = context.new_page()

            # ── 2. KIỂM TRA VÀ ĐĂNG NHẬP ──────────────────────────────────────
            logger.info("Khởi động trình duyệt và kiểm tra trạng thái đăng nhập...")
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60_000)
            HumanBehavior.act_like_reading(page)
            # Kiểm tra trang có ô nhập email không (nếu có nghĩa là chưa đăng nhập)
            if page.locator(self.config.AUTH_SELECTORS["email"]).count() > 0:
                logger.info("⚠️ Trình duyệt yêu cầu đăng nhập. Đang tiến hành...")
                # Truyền thẳng data của khách (hoặc None) vào, FacebookAuth sẽ tự quyết định
                # GÁN KẾT QUẢ VÀO BIẾN ĐỂ KIỂM TRA
                login_success = self.auth.login(
             
                    context=context, 
                    custom_email=custom_email, 
                    custom_pass=custom_pass
                )
                
                # NẾU LOGIN THẤT BẠI -> DỪNG TOÀN BỘ TIẾN TRÌNH
                if not login_success:
                    logger.error("🛑 Đăng nhập thất bại. Dừng tiến trình cào dữ liệu.")
                    browser.close()
                    raise ValueError("LOGIN_FAILED")
            else:
                logger.info("✅ Trình duyệt đã đăng nhập sẵn thông qua Cookie.")

            # ── 3. LẶP QUA MẢNG CÁC GROUP ĐỂ CÀO DATA ─────────────────────────
            for group in groups:
                logger.info(f"🚀 Bắt đầu cào group: {group.name} - {group.url}")
                try:
                    url = group.url
                    # Thêm sorting_setting=CHRONOLOGICAL nếu chưa có
                    if 'sorting_setting=CHRONOLOGICAL' not in url:
                        url += ('&' if '?' in url else '?') + 'sorting_setting=CHRONOLOGICAL'
                    
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    time.sleep(4)
                    
                    # tạo biến lưu danh sách các thông tin bài viết khi lấy dữ liệu
                    all_valid_posts: List[Post] = []
                    # tránh trùng lặp link bài viết
                    seen_urls = set()
                    # tạo biến khởi đầu cho việc đã loading bao nhiêu bài viết cũ liên tiếp
                    consecutive_old = 0
                    should_stop = False  # ← cờ dừng toàn bộ
                    safe_limit = self.config.SAFE_LIMIT
                    # [TÍNH NĂNG MỚI] Các biến để check cuộn đến cuối trang
                    last_scroll_height = 0
                    scroll_stuck_count = 0
                    MAX_STUCK_LIMIT = 3 # Cho phép cuộn hụt 3 lần trước khi kết luận là đã hết bài
                    # Vòng lặp cuộn cho từng Group
                    while not should_stop:
                        try:
                            # xem có bài viết nào không quá 5s mà ko có thì cho wa
                            page.wait_for_selector(self.config.FB_POST_CONTAINER, timeout=5_000)
                        except Exception:
                            pass
                        
                        # lấy all bài viết
                        blocks = page.locator(self.config.FB_POST_CONTAINER).all()
                        
                        
                        
                            
                        # lọc qua các bài viết để bóc tách dữ liệu bài viết
                        for block in blocks:
                            try:
                                # [BẢN VÁ QUAN TRỌNG TỪ SENIOR] 
                                # 1. Ép bài viết phải cuộn vào giữa màn hình
                                block.scroll_into_view_if_needed()
                                
                                # 2. Dừng 0.5s - 1s để Facebook kịp render DOM và số liệu
                                page.wait_for_timeout(500)
                                # lấy link bài viết và thời gian đăng bài
                                post_url, post_date = PostExtractor.get_info(block)

                                if not post_url or post_url in seen_urls:
                                    continue
                                
                                age = classify_timestamp(post_date)
                                if age == 'old':
                                    consecutive_old += 1
                                    logger.debug(f"[OLD {consecutive_old}/{self.config.MAX_OLD_POSTS_LIMIT}] {post_url}")
                                    if consecutive_old >= self.config.MAX_OLD_POSTS_LIMIT:
                                        should_stop = True
                                        break
                                    seen_urls.add(post_url)
                                    continue
                                elif age == 'unknown':
                                    pass
                                else:
                                    consecutive_old = 0
                                
                                seen_urls.add(post_url)
                                
                                # Bóc tách dữ liệu
                                stats      = PostExtractor.get_stats(block)
                                # score      = stats['reactions'] + stats['comments'] * 2 + stats['shares'] * 3
                                score      = stats['comments']
                                media_url  = PostExtractor.get_media(block, post_url)
                                image_urls = PostExtractor.get_images(block)
                                content    = PostExtractor.get_content(block)

                                post = Post(
                                    url=post_url,
                                    date=post_date,
                                    reactions=stats['reactions'],
                                    comments=stats['comments'],
                                    shares=stats['shares'],
                                    score=score,
                                    content=content,
                                    media_url=media_url,
                                    images=image_urls,
                                )
                                all_valid_posts.append(post)
                                logger.info(f"✅ [{group.name}] Bài số {len(all_valid_posts)} | score={score}")
                                
                                # kiểm tra đã lấy đc bao nhiêu bài viết nếu đủ bài viết theo yêu cầu thì dừng
                                if len(seen_urls) >= safe_limit:
                                    logger.info(f"✅ Đã đủ {safe_limit} bài cho {group.name}. Dừng.")
                                    should_stop = True
                                    break
                            except Exception as e:
                                logger.debug(f"[block error] {e}")
                                continue

                        if should_stop:
                            logger.info(f"🛑 Quá nhiều bài cũ liên tiếp ở {group.name}. Chuyển group tiếp theo.")
                            break
                        # [TÍNH NĂNG MỚI] Lấy chiều cao trang TRƯỚC khi cuộn
                        last_scroll_height = page.evaluate("document.documentElement.scrollHeight")
                        # [UPDATE] Luồng cuộn trang tự nhiên
                        # Lặp lại việc cuộn ngẫu nhiên 1-3 lần để giống người đang lướt feed
                        for _ in range(random.randint(1, 2)):
                           HumanBehavior.random_scroll(page, max_distance=self.config.SCROLL_DISTANCE)
                        if random.random() < 0.10:
                           HumanBehavior.act_like_reading(page)
                          # Delay chung trước vòng lặp tiếp theo bằng Gamma phân phối
                        HumanBehavior.gamma_delay(mean=self.config.SCROLL_SLEEP_MIN, shape=2)
                        # [TÍNH NĂNG MỚI] Lấy chiều cao trang SAU khi cuộn và chờ load
                        new_scroll_height = page.evaluate("document.documentElement.scrollHeight")
                        # So sánh chiều cao để xác định xem có tải thêm được data không
                        if new_scroll_height == last_scroll_height:
                            scroll_stuck_count += 1
                            logger.debug(f"⚠️ Chiều cao trang không đổi ({scroll_stuck_count}/{MAX_STUCK_LIMIT}). Đang ở cuối trang hoặc chờ load thêm...")
                            if scroll_stuck_count >= MAX_STUCK_LIMIT:
                                logger.info(f"🛑 Đã chạm đáy Group {group.name} (không có thêm bài mới). Chuyển group tiếp theo.")
                                should_stop = True
                                break # Thoát luôn khỏi vòng lặp while để đi qua bước tổng hợp
                        else:
                            scroll_stuck_count = 0 # Reset bộ đếm nếu trang được mở rộng thành công
                    # 3. Tổng hợp dữ liệu cho Group hiện tại
                    sorted_posts = sorted(all_valid_posts, key=lambda x: x.score, reverse=True)
                    hot_post = sorted_posts[0] if sorted_posts else None

                    summary = GroupSummary(
                        group_name=group.name,
                        total_posts_24h=len(all_valid_posts),
                        hot_post=hot_post
                    )
                    results.append(summary)
                    logger.info(f"📊 Đã tổng hợp xong {group.name}: {summary.total_posts_24h} bài.")

                except Exception as e:
                    logger.error(f"❌ Lỗi khi cào group {group.name}: {e}")
                    # Thêm một bản ghi lỗi để mảng output không bị thiếu group
                    results.append(GroupSummary(group_name=group.name, total_posts_24h=0, hot_post=None))
                    continue
                
            # [THÊM ĐOẠN CODE NÀY ĐỂ CẬP NHẬT COOKIE]
            try:
                # Nếu đang dùng file default_state (chứ không phải login chay)
                if not (custom_email and custom_pass) and hasattr(self.auth, 'default_state_path'):
                    # Trích xuất toàn bộ cookie & local storage hiện tại và ghi đè vào file
                    context.storage_state(path=self.auth.default_state_path)
                    logger.info("💾 Đã cập nhật và lưu lại Cookie/Session mới thành công.")
            except Exception as e:
                logger.error(f"❌ Lỗi khi lưu lại trạng thái phiên: {e}")
            browser.close()
            return results