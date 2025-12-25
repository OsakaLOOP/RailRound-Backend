import time
import threading
from typing import Dict, Any, Type, Optional

from worker_base import WorkerProcess, ProgressTracker, WorkerAdapter

# 自定义worker类
from geojson_crawler import GeoJsonWorker
from ekidata_crawler import EkidataWorker
from railway_processer import RailwayDataService
from line_segmenter import LineSegmenter

class WorkerRegistry:
    _name_to_cls: Dict[str, Type[WorkerProcess]] = {}
    _cls_to_name: Dict[Type[WorkerProcess], str] = {}
    
    @classmethod
    def register(cls, name: str, worker_cls: Type[WorkerProcess]):
        """绑定Worker类和唯一名称的双向字典"""
        if name in cls._name_to_cls:
            if cls._name_to_cls[name] != worker_cls:
                raise ValueError(f"Worker 实例 '{name}' 已注册为 {cls._name_to_cls[name]} 类.")
            return 

        if worker_cls in cls._cls_to_name:
             raise ValueError(f"Worker 类 '{worker_cls.__name__}' 已注册实例 '{cls._cls_to_name[worker_cls]}'.")
        
        cls._name_to_cls[name] = worker_cls
        cls._cls_to_name[worker_cls] = name
        
    @classmethod
    def get_cls(cls, name: str) -> Optional[Type[WorkerProcess]]:
        return cls._name_to_cls.get(name)

    @classmethod
    def get_name(cls, worker_cls: Type[WorkerProcess]) -> Optional[str]:
        return cls._cls_to_name.get(worker_cls)
    
    @classmethod
    def get_all_registered(cls):
        return cls._name_to_cls.copy()

WorkerRegistry.register("geojson", GeoJsonWorker)
WorkerRegistry.register("ekidata", EkidataWorker)
#WorkerRegistry.register("Line Segmentation", LineSegmenter)

class WorkerManager:
    def __init__(self):
        self._workers: Dict[str, WorkerProcess] = {}
        self._lock = threading.Lock()

        self.processor = RailwayDataService()

        self.cycle_active = False
    
    def create_worker(self, type_name: str, instance_name: str, **kwargs) -> WorkerProcess:
        
        with self._lock:
            if instance_name in self._workers:
                raise ValueError(f"Worker 已存在: '{instance_name}'.")
            
            worker_cls = WorkerRegistry.get_cls(type_name)
            if not worker_cls:
                raise ValueError(f"未知 Worker 类型: '{type_name}'")
            
            worker = worker_cls(name=instance_name, **kwargs)
            self._workers[instance_name] = worker
            return worker

    def get_worker(self, instance_name: str) -> Optional[WorkerProcess]:
        with self._lock:
            return self._workers.get(instance_name)

    def get_all_workers(self):
        with self._lock:
            return list(self._workers.values())

    def start_full_cycle(self):
        """从头开始运行"""
        with self._lock:
            print("[周期] 全周期运行...")
            self.cycle_active = True
            for worker in self._workers.values():
                worker.status['nextrun'] = 0
                if worker.status['statcode'] == 500:
                     worker.status['retry'] = 0
                     worker.status['statcode'] = 0 # 重置为 idle/ready
        
    def loop(self):
        while True:
            now = time.time()
            workers_list = self.get_all_workers()
            
            # 1. 规划
            for worker in workers_list:
                # 状态检测
                if worker.status['statcode'] in [0, 200] and now > worker.status.get('nextrun', 0):
                    print(f"[周期] 开始运行 {worker.name} ({worker.type})")
                    worker.status['retry'] = 0
                    t = threading.Thread(target=worker.run)
                    t.start()

                elif worker.status['statcode'] == 500:
                    current_retries = worker.status['retry']
                    if current_retries < worker.max_retry:
                        print(f"[Retry] {worker.name} failed. Retrying ({current_retries + 1}/{worker.max_retry})...")
                        worker.mark_failed()
                        t = threading.Thread(target=worker.run)
                        t.start()
                    else:
                        pass 

            # 2. 循环
            if self.cycle_active:
                all_finished = True
                for worker in workers_list:
                    if worker.status['statcode'] == 1:
                        all_finished = False
                        break

                if all_finished and workers_list: 
                    print("[Cycle] 完整运行周期完成. 正在生成格式化数据...")
                    try:
                        self.processor.build()
                        print("[Cycle] 完成数据生成.")
                    except Exception as e:
                        print(f"[Cycle] 数据生成错误: {e}")

                    self.cycle_active = False

            time.sleep(1)

manager = WorkerManager()