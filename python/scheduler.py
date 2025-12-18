import time
from abc import ABC, abstractmethod

class TypeToWorker(dict):
    def __init__(self, iterable=[]):
        super().__init__()
        self.count = 0
        if iterable:
            for item in iterable:
                self.add(item)

    def add(self, key):
        # 仅当键不存在时才分配新编号，实现去重和自增
        if key not in self:
            self[key] = self.count
            self.count += 1
        return self[key]


    
class worker(ABC):
    def __init__(self,type:str):
        
        self.type = type
        self.status = {'starttime':time.time(), 'uptime':0, 'lastrun':0, 'lastreturn':None, 'error':None, 'statcode': 0}
        # Time stamp in seconds
        # 0: Idle, 1: Running, 200: Success, 500: Error
    def _pre_run(self):
        """运行前更新状态"""
        self.status['lastrun'] = time.time()
        self.status['statcode'] = 1
        
    def _post_run(self, result, error=None):
        """运行后更新状态"""
        current_time = time.time()
        self.status['uptime'] = current_time - self.status['starttime']
        
        if error:
            self.status['statcode'] = 500
            self.status['lastreturn'] = str(error)
        else:
            self.status['statcode'] = 200
            self.status['lastreturn'] = result
    
    @abstractmethod
    def trigger(self):
        """子类必须实现此方法"""
        pass

    
TypeDict = TypeToWorker(['geojson_worker',geojsonWorker('',30,)])