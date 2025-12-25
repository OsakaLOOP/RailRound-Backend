import logging
import json
import psutil
import time
from worker_manager import manager

frontend_logger = logging.getLogger("Frontend")

class Api:
    
    def __init__(self):
        self._window=None
        self._is_maximized = False
        self._last_net = psutil.net_io_counters()
        self._last_disk = psutil.disk_io_counters()
        self._last_time = time.time()  
        
    def setWindow(self,window):
        self._window=window
        
    def sendLog(self, level, msg):
        try:
            # 尝试解析 JSON
            msg_content = json.loads(msg) if msg.startswith('{') or msg.startswith('[') else msg
        except:
            msg_content = msg

        if level == 'error':
            frontend_logger.error(msg_content)
        elif level == 'warn':
            frontend_logger.warning(msg_content)
        else:
            frontend_logger.info(msg_content)
            
    def minimize(self):
        """最小化窗口"""
        if self._window:
            self._window.minimize()

    def toggle_maximize(self):
        """维护最大化状态"""
        if self._window:
            if self._is_maximized:
                self._window.restore()
                self._is_maximized = False
            else:
                self._window.maximize()
                self._is_maximized = True

    def close(self):
        """关闭程序"""
        try:
            if self._window:
                win = self._window
                self._window = None # 防止重复调用, 报错:System.ObjectDisposedException
                
                win.destroy()
        except Exception:
            pass

    def open_child_window(self, title, url):
        """Open a child window for debugging or visualization."""
        try:
            import webview
            webview.create_window(title, url, frameless=False, fullscreen=False)
        except Exception as e:
            logging.error(f"Failed to open child window: {e}")

    def retrive_performance_data(self):
        """获取性能数据"""
        curr_net = psutil.net_io_counters()
        curr_disk = psutil.disk_io_counters()
        curr_time = time.time()

        dt = curr_time - self._last_time
        try:
            disk_r = (curr_disk.read_bytes - self._last_disk.read_bytes) / 1024 / 1024 / dt
            disk_w = (curr_disk.write_bytes - self._last_disk.write_bytes) / 1024 / 1024 / dt
            
            net_d = (curr_net.bytes_recv - self._last_net.bytes_recv) / 1024 / dt
            net_u = (curr_net.bytes_sent - self._last_net.bytes_sent) / 1024 / dt
            
            self._last_net = curr_net
            self._last_disk = curr_disk
            self._last_time = curr_time

            return [int(psutil.cpu_percent(interval=1)), int(psutil.virtual_memory().percent), int(disk_r), int(disk_w), int(net_d), int(net_u)]
        except:
            return[0,0,0,0,0,0]
        # 顺序: CPU, RAM, DISK, NET

    def get_workers_status(self):
        return [w.get_dashboard_view() for w in manager.get_all_workers()]

    def start_worker(self, name):
        worker = manager.get_worker(name)
        if worker:
            worker.status['nextrun'] = 0
            worker.status['statcode'] = 0
            return True
        return False

    def start_full_cycle(self):
        manager.start_full_cycle()
        return True

    def stop_full_cycle(self):
        manager.cycle_active = False
        return True

    def update_worker_period(self, name, period):
        worker = manager.get_worker(name)
        if worker:
            try:
                p = int(period)
                if p > 0:
                    worker.period = p
                    return True
            except:
                pass
        return False