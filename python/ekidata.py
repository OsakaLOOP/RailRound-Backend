import time
import requests
import webview
import os
import http.cookies
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- 配置区域 ---
class Config:
    LOGIN_URL = "https://ekidata.jp//dl/"
    TARGET_URL = "https://ekidata.jp/dl/?p=1"
    USERNAME = "mywrh15@126.com"
    PASSWORD = "mywrh2019"
    
    # CSS 选择器
    SELECTOR_USER = "input[name='ac']"
    SELECTOR_PASS = "input[name='ps']"
    SELECTOR_BTN = "input[type='submit']"
    
    DOWNLOAD_DIR = "./downloads"
    DEBUG_MODE = True  # 设置为 False 可在屏幕上显示浏览器窗口进行调试

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
        # 伪装 User-Agent 防止被服务端拒绝
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
            hidden=Config.DEBUG_MODE, # 调试模式下隐藏，非调试模式显示
            width=800, height=600
        )

        def auth_logic(w):
            time.sleep(3) # 等待DOM加载
            
            logger.info("注入登录脚本...")
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
        
        # 转换 pywebview cookie 对象为 dict
        cookie_dict = {}
        for c in cookies:
            try:
                # 情况A: 处理日志中出现的 SimpleCookie 类型
                if isinstance(c, http.cookies.BaseCookie):
                    # SimpleCookie 像字典一样存储 Morsel 对象
                    for key, morsel in c.items():
                        cookie_dict[key] = morsel.value
                        print(c.output())
                        logger.info(f"解析到 Cookie (SimpleCookie): {key}={morsel.value[:5]}...")
                else:
                    raise ValueError(f'Cookie 类型不正确 - {type(c)}')
                    
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

        # 3. 解析与下载
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select("a[href*='f.php']") # 锚点定位
        
        logger.info(f"解析到 {len(links)} 个潜在文件")

        for link in links:
            href = link.get('href','')
            print(link)
            full_url = urljoin(Config.TARGET_URL,  str(href))
            
            # 文件名提取逻辑
            try:
                # 假设 url 结构: f.php?d=20250122&...
                date_part = str(href).split('d=')[1].split('&')[0]
                filename = f"ekidata_{date_part}.csv"
            except IndexError:
                filename = f"ekidata_{int(time.time())}.csv"

            save_path = os.path.join(Config.DOWNLOAD_DIR, filename)
            
            if os.path.exists(save_path):
                logger.info(f"跳过已存在: {filename}")
                continue

            self._download_file(full_url, save_path)
            time.sleep(2) # 礼貌延时

    def _download_file(self, url, path):
        try:
            with self.session.get(url, stream=True) as r:
                r.raise_for_status()
                # 检查是否是 CSV 类型 (防止下载到报错 HTML)
                if 'text/html' in r.headers.get('Content-Type', ''):
                    logger.warning(f"下载内容疑似为HTML而非文件: {url}")
                    return

                with open(path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            logger.info(f"下载成功: {os.path.basename(path)}")
        except Exception as e:
            logger.error(f"下载出错 {url}: {e}")

if __name__ == "__main__":
    crawler = CrawlerService()
    crawler.run()