#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from flask import Flask, jsonify, request, render_template, current_app
from flask_sqlalchemy import SQLAlchemy
from pathlib import Path
import threading, json, time, os, traceback

from scraper import TMDBClient, scrape_one
from models import db, init_db, MovieCache

# -------------------------------------------------
# 初始化 Flask
# -------------------------------------------------
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mediamm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# 允许多线程访问同一个 SQLite 连接
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "connect_args": {"check_same_thread": False}
}

db.init_app(app)
# init_db(app)

# -------------------------------------------------
# 读取 config.json
# -------------------------------------------------
cfg_path = Path("config.json")
if cfg_path.exists():
    with open(cfg_path, "r", encoding="utf-8") as f:
        CFG = json.load(f)
else:
    CFG = {"tmdb": {"api_key": "", "language": "zh-CN"}}
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(CFG, f, indent=2, ensure_ascii=False)
    print("⚠️ 未找到 config.json，已生成模板，请填写 TMDB API Key 后重启。")

tmdb = TMDBClient(CFG["tmdb"]["api_key"])
ROOT_DIR_DEFAULT = CFG["scan"]["root_dir"]

queue_lock = threading.Lock()
active_jobs = {}
SCAN_EXT = {".mp4", ".mkv", ".mov", ".avi", ".flv"}

# -------------------------------------------------
# 扫描目录
# -------------------------------------------------
@app.get("/api/scan")
def api_scan():
    root = Path(request.args.get("root", "."))
    if not root.exists():
        return jsonify({"ok": False, "error": f"目录不存在: {root}"})
    items = []
    for p in root.glob("**/*"):
        if p.is_file() and p.suffix.lower() in SCAN_EXT:
            cache = db.session.get(MovieCache, str(p))
            items.append({
                "name": p.name,
                "path": str(p),
                "has_poster": cache.poster if cache else False,
                "has_nfo": cache.nfo if cache else False,
                "has_fanart": cache.fanart if cache else False
            })
    return jsonify({"ok": True, "items": items})

# -------------------------------------------------
# 搜索 TMDB
# -------------------------------------------------
@app.get("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    year = request.args.get("year", "").strip()
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
        th = threading.Thread(target=_run_scrape_job, args=(app_obj, movie_path, tmdb_id, opts), daemon=True)
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
def _run_scrape_job(app, movie_path: Path, tmdb_id: int, opts: dict):
    """线程执行刮削任务"""
    with app.app_context():
        job_id = str(movie_path)
        try:
            meta = tmdb.fetch_movie_full(tmdb_id, language=opts["lang"])
            cache = db.session.get(MovieCache, job_id) or MovieCache(path=job_id)
            cache.tmdb_id = tmdb_id
            cache.title = meta.get("title") or meta.get("original_title")
            cache.year = (meta.get("release_date") or "")[:4]
            cache.poster = cache.fanart = cache.nfo = False
            cache.last_error = None
            db.session.add(cache)
            db.session.commit()

            # 阶段1：下载海报
            scrape_one(movie_path, meta, CFG, {**opts, "stage": "poster"})
            cache.poster = True
            db.session.commit()

            # 阶段2：生成 NFO
            scrape_one(movie_path, meta, CFG, {**opts, "stage": "nfo"})
            cache.nfo = True
            db.session.commit()

            # 阶段3：下载背景
            scrape_one(movie_path, meta, CFG, {**opts, "stage": "fanart"})
            cache.fanart = True
            db.session.commit()

        except Exception as e:
            print(f"[刮削失败] {movie_path}: {e}")
            traceback.print_exc()
        finally:
            db.session.remove()  # 如果你还保留了数据库
            with queue_lock:
                if job_id in active_jobs:
                    active_jobs.pop(job_id, None)
            print(f"[任务结束] {movie_path}")

# -------------------------------------------------
# 查询任务状态
# -------------------------------------------------
@app.get("/api/job")
def api_job():
    """检测任务是否仍在运行 + 自动向下一层目录查找影片文件"""
    job_id = request.args.get("id")
    if not job_id:
        return jsonify({"running": False, "cache": None})

    jp = Path(job_id)

    # 线程是否仍在运行
    with queue_lock:
        running = job_id in active_jobs

    search_dirs = []

    # 如果原始文件还在（未重命名）
    if jp.exists():
        search_dirs.append(jp.parent)

    # 否则它可能被移动到了“电影名 (年份)”文件夹里
    if not search_dirs and jp.parent.exists():
        parent = jp.parent
        for sub in parent.iterdir():
            if sub.is_dir():
                # 兼容中英文、带空格/括号
                if jp.stem.split(".")[0] in sub.name:
                    search_dirs.append(sub)
                    break
        # 如果上面没找到，也兜底搜索所有子目录
        if not search_dirs:
            for sub in parent.iterdir():
                if sub.is_dir():
                    search_dirs.append(sub)

    # 检查文件
    poster = nfo = fanart = False
    for d in search_dirs:
        try:
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
        except Exception:
            pass

    cache = {"poster": poster, "nfo": nfo, "fanart": fanart}
    print(f"[/api/job] 查找目录={[str(p) for p in search_dirs]} → cache={cache}")

    # 如果三个文件都存在，就认为任务完成
    if poster and nfo and fanart:
        running = False

    return jsonify({"running": running, "cache": cache})




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
    # 关闭 debug 模式，防止多进程 reloader 导致线程锁
    app.run(host="0.0.0.0", port=8003, debug=False, threaded=True)
