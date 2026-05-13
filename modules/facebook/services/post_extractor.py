from typing import Tuple, Optional, Dict
from src.modules.facebook.constants.facebook_regex import POST_URL_RE, VIDEO_URL_RE,NON_REACTION_KEYWORDS, COMMENT_RE, SHARE_RE, REACTION_NUM_RE
from src.core.utils.facebook_parsers import clean_post_url, extract_ts_hint, classify_timestamp
from src.core.utils.date_parser import parse_interactions
from typing import List
class PostExtractor:
    """Class chuyên chịu trách nhiệm đọc hiểu các thẻ HTML/DOM của Facebook"""
    # nói chung chuyên tóc tách dữ liệu từ bài viết


    # hàm chuyên bóc tách lấy link bài viết và thời gian đăng bài viết đó 
    @staticmethod
    def get_info(element) -> Tuple[Optional[str], str]:
           """Tương tác DOM: Bóc URL và thời gian từ Element block."""
           url, post_date = None, ""
           try:
              all_links = element.locator('a[href]').all()

        # ── BƯỚC 1: Tìm URL bài viết ─────────────────────────────────────
              for link in all_links:
                  href = link.get_attribute('href') or ''
                  if '/posts/' not in href and '/permalink/' not in href:
                     continue
                  if not POST_URL_RE.search(href):
                     continue
                  candidate = clean_post_url(href)
                  if candidate:
                     url = candidate
                     break  # Lấy được URL rồi → dừng

              if not url:
                return None, ""

        # ── BƯỚC 2: Tìm timestamp từ TẤT CẢ thẻ <a> trong block ─────────
        # Facebook để timestamp ở thẻ <a> riêng, thường có aria-label hoặc
        # inner_text dạng "1 giờ", "Hôm qua", "20 tháng 4"...
              for link in all_links:
                  raw = (link.get_attribute('aria-label') or link.inner_text() or '').strip()
                  if not raw:
                    continue

                  ts = extract_ts_hint(raw)
                  if classify_timestamp(ts) != 'unknown':
                    post_date = ts
                    break  # Lấy được timestamp rõ ràng → dừng

           except Exception:
             pass

           return url, post_date
    
    # hàm lấy link video nếu có
    @staticmethod
    def get_media(element, post_url: str) -> Optional[str]:
        """Tương tác DOM: Bóc tách link Video/Reel nếu có trong bài viết (Bao gồm cả bài Share)."""
        try:
            #  BƯỚC 1: Quét bề nổi - Dùng Regex tìm các link <a> hiển nhiên
            for link in element.locator('a[href]').all():
                href = link.get_attribute('href') or ''
                if VIDEO_URL_RE.search(href):
                    return clean_post_url(href)

            # BƯỚC 2:  Đào sâu bằng JS nhưng dùng Regex Python để kiểm duyệt
            if element.locator('video').count() > 0:
                
                # Dùng JS để vơ vét tất cả link tiềm năng đang bị giấu kín trong DOM
                candidate_links = element.evaluate("""
                    (el) => {
                        let links = [];
                        
                        // 1. Quét vét cạn thẻ <a> (kể cả những thẻ bị FB dùng CSS ẩn đi)
                        for (const a of el.querySelectorAll('a[href]')) {
                            links.push(a.href || a.getAttribute('href') || '');
                        }
                        
                        // 2. Mò mẫm trong các Data Attribute (Nơi FB giấu ID video)
                        for (const node of el.querySelectorAll('[data-video-id]')) {
                            const vid = node.getAttribute('data-video-id');
                            if (vid) links.push(`https://www.facebook.com/watch?v=${vid}`);
                        }
                        
                        return links;
                    }
                """)

                # Mang mảng link (candidate_links) về lại Python
                # Áp dụng ĐÚNG biến VIDEO_URL_RE để quét từng link một
                if candidate_links:
                    for href in candidate_links:
                        if VIDEO_URL_RE.search(href):
                            return clean_post_url(href)

                # BƯỚC 3: Cùng đường (có video nhưng không bóc được) - Lấy tạm link bài viết (post_url) làm link video
                return clean_post_url(post_url) if post_url else None

        except Exception:
            pass
            
        return None     
                    
    #  hàm lấy danh sách các ảnh nếu có
    @staticmethod
    def get_images(element) -> List[str]:
        """Tương tác DOM: Trích xuất danh sách các link ảnh đính kèm trong bài."""
        images = []
        try:
            # Nhắm thẳng vào thẻ <img>, không lấy thẻ <a>
            for img in element.locator('img').all():
                src = img.get_attribute('src') or ''
                
                # BỘ LỌC ẢNH RÁC:
                # 1. Ảnh thực tế của FB luôn được host trên server 'scontent'
                # 2. Loại bỏ các icon cảm xúc (thường có kích thước siêu nhỏ hoặc chứa chữ emoji/images)
                if 'scontent' in src and '/emoji/' not in src and '/images/locales/' not in src:
                    # Có thể lọc thêm bằng kích thước nếu cần (VD: chỉ lấy ảnh to)
                    width = img.get_attribute('width')
                    if width and int(width) < 100:
                        continue # Bỏ qua ảnh có chiều rộng bé hơn 100px (avatar/icon)
                        
                    images.append(src)
        except Exception:
            pass
            
        # Dùng set() để xóa các link ảnh bị trùng lặp trong cùng 1 bài, sau đó ép lại thành list
        return list(set(images))
    
   # hàm lấy các lượng tương tác , bình luận và lượt chia sẽ
    @staticmethod
    def get_stats(element) -> Dict[str, int]:
        reactions = 0
        comments  = 0
        shares    = 0
        seen: set = set()
        # kiểm tra xem nằm ở đâu
        # # DEBUG: thêm tạm vào đầu hàm
        # try:
        #     for btn in element.locator('div[role="button"], span[role="button"]').all():
        #        txt = (btn.inner_text() or '').strip()
        #        if txt:
        #            print(f"[DEBUG BTN] repr={repr(txt[:80])}")
        #     for node in element.locator('[aria-label]').all():
        #          label = (node.get_attribute('aria-label') or '').strip()
        #          if label:
        #             print(f"[DEBUG ARIA] repr={repr(label[:80])}")
        # except:
        #     pass

        # ── REACTIONS: Giữ nguyên logic cũ qua aria-label ─────────────────
        try:
            for node in element.locator('[aria-label]').all():
                label = (node.get_attribute('aria-label') or '').strip()
                if not label or label in seen:
                    continue
                seen.add(label)
                ll = label.lower()

                if NON_REACTION_KEYWORDS.search(ll):
                    continue

                if 'người' in ll:
                    m = REACTION_NUM_RE.search(label)
                    if m:
                        val = parse_interactions(m.group(1))
                        if val > 0:
                            reactions += val
        except Exception:
            pass

        # ── COMMENTS + SHARES: đọc 3 số tương tác theo thứ tự hiển thị ──────
        try:
            action_bar = element.evaluate("""
                (el) => {
                    const results = { comments: 0, shares: 0 };
                    const numericRe = /^[\\d][\\d.,]*\\s*[KkMmTtBb]?$/;
                    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
                    const nums = [];
                    const seen = new Set();

                    while (walker.nextNode()) {
                        const txt = (walker.currentNode.nodeValue || '').trim();
                        if (!numericRe.test(txt)) continue;

                        const parent = walker.currentNode.parentElement;
                        if (!parent) continue;
                        const style = window.getComputedStyle(parent);
                        if (style.display === 'none' || style.visibility === 'hidden') continue;

                        const key = `${txt}|${parent.tagName}|${parent.className}`;
                        if (seen.has(key)) continue;
                        seen.add(key);
                        nums.push(txt);
                    }

                    // Mẫu UI phổ biến: [reactions, comments, shares]
                    if (nums.length >= 3) {
                        results.comments = nums[1] || 0;
                        results.shares = nums[2] || 0;
                    }

                    return results;
                }
            """)

            if action_bar:
                if action_bar.get('comments'):
                    comments = parse_interactions(str(action_bar['comments']))
                if action_bar.get('shares'):
                    shares = parse_interactions(str(action_bar['shares']))

        except Exception:
            pass

        # ── FALLBACK: Dùng aria-label "Thích: 93 người" style ─────────────
        if not comments or not shares:
            try:
                for node in element.locator('[aria-label]').all():
                    label = (node.get_attribute('aria-label') or '').strip()
                    if not label:
                        continue
                    ll = label.lower()
                    if not comments and (m := COMMENT_RE.search(label)):
                        comments = parse_interactions(m.group(1))
                    if not shares and (m := SHARE_RE.search(label)):
                        shares = parse_interactions(m.group(1) or m.group(2) or '')
                    if comments and shares:
                        break
            except Exception:
                pass

        return {'reactions': reactions, 'comments': comments, 'shares': shares}
   
   # hàm  nếu thấy nội dung có nút xem thêm thì click vào nút đó 
#    và đôi khi ở phần bình luận cũng hay có nút này ta sẽ bỏ qua nó nếu ở bình luận
    @staticmethod
    def expand_see_more(element) -> None:
        """Click nút 'Xem thêm' ở nội dung chính, TUYỆT ĐỐI bỏ qua khu vực bình luận."""
        try:
            # Dùng JS để vừa tìm nút vừa kiểm tra ranh giới, tránh quét nhầm bình luận
            clicked = element.evaluate("""
                (el) => {
                    // 1. Lấy mốc ranh giới khu vực bình luận
                    const commentSection = el.querySelector(
                        '[role="article"] [role="article"], ' +
                        '[aria-label*="Comment"], ' +
                        '[aria-label*="Bình luận"], ' +
                        '[data-testid*="comment"]'
                    );
                    
                    // 2. Tìm tất cả các nút
                    const buttons = el.querySelectorAll('div[role="button"], span[role="button"]');
                    let hasClicked = false;
                    
                    for (const btn of buttons) {
                        const txt = (btn.innerText || '').trim().toLowerCase();
                        
                        // Nếu đúng là nút Xem thêm / See more
                        if (txt === 'xem thêm' || txt === 'see more') {
                            
                            // 🛡️ BỘ LỌC BÌNH LUẬN:
                            // Nếu nút nằm BÊN TRONG vùng bình luận -> Bỏ qua
                            if (commentSection && commentSection.contains(btn)) continue;
                            // Nếu nút nằm PHÍA SAU vùng bình luận -> Bỏ qua
                            if (commentSection && (commentSection.compareDocumentPosition(btn) & 4)) continue;
                            
                            // Nút nằm trong vùng bài viết chính -> Bấm!
                            btn.click();
                            hasClicked = true;
                        }
                    }
                    return hasClicked; // Trả về true nếu có bấm nút
                }
            """)
            
            # TỐI ƯU TỐC ĐỘ:
            # Chỉ cho bot nghỉ 0.5s (để chờ text bung ra) NẾU thực sự có bài viết dài cần bấm nút.
            # Nếu bài viết ngắn không có nút, bot sẽ chạy lướt qua luôn không phải chờ.
            if clicked:
                import time
                time.sleep(0.5)
                
        except Exception:
            pass
    

    #  hàm chính lấy nội dung của bài viết
    @staticmethod
    def get_content(element) -> str:
        """Tương tác DOM: Bóc tách phần Text của bài viết, TUYỆT ĐỐI không lấy bình luận"""
        PostExtractor.expand_see_more(element)
        #  TẦNG 1: Dùng chìa khóa chuẩn (Ưu tiên lấy chuẩn xác và nhanh nhất)
        try:
            for selector in [
                'div[data-ad-comet-preview="message"]', 
                'div[data-ad-preview="message"]'
            ]:
                node = element.locator(selector).first
                if node.count() > 0:
                    return node.inner_text().strip()
        except Exception:
            pass

        #  TẦNG 2: Fallback bằng JS Evaluate (Lọc chính xác theo vị trí DOM)
        # Quét div[dir="auto"] nhưng dừng lại ngay khi chạm mặt vùng Bình Luận
        try:
            content = element.evaluate("""
                (el) => {
                    // 1. Tìm cái mốc ranh giới: Khu vực bình luận hoặc thanh reaction
                    const commentSection = el.querySelector(
                        '[role="article"] [role="article"], ' +  // Bài viết lồng trong bài viết = comment
                        '[aria-label*="Comment"], ' +
                        '[aria-label*="Bình luận"], ' +
                        '[data-testid*="comment"]'
                    );
                    
                    // 2. Tìm tất cả các khối chứa chữ
                    const allDirs = el.querySelectorAll('div[dir="auto"]');
                    let bestText = '';
                    
                    // Từ khóa UI cấm kỵ (giống NON_REACTION_KEYWORDS ở Python)
                    const banWords = ['bình luận', 'chia sẻ', 'comment', 'share', 'thông báo'];
                    
                    for (const div of allDirs) {
                        // NẾU thẻ này nằm BÊN TRONG commentSection -> Bỏ qua
                        if (commentSection && commentSection.contains(div)) {
                            continue;
                        }
                        
                        // NẾU thẻ này nằm PHÍA SAU commentSection -> Bỏ qua
                        // (Dùng cờ 4: Node.DOCUMENT_POSITION_FOLLOWING)
                        if (commentSection && (commentSection.compareDocumentPosition(div) & 4)) {
                            continue;
                        }
                        
                        const txt = (div.innerText || '').trim();
                        const txtLower = txt.toLowerCase();
                        
                        // Lọc rác: Bỏ qua text quá ngắn hoặc chứa từ khóa UI
                        const isBanned = banWords.some(word => txtLower.includes(word));
                        
                        if (txt.length > 20 && !isBanned) {
                            // Cập nhật lấy đoạn text dài nhất (Caption bài viết)
                            if (txt.length > bestText.length) {
                                bestText = txt;
                            }
                        }
                    }
                    return bestText;
                }
            """)
            if content:
                return content.strip()
        except Exception:
            pass
            
        return ""
