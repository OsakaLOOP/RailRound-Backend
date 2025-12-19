import requests
import webview
import os
import http.cookies
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from worker_base import WorkerProcess

class EkidataWorker(WorkerProcess):
    # --- 配置区域 ---
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

    def __init__(self, name, period, max_retry=3):
        super().__init__(name, period, "ekidata_crawler", max_retry)
        self.session = requests.Session()
        # 伪装 User-Agent 防止被服务端拒绝
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def trigger(self):
        if not os.path.exists(self.DOWNLOAD_DIR):
            os.makedirs(self.DOWNLOAD_DIR)

        # 1. 获取并应用 Cookie
        cookies = self._get_cookies_via_webview()
        if not cookies:
            self.logger.error("未获取到 Cookie，终止任务")
            raise Exception("Failed to get cookies")

        self.session.cookies.update(cookies)

        # 2. 获取列表页
        self.logger.info(f"访问数据页: {self.TARGET_URL}")
        resp = self.session.get(self.TARGET_URL)
        if resp.status_code != 200:
            self.logger.error(f"访问失败 Code: {resp.status_code}")
            raise Exception(f"Failed to access target URL: {resp.status_code}")

        # 3. 解析与下载
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select("a[href*='f.php']") # 锚点定位

        self.logger.info(f"解析到 {len(links)} 个潜在文件")
        self.tracker.start(len(links), self.run_id)

        for link in links:
            href = link.get('href','')
            full_url = urljoin(self.TARGET_URL, str(href))

            # 文件名提取逻辑
            try:
                # 假设 url 结构: f.php?t=1&d=20250122...
                date_part = str(href).split('d=')[1].split('&')[0]
                filename = f"ekidata_{date_part}.csv"
            except IndexError:
                filename = f"ekidata_{int(time.time())}.csv"

            save_path = os.path.join(self.DOWNLOAD_DIR, filename)

            if os.path.exists(save_path):
                self.logger.info(f"跳过已存在: {filename}")
                self.tracker.increment(filename)
                continue

            self._download_file(full_url, save_path)
            self.tracker.increment(filename)
            time.sleep(2) # 礼貌延时

        return f"Completed. Downloaded/Checked {len(links)} files."

    def _get_cookies_via_webview(self):
        """启动(隐形)浏览器完成认证并提取Cookie"""
        self.logger.info("启动 Webview 进行认证...")
        cookies = []
        
        # 创建窗口 (注意：不要调用 webview.start()，因为主线程应该已经在运行它)
        window = webview.create_window(
            'Auth Worker',
            self.LOGIN_URL,
            hidden=False,
            width=800, height=600
        )
        

        # 定义认证逻辑 (注入 JS)
        def auth_logic():
            if not window:
                return
            time.sleep(3) # 等待DOM加载
            
            self.logger.info("注入登录脚本...")
            js = f"""
                document.querySelector("{self.SELECTOR_USER}").value = "{self.USERNAME}";
                document.querySelector("{self.SELECTOR_PASS}").value = "{self.PASSWORD}";
                document.querySelector("{self.SELECTOR_BTN}").click();
            """
            window.evaluate_js(js)
            
            # 等待跳转和Cookie写入
            time.sleep(4) 
            
            raw_cookies = window.get_cookies()
            for c in raw_cookies:
                cookies.append(c)
            
            self.logger.info(f"获取到 {len(cookies)} 个 Cookie，关闭窗口...")
            window.destroy()

        # 在当前线程执行认证逻辑，等待窗口操作完成
        # 等待一下窗口创建
        time.sleep(0.3)

        try:
            auth_logic()
        except Exception as e:
            self.logger.error(f"Auth logic error: {e}")
            if window:
                window.destroy()
        
        # 转换 pywebview cookie 对象为 dict
        cookie_dict = {}
        for c in cookies:
            try:
                # 处理 SimpleCookie 类型
                if isinstance(c, http.cookies.BaseCookie):
                    # SimpleCookie 像字典一样存储 Morsel 对象
                    for key, morsel in c.items():
                        cookie_dict[key] = morsel.value
                else:
                    raise ValueError(f"未知 Cookie 类型: {type(c)}")
                    
            except Exception as e:
                self.logger.warning(f"无法解析单个Cookie: {c} - {e}")
        
        return cookie_dict

    def _download_file(self, url, path):
        try:
            with self.session.get(url, stream=True) as r:
                r.raise_for_status()
                # 检查是否是 CSV 类型 (防止下载到 HTML)
                if 'text/html' in r.headers.get('Content-Type', ''):
                    self.logger.warning(f"下载内容疑似为HTML而非文件: {url}")
                    return

                with open(path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            self.logger.info(f"下载成功: {os.path.basename(path)}")
        except Exception as e:
            self.logger.error(f"下载出错 {url}: {e}")
