from nfo import write_movie_nfo

from pathlib import Path
import requests
import traceback
import re
import shutil
import xml.etree.ElementTree as ET

# ----------------------------------------
# TMDB 客户端类：封装搜索 / 获取电影详情
# ----------------------------------------
class TMDBClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base = "https://api.themoviedb.org/3"

    def _get(self, path: str, params: dict):
        """发送 TMDB GET 请求"""
        params = {"api_key": self.api_key, **params}
        url = f"{self.base}{path}"
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def search_movie(self, query: str, year: str = None):
        """搜索电影"""
        params = {"query": query, "language": "zh-CN"}
        if year:
            params["year"] = year
        j = self._get("/search/movie", params)
        results = []
        for r in j.get("results", []):
            results.append({
                "id": r.get("id"),
                "title": r.get("title"),
                "overview": r.get("overview"),
                "release_date": r.get("release_date"),
                "poster": f"https://image.tmdb.org/t/p/w500{r['poster_path']}" if r.get("poster_path") else None
            })
        return results

    def fetch_movie_full(self, tmdb_id: int, language="zh-CN"):
        """
        返回 TMDB 原始的完整字段（含 credits / keywords / external_ids / images），
        同时附加 poster_url / fanart_url 两个便捷字段，供下载用。
        """
        j = self._get(
            f"/movie/{tmdb_id}",
            {
                "language": language,
                "append_to_response": "credits,images,keywords,external_ids"  # ★ 关键：带上 external_ids
            }
        )
        # 附加便捷直链（原始字段仍保留：poster_path/backdrop_path）
        j["poster_url"] = f"https://image.tmdb.org/t/p/original{j['poster_path']}" if j.get("poster_path") else None
        j["fanart_url"] = f"https://image.tmdb.org/t/p/original{j['backdrop_path']}" if j.get("backdrop_path") else None
        return j


# ----------------------------------------
# 文件处理部分（之前的 scrape_one）
# ----------------------------------------
def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '', name).strip()

def safe_move(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dst.resolve():
        return
    try:
        shutil.move(str(src), str(dst))
    except Exception as e:
        print(f"[重命名失败] {src} → {dst}: {e}")
def scrape_one(movie_path: Path, meta: dict, cfg: dict, opts: dict):
    try:
        stage = opts.get('stage', 'all')
        title = sanitize_filename(meta.get("title") or meta.get("original_title"))
        year = (meta.get("release_date") or "")[:4] or "0000"
        resolution = "2160p" if "2160" in movie_path.name else \
                     "1080p" if "1080" in movie_path.name else "HD"
        
        movie_dir = movie_path.parent / f"{title} ({year})"
        movie_dir.mkdir(parents=True, exist_ok=True)

        new_name = f"{title}.{year}.{resolution}"
        ext = movie_path.suffix.lower()
        new_movie = movie_dir / f"{new_name}{ext}"

        if stage == 'poster':
            safe_move(movie_path, new_movie)

        # 下载海报
        if stage in ('poster', 'all'):
            poster_url = meta.get("poster_url")
            if poster_url:
                r = requests.get(poster_url, timeout=15)
                if r.status_code == 200:
                    poster_path = movie_dir / f"{new_name}.poster.jpg"
                    with open(poster_path, "wb") as f:
                        f.write(r.content)
                    print(f"[海报下载] {poster_path}")

        # 生成 NFO
        if stage in ('nfo', 'all'):
            try:
                write_movie_nfo(meta, movie_dir, basename=new_name) 
                print(f"[NFO 生成] {movie_dir / 'movie.nfo'}")
            except Exception as e:
                print(f"[NFO 生成失败] {e}")

        # 下载背景图
        if stage in ('fanart', 'all'):
            fanart_url = meta.get("fanart_url")
            if fanart_url:
                r = requests.get(fanart_url, timeout=15)
                if r.status_code == 200:
                    fanart_path = movie_dir / f"{new_name}.fanart.jpg"
                    with open(fanart_path, "wb") as f:
                        f.write(r.content)
                    print(f"[背景下载] {fanart_path}")

    except Exception as e:
        print(f"[刮削错误] {movie_path}: {e}")
        traceback.print_exc()
