import time
import threading
import os
import sqlite3
from worker_manager import manager, WorkerRegistry, WorkerProcess

# Mock Worker to speed up test
class MockWorker(WorkerProcess):
    def trigger(self):
        time.sleep(0.1) # Simulate work
        return "Mock Done"

WorkerRegistry.register("mock", MockWorker)

def test_cycle():
    print("Setting up test...")
    # Register mock workers
    manager.create_worker("mock", "worker1", period=9999, type_str="mock")
    manager.create_worker("mock", "worker2", period=9999, type_str="mock")

    # Ensure DB is clean
    if os.path.exists("railway.db"):
        os.remove("railway.db")

    # Start Manager Loop in a separate thread
    print("Starting Manager Loop...")
    t = threading.Thread(target=manager.loop, daemon=True)
    t.start()

    time.sleep(1) # Let it spin up

    # Trigger Cycle
    print("Triggering Full Cycle...")
    manager.start_full_cycle()

    # Wait for completion (poll for DB existence)
    print("Waiting for build...")
    for _ in range(10):
        if not manager.cycle_active and os.path.exists("railway.db"):
            print("Cycle finished and DB created!")
            break
        time.sleep(1)

    # Verify DB content
    if os.path.exists("railway.db"):
        conn = sqlite3.connect("railway.db")
        cursor = conn.cursor()

        try:
            # Check tables
            cursor.execute("SELECT count(*) FROM companies")
            c_count = cursor.fetchone()[0]
            print(f"Companies in DB: {c_count}")

            # Since we use real files in RailwayProcessor, we expect some data if files exist
            # The environment has public/company_data.json, so at least companies should exist.
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
