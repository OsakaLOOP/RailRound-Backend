import logging
import os
import sys
import json
import webview
import time
import socket
import threading
from flask import Flask, render_template, request

#from railway_processer import router as api_router # 引入api路由蓝图
from api import Api
from worker_manager import manager, WorkerRegistry

index=r".\..\dist\index.html"
base_dir = os.path.dirname(os.path.abspath(__file__))
dist_dir = os.path.join(base_dir, '..', 'dist')

app = Flask(__name__, static_folder=dist_dir, template_folder=dist_dir, static_url_path='')
#app.register_blueprint(api_router, url_prefix='/api')
# ./路由
@app.before_request
def log_request_info():
    # Flask debug
    if not request.path.endswith('.js') and not request.path.endswith('.css'):
        print(f"[Dev] Incoming Request: {request.method} {request.path}")


@app.route('/')

def index():
    return render_template('index.html')
def start():
    app.run(host='127.0.0.1', port=5000, threaded=True, use_reloader=False, debug=False)

def wait_for_server(port=5000, timeout=5):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.05)
    return False

class WebviewHandler(logging.Handler):
    
    def __init__(self):
        super().__init__()
        self._window = None
        self.queue = []      # 日志缓冲区, 解决 Flask 加载完成前的死锁问题
        self.is_ready = False # 前端加载

    def set_window(self, window):
        self._window = window
        self._window.events.loaded += self.on_loaded
        self._window.events.closed += self.on_closed
        
    def flush_queue(self):
        """将缓冲区推送到前端"""
        if not self._window or not self.is_ready: return
        
        # 批量处理以提高性能
        while self.queue:
            record = self.queue.pop(0)
            self._send_to_js(record)

    def on_loaded(self):
        self.is_ready = True
        print(f"[System] Frontend loaded. Flushing {len(self.queue)} queued logs...")
        self.flush_queue()
        
    def on_closed(self):
        """
        安全回调, 防止后台线程向已销毁的 WebView2 控件发送日志
        """
        print("[System] Window closed. Detaching log handler.")
        self._window = None
        self.is_ready = False
    
    def _send_to_js(self, record):
        if self._window:
            # 获取日志文本
            msg = self.format(record)
            js_msg = json.dumps(msg)
            msg_type = record.levelname
            js_code = f"addLog('{msg_type}', '{js_msg}');"
            try:
                self._window.evaluate_js(js_code)
            except Exception:
                pass
            
    def emit(self, record):
        if record.name.startswith('pywebview') or record.name == 'werkzeug': 
            return
        if not self.is_ready:
            self.queue.append(record)
        else:
            self._send_to_js(record)

#配置
logger = logging.getLogger()
logger.setLevel(logging.INFO)
frontend_logger = logging.getLogger("Frontend")
frontend_logger.propagate = False

#接受并显示来自网页的 log
python_handler = logging.StreamHandler()
python_handler.setFormatter(logging.Formatter('[JS-SIDE] %(message)s'))
webview_handler = WebviewHandler()

webview_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))

logger.addHandler(webview_handler)
frontend_logger.addHandler(python_handler)

#模拟
def run(window):
    logging.info('Ready.')

#程序启动
if __name__ == '__main__':

    # Initialize workers
    if not manager.get_worker('geojson'):
        manager.create_worker('geojson', 'GeojsonWorker', period=3600)

    if not manager.get_worker('ekidata'):
        manager.create_worker('ekidata', 'EkidataWorker', period=3600)

    # Start manager loop
    t_manager = threading.Thread(target=manager.loop)
    t_manager.daemon = True
    t_manager.start()

    api_instance = Api()
    t = threading.Thread(target=start)
    t.daemon = True # 守护线程, 自动销毁
    t.start()
    logger.info("Starting Flask server...")
    if not wait_for_server():
        print("Fatal: Server failed to start.")
        sys.exit(1)
    else:
        print("TCP port is open.")
    
    window = webview.create_window(
        'Test',
        url='http://127.0.0.1:5000', # localhost 不够 robust
        js_api=api_instance,
        frameless=True,
        text_select=True,
        easy_drag=False
    )
    api_instance.setWindow(window)
    webview_handler.set_window(window)

    webview.start(run, window)