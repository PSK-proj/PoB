import os
import time
import requests

LB_URL = os.getenv("LB_URL", "http://lb:8000")


def main():
    print(f"ClientGen: sending test requests to {LB_URL}/request")
    for i in range(10):
        try:
            resp = requests.post(f"{LB_URL}/request", timeout=2)
            print(f"[{i}] status={resp.status_code} body={resp.json()}")
        except Exception as e:
            print(f"[{i}] error: {e}")
        time.sleep(1)


if __name__ == "__main__":
    main()
