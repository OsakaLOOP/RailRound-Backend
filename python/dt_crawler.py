import time
import requests
import webview
import os
import http.cookies
import logging
from email.message import EmailMessage
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs


# --- 配置区域 ---
class Config:
    LOGIN_URL = "https://ekidata.jp//dl/"
    TARGET_URL = "https://ekidata.jp/dl/?p=1"


    USERNAME = "mywrh15@126.com"
    PASSWORD = "mywrh2019"


    SELECTOR_USER = "input[name='ac']"
    SELECTOR_PASS = "input[name='ps']"
    SELECTOR_BTN = "input[type='submit']"

    DOWNLOAD_DIR = "./downloads"
    DEBUG_MODE = True


# --- 日志设置 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Ekidata] - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger()


class CrawlerService:
    def __init__(self):
        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def _get_cookies_via_webview(self):
        """启动(隐形)浏览器完成认证并提取Cookie"""
        logger.info("启动 Webview 进行认证...")
        cookies = []

        # 创建窗口
        window = webview.create_window(
            'Auth Worker',
            Config.LOGIN_URL,
            hidden=Config.DEBUG_MODE,
            width=800, height=600
        )

        def auth_logic(w):
            time.sleep(3)  # 等待页面加载

            logger.info("注入登录脚本...")
            # 自动填充并点击登录
            js = f"""
                document.querySelector("{Config.SELECTOR_USER}").value = "{Config.USERNAME}";
                document.querySelector("{Config.SELECTOR_PASS}").value = "{Config.PASSWORD}";
                document.querySelector("{Config.SELECTOR_BTN}").click();
            """
            w.evaluate_js(js)

            # 等待跳转和Cookie写入
            time.sleep(4)

            raw_cookies = w.get_cookies()
            for c in raw_cookies:
                cookies.append(c)

            logger.info(f"获取到 {len(cookies)} 个 Cookie，关闭窗口...")
            w.destroy()

        webview.start(func=auth_logic, args=(window,), private_mode=False)

        # 转换 cookie 格式
        cookie_dict = {}
        for c in cookies:
            try:
                if isinstance(c, http.cookies.BaseCookie):
                    for key, morsel in c.items():
                        cookie_dict[key] = morsel.value
                else:
                    pass
            except Exception as e:
                logger.warning(f"无法解析单个Cookie: {c} - {e}")

        return cookie_dict

    def run(self):
        if not os.path.exists(Config.DOWNLOAD_DIR):
            os.makedirs(Config.DOWNLOAD_DIR)

        # 1. 获取并应用 Cookie
        cookies = self._get_cookies_via_webview()
        if not cookies:
            logger.error("未获取到 Cookie，终止任务")
            return
        self.session.cookies.update(cookies)

        # 2. 获取列表页
        logger.info(f"访问数据页: {Config.TARGET_URL}")
        resp = self.session.get(Config.TARGET_URL)
        if resp.status_code != 200:
            logger.error(f"访问失败 Code: {resp.status_code}")
            return

        # 3. 解析页面并筛选最新文件
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select("a[href*='f.php']")

        logger.info(f"原始链接数: {len(links)}，开始筛选...")

        # 字典结构: {'t值': {'date': 20250101, 'url': 'https://...'}}
        latest_map = {}

        for link in links:
            href = link.get('href', '')
            full_url = urljoin(Config.TARGET_URL, str(href))

            try:
                # 解析 URL 参数
                parsed_url = urlparse(full_url)
                params = parse_qs(parsed_url.query)

                # 获取 t (分类) 和 d (日期)
                t_vals = params.get('t')
                d_vals = params.get('d')

                if t_vals and d_vals:
                    t_val = t_vals[0]

                    d_val = int(d_vals[0])


                    if t_val not in latest_map or d_val > latest_map[t_val]['date']:
                        latest_map[t_val] = {
                            'date': d_val,
                            'url': full_url
                        }
            except Exception as e:
                logger.warning(f"链接解析跳过: {href}, 原因: {e}")
                continue

        # 对分类 t 进行排序，保证下载顺序
        sorted_t_keys = sorted(latest_map.keys(), key=lambda x: int(x) if x.isdigit() else x)
        logger.info(f"筛选完成，即将下载 {len(sorted_t_keys)} 个最新文件")

        # 4. 执行下载
        for t_val in sorted_t_keys:
            item = latest_map[t_val]
            self._download_smart(item['url'], Config.DOWNLOAD_DIR, item['date'])
            time.sleep(2)  # 礼貌延时防止封禁

    def _download_smart(self, url, save_dir, date_hint):
        """优先使用响应头中的文件名"""
        try:

            with self.session.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()

                # 检查内容类型，防止下载到报错页面
                if 'text/html' in r.headers.get('Content-Type', ''):
                    logger.warning(f"目标疑似非文件(HTML): {url}")
                    return


                filename = None
                content_disposition = r.headers.get('Content-Disposition')

                if content_disposition:
                    msg = EmailMessage()
                    msg['content-disposition'] = content_disposition
                    filename = msg.get_filename()

                # 兜底文件名：如果服务器没给文件名，就自己拼一个
                if not filename:
                    filename = f"company{date_hint}.csv"

                # 净化文件名并拼接路径
                filename = os.path.basename(filename)
                save_path = os.path.join(save_dir, filename)

                if os.path.exists(save_path):
                    logger.info(f"跳过已存在: {filename}")
                    return

                # 开始正式写入文件
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                logger.info(f"下载成功: {filename}")

        except Exception as e:
            logger.error(f"下载出错 {url}: {e}")


if __name__ == "__main__":
    crawler = CrawlerService()
    crawler.run()