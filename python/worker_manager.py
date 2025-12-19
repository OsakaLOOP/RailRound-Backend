import time
import threading
from typing import Dict, Any, Type, Optional

# Import Base Classes
from worker_base import WorkerProcess, ProgressTracker, WorkerAdapter

# Import Specific Workers
from geojson_crawler import GeoJsonWorker
from ekidata_crawler import EkidataWorker

class WorkerRegistry:
    _name_to_cls: Dict[str, Type[WorkerProcess]] = {}
    _cls_to_name: Dict[Type[WorkerProcess], str] = {}
    
    @classmethod
    def register(cls, name: str, worker_cls: Type[WorkerProcess]):
        """Register a worker class with a unique name."""
        if name in cls._name_to_cls:
            if cls._name_to_cls[name] != worker_cls:
                raise ValueError(f"Worker name '{name}' is already registered to {cls._name_to_cls[name]}")
            return # Already registered correctly

        if worker_cls in cls._cls_to_name:
             raise ValueError(f"Worker class '{worker_cls.__name__}' is already registered as '{cls._cls_to_name[worker_cls]}'.")
        
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


class WorkerManager:
    def __init__(self):
        self._workers: Dict[str, WorkerProcess] = {}
        self._lock = threading.Lock()
    
    def create_worker(self, type_name: str, instance_name: str, **kwargs) -> WorkerProcess:
        
        with self._lock:
            if instance_name in self._workers:
                raise ValueError(f"Worker instance with name '{instance_name}' already exists.")
            
            worker_cls = WorkerRegistry.get_cls(type_name)
            if not worker_cls:
                raise ValueError(f"Unknown worker type: '{type_name}'")
            
            # Instantiate
            worker = worker_cls(name=instance_name, **kwargs)
            self._workers[instance_name] = worker
            return worker

    def get_worker(self, instance_name: str) -> Optional[WorkerProcess]:
        with self._lock:
            return self._workers.get(instance_name)

    def get_all_workers(self):
        with self._lock:
            return list(self._workers.values())
        
    def loop(self):
        while True:
            now = time.time()
            workers_list = self.get_all_workers()
            
            for worker in workers_list:
                # Check status and trigger if needed
                if worker.status['statcode'] in [0, 200] and now > worker.status.get('nextrun', 0):
                    print(f"[Schedule] Starting run for {worker.name} ({worker.type})")
                    worker.status['retry'] = 0
                    # Run in a separate thread to not block the manager loop
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
                        pass # Give up or wait for manual reset

            time.sleep(1)

# Global Manager Instance
manager = WorkerManager()

# For backward compatibility or simple usage
def loop(workers=None):
    # If workers list is provided, register them loosely or just ignore and use the manager's list
    # The new design encourages using manager.create_worker() and then manager.loop()
    if workers:
        print("Warning: Passing workers list to loop() is deprecated. Use WorkerManager.")
        for w in workers:
            pass
            
    manager.loop()
