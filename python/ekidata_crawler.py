import requests
import webview
import os
import http.cookies
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
from email.message import EmailMessage
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

        # 字典结构: {'t值': {'date': 20250101, 'url': 'https://...'}}
        latest_map = {}

        for link in links:
            href = link.get('href', '')
            full_url = urljoin(self.TARGET_URL, str(href))

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
                self.logger.warning(f"链接解析跳过: {href}, 原因: {e}")
                continue

        # 对分类 t 进行排序，保证下载顺序
        sorted_t_keys = sorted(latest_map.keys(), key=lambda x: int(x) if x.isdigit() else x)
        self.logger.info(f"筛选完成，即将下载 {len(sorted_t_keys)} 个最新文件")

        self.tracker.start(len(sorted_t_keys), self.run_id)

        # 4. 执行下载
        for t_val in sorted_t_keys:
            item = latest_map[t_val]
            self._download_smart(item['url'], self.DOWNLOAD_DIR, item['date'])
            self.tracker.increment()
            time.sleep(2)  # 礼貌延时防止封禁

        return f"Completed. Downloaded/Checked {len(sorted_t_keys)} latest files."

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
            time.sleep(2) # 等待DOM加载
            
            self.logger.info("注入登录脚本...")
            js = f"""
                document.querySelector("{self.SELECTOR_USER}").value = "{self.USERNAME}";
                document.querySelector("{self.SELECTOR_PASS}").value = "{self.PASSWORD}";
                document.querySelector("{self.SELECTOR_BTN}").click();
            """
            window.evaluate_js(js)
            
            # 等待跳转和Cookie写入
            time.sleep(3) 
            
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

    def _download_smart(self, url, save_dir, date_hint):
        """优先使用响应头中的文件名"""
        try:

            with self.session.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()

                # 检查内容类型，防止下载到报错页面
                if 'text/html' in r.headers.get('Content-Type', ''):
                    self.logger.warning(f"目标疑似非文件(HTML): {url}")
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
                    self.logger.info(f"跳过已存在: {filename}")
                    return

                # 开始正式写入文件
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                self.logger.info(f"下载成功: {filename}")

        except Exception as e:
            self.logger.error(f"下载出错 {url}: {e}")
