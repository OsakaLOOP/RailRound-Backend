import time
import threading
import os
import sqlite3
from worker_manager import manager, WorkerRegistry, WorkerProcess

'''class MockWorker(WorkerProcess):
    def trigger(self):
        time.sleep(0.1) # Simulate work
        return "Mock Done"

WorkerRegistry.register("mock", MockWorker)'''

def test_cycle():
    print("开始测试...")
    manager.create_worker("mock", "worker1", period=9999, type_str="mock")
    manager.create_worker("mock", "worker2", period=9999, type_str="mock")

    # 重新建立db
    if os.path.exists("railway.db"):
        os.remove("railway.db")

    print("Starting Manager Loop...")
    t = threading.Thread(target=manager.loop, daemon=True)
    t.start()

    time.sleep(1) 

    # Trigger Cycle
    print("开始全周期...")
    manager.start_full_cycle()

    print("等待db加载...")
    for _ in range(10):
        if not manager.cycle_active and os.path.exists("railway.db"):
            print("周期完成, 所有数据已存储")
            break
        time.sleep(1)

    # 内容验证
    if os.path.exists("railway.db"):
        conn = sqlite3.connect("railway.db")
        cursor = conn.cursor()

        try:
            # 验证表
            cursor.execute("SELECT count(*) FROM companies")
            c_count = cursor.fetchone()[0]
            print(f"Companies in DB: {c_count}")

            if c_count > 0:
                print("SUCCESS: Data found in DB.")
            else:
                print("WARNING: DB created but empty (maybe missing source files?).")

        except Exception as e:
            print(f"FAILURE: DB query failed: {e}")
        finally:
            conn.close()
    else:
        print("FAILURE: railway.db was not created.")

if __name__ == "__main__":
    test_cycle()
