"""实际测试 douyin 模式 API — 验证随机模式、快速连续请求"""
import os, sys, json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config

test_dir = Path(os.environ["USERPROFILE"]) / "AppData/Local/Temp/test_douyin_videos"
print(f"Test dir: {test_dir}")

if not test_dir.is_dir():
    print("Test dir does not exist — all douyin live tests skipped")
    print("To run: mkdir " + str(test_dir) + " && place video files inside")
else:
    print(f"Files count: {len(list(test_dir.iterdir()))}")

    config.RUN_MODE = "douyin"
    config.MEDIA_DIR = test_dir
    config.DB_PATH = str(test_dir / "test_live.db")
    config.DOUYIN_RANDOM_MEDIA = True

    # 删除旧 DB
    for p in [config.DB_PATH, config.DB_PATH + "-wal", config.DB_PATH + "-shm"]:
        if os.path.exists(p):
            os.remove(p)

    from flask import Flask
    app = Flask(__name__)
    app.secret_key = "test"

    from blueprints.auth import auth_bp
    from blueprints.douyin_api import douyin_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(douyin_bp)

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["logged_in"] = True

        # ── 1. Init ────────────────────────────────
        r = client.get("/api/douyin/init")
        d1 = r.get_json()
        print(f"\n1. Init: code={d1['code']}", end="")
        if d1["code"] == 0:
            print(f" name={d1['data']['name']}")
            first_name = d1["data"]["name"]
        else:
            print(f" msg={d1.get('msg', '')}")
            first_name = None

        # ── 2. Next × 10 ───────────────────────────
        print("\n2. Next × 10:")
        names_sequence = []
        for i in range(10):
            r = client.get("/api/douyin/next")
            d = r.get_json()
            if d["code"] == 0:
                names_sequence.append(d["data"]["name"])
                print(f"   [{i+1}] {d['data']['name']}")
            else:
                print(f"   [{i+1}] code={d['code']} msg={d.get('msg','')}")
                break

        print(f"   Got {len(names_sequence)} unique names: {len(set(names_sequence))}")

        # ── 3. Fresh init — check randomness ──────
        with client.session_transaction() as sess:
            sess.clear()

        with client.session_transaction() as sess:
            sess["logged_in"] = True

        r2 = client.get("/api/douyin/init")
        d2 = r2.get_json()
        print(f"\n3. Fresh init: name={d2.get('data',{}).get('name','N/A')}")
        print(f"   First session init:  {first_name}")
        print(f"   Second session init: {d2.get('data',{}).get('name','N/A')}")

        if first_name and d2["code"] == 0:
            if first_name != d2["data"]["name"]:
                print("   >>> Random WORKS (different init results)")
            else:
                # Check if random just happened to pick the same
                with client.session_transaction() as sess:
                    sess.clear()
                with client.session_transaction() as sess:
                    sess["logged_in"] = True
                r3 = client.get("/api/douyin/init")
                d3 = r3.get_json()
                print(f"   Third session init:  {d3.get('data',{}).get('name','N/A')}")
                if first_name != d3["data"]["name"]:
                    print("   >>> Random WORKS (first vs third different)")
                else:
                    print("   >>> Random BROKEN — same init every time!")

        # ── 4. Rapid sequential calls ─────────────
        print("\n4. Simulating rapid sequential next calls:")
        with client.session_transaction() as sess:
            sess.clear()
        with client.session_transaction() as sess:
            sess["logged_in"] = True

        client.get("/api/douyin/init")
        rapid_names = []
        for i in range(15):
            r = client.get("/api/douyin/next")
            d = r.get_json()
            if d["code"] == 0:
                rapid_names.append(d["data"]["name"])
            else:
                print(f"   [{i+1}] Stopped: code={d['code']}")
                break
        print(f"   Got {len(rapid_names)} videos in rapid succession")
        print(f"   No duplicates: {len(rapid_names) == len(set(rapid_names))}")

    # Cleanup
    for p in [config.DB_PATH, config.DB_PATH + "-wal", config.DB_PATH + "-shm"]:
        if os.path.exists(p):
            os.remove(p)

    config.DB_PATH = None
    config.MEDIA_DIR = None
    print("\nDone.")
