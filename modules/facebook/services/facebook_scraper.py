import time
from dataclasses import dataclass
from typing import List, Optional
from src.modules.facebook.services.post_extractor import PostExtractor
from playwright.sync_api import sync_playwright

from src.modules.crawl_fb.models.post import Post
from src.modules.facebook.services.facebook_auth import FacebookAuth
from src.core.utils.logger import setup_logger
from src.modules.crawl_fb.models.GroupSummary import GroupSummary
from .human_behavior import HumanBehavior

logger = setup_logger(__name__)


@dataclass
class GroupTarget:
    """Entity để truyền dữ liệu đầu vào cho các Group cần cào"""
    name: str
    url: str


class FacebookScraper:
    def __init__(self, config):
        self.config = config
        self.auth = FacebookAuth(config)

    def _try_get_post_url_from_comment(self, page, content: str, comments: int) -> str:
        try:
            if not content:
                return ""

            needle = content[:40]
            comment_text = str(comments)

            clicked = page.evaluate("""
            ({ needle, commentText }) => {
            const matches = [...document.querySelectorAll("div, span, a")]
                .filter(el => (el.innerText || "").includes(needle))
                .sort((a, b) => (a.innerText || "").length - (b.innerText || "").length);

            for (const el of matches) {
                let box = el;

                for (let level = 0; level < 35; level++) {
                if (!box.parentElement) break;
                box = box.parentElement;

                const text = box.innerText || "";
                if (!text.includes(needle)) continue;

                const candidates = [...box.querySelectorAll("span, div, a")]
                    .filter(x => {
                    const t = (x.innerText || "").trim();
                    const r = x.getBoundingClientRect();

                    return (
                        t === commentText &&
                        r.width > 0 &&
                        r.height > 0
                    );
                    });

                console.log("COMMENT CANDIDATES =", candidates.length, commentText);

                // Ưu tiên candidate nằm thấp hơn content, thường là hàng reaction/comment/share
                const target = candidates
                    .sort((a, b) => b.getBoundingClientRect().top - a.getBoundingClientRect().top)[0];

                if (target) {
                    target.scrollIntoView({ block: "center" });
                    target.click();
                    return true;
                }
                }
            }

            return false;
            }
            """, {
                "needle": needle,
                "commentText": comment_text
            })

            print("CLICK COMMENT NUMBER =", clicked, "COMMENT =", comment_text)

            if not clicked:
                return ""

            page.wait_for_timeout(3000)

            url = page.evaluate("""
            () => {
            const root = document.querySelector('[role="dialog"]') || document.body;

            const hrefs = [...root.querySelectorAll('a[href]')]
                .map(a => a.href)
                .filter(h =>
                h.includes("/groups/") &&
                h.includes("/posts/")
                );

            for (const href of hrefs) {
                const m = href.match(/\\/groups\\/([^/?#]+)\\/posts\\/(\\d+)/);
                if (m) {
                return `https://www.facebook.com/groups/${m[1]}/posts/${m[2]}/`;
                }
            }

            return "";
            }
            """)

            print("COMMENT URL AFTER CLICK =", url)

            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
            except Exception:
                pass

            return url or ""

        except Exception as e:
            print("GET COMMENT URL ERROR =", e)
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
            except Exception:
                pass
            return ""
        
    def scrape_groups(
        self,
        groups: List[GroupTarget],
        custom_email: Optional[str] = None,
        custom_pass: Optional[str] = None
    ) -> List[GroupSummary]:

        results: List[GroupSummary] = []

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir="fb_profile",
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ],
                viewport=None,
            )

            page = context.new_page()

            try:
                # ── 1. KIỂM TRA ĐĂNG NHẬP ─────────────────────────────────────
                logger.info("Khởi động trình duyệt và kiểm tra trạng thái đăng nhập...")

                page.goto(
                    "https://www.facebook.com/",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )

                print("CURRENT URL =", page.url)
                print("LOGIN INPUT EXISTS =", page.locator('input[name="email"]').count())
                print("FEED EXISTS =", page.locator('div[role="feed"]').count())
                print(
                    "GROUP TITLE =",
                    page.locator("h1").inner_text()
                    if page.locator("h1").count()
                    else "NO TITLE",
                )

                HumanBehavior.act_like_reading(page)

                if page.locator(self.config.AUTH_SELECTORS["email"]).count() > 0:
                    logger.info("⚠️ Trình duyệt yêu cầu đăng nhập. Đang tiến hành...")

                    login_page = self.auth.login(
                        context=context,
                        custom_email=custom_email,
                        custom_pass=custom_pass,
                    )

                    if not login_page:
                        logger.error("🛑 Đăng nhập thất bại. Dừng tiến trình cào dữ liệu.")
                        raise ValueError("LOGIN_FAILED")

                    page = login_page
                else:
                    logger.info("✅ Trình duyệt đã đăng nhập sẵn thông qua Cookie.")

                # ── 2. CÀO TỪNG GROUP ─────────────────────────────────────────
                for group in groups:
                    logger.info(f"🚀 Bắt đầu cào group: {group.name} - {group.url}")

                    try:
                        url = group.url

                        if "sorting_setting=CHRONOLOGICAL" not in url:
                            url += ("&" if "?" in url else "?") + "sorting_setting=CHRONOLOGICAL"

                        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                        page.wait_for_timeout(8000)

                        print("AFTER GROUP URL =", page.url)
                        print(
                            "H1 =",
                            page.locator("h1").inner_text()
                            if page.locator("h1").count()
                            else "NO H1",
                        )

                        body_text = page.locator("body").inner_text(timeout=5000)
                        print("BODY PREVIEW =", body_text[:1500])

                        seen_keys = set()
                        all_feed_posts = []
                        

                        # ── 3. SCROLL VÀ LẤY POST TỪ BODY TEXT ────────────────
                        MAX_ROUNDS = 5

                        for round_idx in range(MAX_ROUNDS):
                            feed_posts = page.evaluate(
                                """
                                () => {
                                  const lines = (document.body.innerText || "")
                                    .split("\\n")
                                    .map(x => x.trim())
                                    .filter(Boolean);

                                  const badAuthors = new Set([
                                    "Tìm bạn bè",
                                    "Nhóm của Giáp Đức Thắng",
                                    "Cộng đồng n8n AI Automation Việt Nam",
                                    "Nhóm Công khai",
                                    "Tham gia nhóm",
                                    "Chia sẻ",
                                    "Xem thêm",
                                    "Giới thiệu",
                                    "Thảo luận",
                                    "Đáng chú ý",
                                    "Mọi người",
                                    "Sự kiện",
                                    "File phương tiện",
                                    "File",
                                    "Bạn viết gì đi...",
                                    "Bài viết ẩn danh",
                                    "Cảm xúc/hoạt động",
                                    "Thăm dò ý kiến",
                                    "Facebook",
                                    "Huy hiệu nội dung đáng chú ý",
                                    "5 mục mới",
                                    "Người tham gia ẩn danh",
                                    "Quản trị viên",
                                    "Người kiểm duyệt",
                                    "Theo dõi"
                                  ]);

                                  function isPossibleAuthor(x) {
                                    return (
                                      x &&
                                      x.length >= 3 &&
                                      x.length <= 60 &&
                                      !badAuthors.has(x) &&
                                      !/^\\d+$/.test(x) &&
                                      !x.includes("·") &&
                                      !x.includes("thành viên")
                                    );
                                  }

                                  function isContentLine(x) {
                                    return (
                                      x &&
                                      x.length > 20 &&
                                      !badAuthors.has(x) &&
                                      !x.includes("Facebook") &&
                                      !/^\\d+$/.test(x) &&
                                      x !== "·"
                                    );
                                  }

                                  const posts = [];

                                  for (let authorIndex = 0; authorIndex < lines.length; authorIndex++) {
                                    const author = lines[authorIndex];

                                    if (!isPossibleAuthor(author)) continue;

                                    const contentIndex = lines.findIndex((x, i) =>
                                      i > authorIndex &&
                                      i < authorIndex + 80 &&
                                      isContentLine(x)
                                    );

                                    if (contentIndex === -1) continue;
                                    

                                    for (
                                      let i = contentIndex + 1;
                                      i < Math.min(lines.length - 2, contentIndex + 20);
                                      i++
                                    ) {
                                      if (
                                        /^\\d+$/.test(lines[i]) &&
                                        /^\\d+$/.test(lines[i + 1]) &&
                                        /^\\d+$/.test(lines[i + 2])
                                      ) {
                                        posts.push({
                                          author,
                                          content: lines[contentIndex],
                                          reactions: Number(lines[i]),
                                          comments: Number(lines[i + 1]),
                                          shares: Number(lines[i + 2]),
                                          score:
                                            Number(lines[i]) +
                                            Number(lines[i + 1]) +
                                            Number(lines[i + 2])
                                        });

                                        // bỏ qua phần còn lại của bài này
                                        authorIndex = i + 2;
                                        break;
                                      }
                                    }
                                  }

                                  const seen = new Set();

                                  return posts.filter(p => {
                                    const key = p.author + "|" + p.content;

                                    if (seen.has(key)) return false;

                                    seen.add(key);
                                    return true;
                                  });
                                }
                                """
                            )

                            new_count = 0

                            for p_item in feed_posts:
                                key = p_item["author"] + "|" + p_item["content"]

                                if key in seen_keys:
                                    continue

                                p_item["url"] = ""

                                seen_keys.add(key)
                                all_feed_posts.append(p_item)
                                new_count += 1

                            print(f"ROUND {round_idx + 1} NEW =", new_count)
                            print("TOTAL =", len(all_feed_posts))

                            # Chỉ scroll nếu chưa phải vòng cuối
                            # Chỉ scroll nếu chưa phải vòng cuối
                            if round_idx < MAX_ROUNDS - 1:
                                page.mouse.wheel(0, 2500)
                                page.wait_for_timeout(4000)

                        print("ALL FEED POSTS =", all_feed_posts)

                        # ── 4. CONVERT SANG MODEL POST ───────────────────────
                        all_valid_posts: List[Post] = []

                        for item in all_feed_posts:
                            post = Post(
                                url=item.get("url", ""),     # hiện tại chưa map URL
                                date="",     # hiện tại chưa lọc timestamp 24h
                                reactions=item["reactions"],
                                comments=item["comments"],
                                shares=item["shares"],
                                score=item["score"],
                                content=item["content"],
                                media_url=None,
                                images=[],
                            )

                            all_valid_posts.append(post)

                        sorted_posts = sorted(
                            all_valid_posts,
                            key=lambda x: x.score,
                            reverse=True,
                        )

                        hot_post = sorted_posts[0] if sorted_posts else None

                        if hot_post:
                            hot_url = self._try_get_post_url_from_comment(
                                page,
                                hot_post.content,
                                hot_post.comments
                            )
                            hot_post.url = hot_url
                            print("HOT POST URL =", hot_url)


                        summary = GroupSummary(
                            group_name=group.name,
                            total_posts_24h=len(all_valid_posts),
                            hot_post=hot_post,
                        )

                        results.append(summary)

                        print("SUMMARY =", summary)
                        logger.info(
                            f"📊 Đã tổng hợp xong {group.name}: "
                            f"{summary.total_posts_24h} bài."
                        )

                    except Exception as e:
                        logger.error(f"❌ Lỗi khi cào group {group.name}: {e}")

                        results.append(
                            GroupSummary(
                                group_name=group.name,
                                total_posts_24h=0,
                                hot_post=None,
                            )
                        )

                        continue

                # ── 5. LƯU COOKIE ───────────────────────────────────────────
                try:
                    if not (custom_email and custom_pass) and hasattr(
                        self.auth,
                        "default_state_path",
                    ):
                        context.storage_state(path=self.auth.default_state_path)
                        logger.info("💾 Đã cập nhật và lưu lại Cookie/Session mới thành công.")
                except Exception as e:
                    logger.error(f"❌ Lỗi khi lưu lại trạng thái phiên: {e}")

                return results

            finally:
                context.close()