import time
import os
import logging
import uuid
import threading
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class WorkerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return '[RunID:%s] %s' % (self.extra['worker'].run_id or 'None', msg), kwargs # type: ignore

class ProgressTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self.total = 0
        self.current = 0
        self.start_time = 0
        self.error = 0
        self._errors = []
        self.run_id = ''

    def start(self, total: int, run_id: str = ''):
        '''开始任务'''
        with self._lock:
            self.total = total
            self.current = 0
            self.start_time = time.time()
            self.run_id = run_id

    def update(self, current: int):
        '''更新进度'''
        with self._lock:
            self.current = current

    def get_snapshot(self):
        '''获取展示数据'''
        with self._lock:
            # 1. 耗时计算
            elapsed = time.time() - self.start_time

            # 2. 进度计算
            if self.total == 0:
                percent = 0
            else:
                percent = int((self.current / self.total) * 100)

            # 3. ETA 计算 (核心)
            eta_seconds = 0
            speed = 0
            if self.current > 0:
                # 平均处理速度 (秒/个)
                avg_time_per_item = elapsed / self.current
                remaining_items = self.total - self.current
                eta_seconds = int(avg_time_per_item * remaining_items)
                speed = round(self.current / elapsed, 2) # 个/秒

            # 4. 格式化输出 (给人类看的)
            return {
                "progress": f"{self.current}/{self.total}",
                "percent": f"{percent}%",
                "elapsed": f"{int(elapsed)}s",
                "eta": f"{eta_seconds}s",  # 剩余秒数
                "speed": f"{speed}/s"      # 速度
            }

    def get_view_model(self):
        '''为前端生成数据字典'''
        with self._lock:
            elapsed = time.time() - self.start_time

            # 基础计算
            percent = 0
            if self.total > 0:
                percent = round((self.current / self.total) * 100, 1)

            # ETA 计算
            eta = 0
            speed = 0.0
            if self.current > 0 and self.total > 0:
                avg_time = elapsed / self.current
                eta = int(avg_time * (self.total - self.current))
                speed = round(self.current / elapsed, 2)

            return {
                "current": self.current,
                "total": self.total,
                "percent": percent,
                "eta_seconds": eta,
                "speed": speed,
                "error": self.error,
                "run_id": self.run_id,
                # 如果 current < total 且 total > 0，认为 active
                "is_active": (self.current < self.total) and (self.total > 0)
            }

    def increment(self, item= None):
        '''进度+1'''
        with self._lock:
            self.current += 1
            if item is not None:
                self._item = item

    def add_to_total(self, n: int):
        '''增加总数'''
        with self._lock:
            self.total += n

    def recErr(self,err:str):
        with self._lock:
            self._errors.append(err)

class WorkerProcess(ABC):
    def __init__(self, name: str, period: int, type_str: str, max_retry=3):
        self.name = name
        self.period = period if period>=3600 else 3600 # 部分任务耗时, 周期太短干扰调度
        self.type = type_str
        self.log_dir = 'logs'
        self.max_retry = max_retry
        self.run_id = ''

        self.logger = self._setup_logger()
        self.tracker = ProgressTracker()

        # 初始化状态字典
        self.status = {
            'starttime': time.time(),
            'nextrun': time.time(),
            'uptime': 0,
            'lastrun': 0,
            'lastreturn': None,
            'statcode': 0,  # 0: Idle, 1: Running, 200: Success, 500: Error
            'retry':0
        }

    def _setup_logger(self):
        '''配置独立 Logger'''
        # 1. 创建 Logger
        logger = logging.getLogger(f"Worker.{self.name}")
        logger.setLevel(logging.INFO)

        # 2. 防止重复添加 Handler
        if not logger.hasHandlers():
            if not os.path.exists(self.log_dir):
                os.makedirs(self.log_dir)

            formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

            # 3. 文件输出
            file_handler = logging.FileHandler(
                os.path.join(self.log_dir, f"{self.name}.log"),
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            # 4. 控制台输出
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        return WorkerAdapter(logger, {'worker': self})

    def _pre_run(self):
        '''运行前更新状态'''
        self.status['lastrun'] = time.time()
        self.status['statcode'] = 1
        self.run_id = str(uuid.uuid4())[:8]
        self.logger.info(f"Starting Run {self.run_id}")

    def _post_run(self, result, error=None):
        '''运行后更新状态'''
        current_time = time.time()
        self.status['uptime'] = current_time - self.status['starttime']

        summary = f"Run {self.run_id} Finished. Total Processed: {self.tracker.current}, Time Taken: {round(self.status['uptime'], 2)}s"

        if error:
            self.status['statcode'] = 500
            self.status['lastreturn'] = str(error)
            self.status['retry'] += 1
            self.logger.error(f"{summary} (with errors)")
        else:
            self.status['statcode'] = 200
            self.status['lastreturn'] = result
            self.status['nextrun'] = current_time + self.period
            self.logger.info(summary)

    def get_dashboard_view(self):
        """前端展示的状态"""
        # 获取进度快照
        prog_data = self.tracker.get_view_model()

        return {
            "id": self.name,# React key
            "display_name": self.name,
            "type": self.type,
            "status_code": self.status['statcode'], # 0, 1, 200, 500
            "status_text": self._get_status_text(self.status['statcode']),
            "period": self.period, # Expose period
            "progress": prog_data,
            "last_update_ts": time.time(),

            "log_preview": str(self.status.get('lastreturn') or "Ready")[:50]
        }

    def _get_status_text(self, code):
        mapping = {0: "待机", 1: "运行中", 200: "完成", 500: "错误"}
        return mapping.get(code, "Unknown")

    def run(self):
        # 抽象统一流程
        self._pre_run()

        # 子类一定要调用tracker.start()!!!!!

        try:
            result_msg = self.trigger()
            self._post_run(result_msg)

        except Exception as e:
            # 统一的错误处理
            self.logger.exception("Critical Failure")
            self.tracker.recErr(str(e))
            self._post_run(None, error=e)

    def mark_failed(self):
        """标记为失败, 并计数"""
        self.status['retry'] += 1

    # 抽象子类定义
    @abstractmethod
    def trigger(self):
        pass
