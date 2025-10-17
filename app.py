#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from flask import Flask, jsonify, request, render_template, current_app
from pathlib import Path
import threading, json, time, traceback
from scraper import TMDBClient, scrape_one

# -------------------------------------------------
# 初始化 Flask
# -------------------------------------------------
app = Flask(__name__, template_folder='templates', static_folder='static')

# -------------------------------------------------
# 读取 config.json
# -------------------------------------------------
cfg_path = Path("config.json")
if cfg_path.exists():
    with open(cfg_path, "r", encoding="utf-8") as f:
        CFG = json.load(f)
else:
    CFG = {"tmdb": {"api_key": "", "language": "zh-CN"}, "scan": {"root_dir": "data"}}
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(CFG, f, indent=2, ensure_ascii=False)
    print("⚠️ 未找到 config.json，已生成模板，请填写 TMDB API Key 后重启。")

tmdb = TMDBClient(CFG["tmdb"]["api_key"])
ROOT_DIR_DEFAULT = CFG.get("scan", {}).get("root_dir", "data")

queue_lock = threading.Lock()
active_jobs = {}
SCAN_EXT = {".mp4", ".mkv", ".mov", ".avi", ".flv"}

# -------------------------------------------------
# 扫描目录
# -------------------------------------------------
@app.get("/api/scan")
def api_scan():
    root = Path(request.args.get("root", ROOT_DIR_DEFAULT))
    if not root.exists():
        return jsonify({"ok": False, "error": f"目录不存在: {root}"})

    items = []
    for p in root.glob("**/*"):
        if p.is_file() and p.suffix.lower() in SCAN_EXT:
            movie_dir = p.parent
            has_poster = any(f.suffix == ".jpg" and ".poster" in f.name.lower() for f in movie_dir.iterdir())
            has_nfo = any(f.suffix == ".nfo" for f in movie_dir.iterdir())
            has_fanart = any(f.suffix == ".jpg" and ".fanart" in f.name.lower() for f in movie_dir.iterdir())

            items.append({
                "name": p.name,
                "path": str(p),
                "has_poster": has_poster,
                "has_nfo": has_nfo,
                "has_fanart": has_fanart
            })
    return jsonify({"ok": True, "items": items})

# -------------------------------------------------
# 搜索 TMDB
# -------------------------------------------------
@app.get("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    year = request.args.get("year", "").strip()
    if not q:
        return jsonify({"ok": False, "error": "缺少参数 q"})
    results = tmdb.search_movie(q, year)
    return jsonify({"ok": True, "results": results})

# -------------------------------------------------
# 启动刮削任务
# -------------------------------------------------
@app.post("/api/scrape")
def api_scrape():
    data = request.get_json(force=True)
    movie_path = Path(data["path"])
    tmdb_id = int(data["tmdb_id"])
    opts = {
        "write_nfo": True,
        "download_images": True,
        "download_subs": False,
        "lang": CFG["tmdb"]["language"]
    }

    print(f"[启动任务] {movie_path}")
    meta = tmdb.fetch_movie_full(tmdb_id, language=opts["lang"])
    job_id = str(movie_path)

    app_obj = current_app._get_current_object()
    with queue_lock:
        if job_id in active_jobs:
            return jsonify({"ok": False, "error": "该条目正在处理中"}), 409
        th = threading.Thread(target=_run_scrape_job, args=(app_obj, movie_path, meta, opts), daemon=True)
        active_jobs[job_id] = th
        th.start()

    info = {
        "title": meta.get("title"),
        "overview": meta.get("overview"),
        "year": (meta.get("release_date") or "")[:4],
        "poster_url": meta.get("poster_url"),
        "rating": meta.get("vote_average"),
        "genres": [g.get("name") for g in meta.get("genres", [])],
    }
    return jsonify({"ok": True, "job_id": job_id, "info": info})

# -------------------------------------------------
# 后台线程任务
# -------------------------------------------------
def _run_scrape_job(app, movie_path: Path, meta: dict, opts: dict):
    with app.app_context():
        job_id = str(movie_path)
        try:
            scrape_one(movie_path, meta, CFG, {**opts, "stage": "poster"})
            scrape_one(movie_path, meta, CFG, {**opts, "stage": "nfo"})
            scrape_one(movie_path, meta, CFG, {**opts, "stage": "fanart"})
        except Exception as e:
            print(f"[刮削失败] {movie_path}: {e}")
            traceback.print_exc()
        finally:
            with queue_lock:
                active_jobs.pop(job_id, None)
            print(f"[任务结束] {movie_path}")

# -------------------------------------------------
# 查询任务状态
# -------------------------------------------------
@app.get("/api/job")
def api_job():
    job_id = request.args.get("id")
    if not job_id:
        return jsonify({"running": False, "cache": {}})

    try:
        jp = Path(job_id)
        with queue_lock:
            running = job_id in active_jobs

        search_dirs = []
        if jp.exists():
            search_dirs.append(jp.parent)
        else:
            parent = jp.parent
            if parent.exists():
                for sub in parent.iterdir():
                    if sub.is_dir() and jp.stem.split(".")[0] in sub.name:
                        search_dirs.append(sub)
                        break
                if not search_dirs:
                    search_dirs.extend([d for d in parent.iterdir() if d.is_dir()])

        poster = nfo = fanart = False
        for d in search_dirs:
            for f in d.glob("*"):
                name = f.name.lower()
                if ".poster" in name and name.endswith(".jpg"):
                    poster = True
                elif name.endswith(".nfo"):
                    nfo = True
                elif ".fanart" in name and name.endswith(".jpg"):
                    fanart = True
            if poster and nfo and fanart:
                break

        cache = {"poster": poster, "nfo": nfo, "fanart": fanart}
        print(f"[/api/job] 查找目录={[str(p) for p in search_dirs]} → cache={cache}")
        print("[api_job返回]", {"running": running, "cache": cache})
        return jsonify({"running": running, "cache": cache})
    except Exception as e:
        print("[api_job异常]", e)
        traceback.print_exc()
        return jsonify({"running": False, "cache": {}, "error": str(e)})


# -------------------------------------------------
# 首页
# -------------------------------------------------
@app.get("/")
def index():
    return render_template("index.html", default_root=ROOT_DIR_DEFAULT)

# -------------------------------------------------
# 启动应用
# -------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8003, debug=False, threaded=True)
