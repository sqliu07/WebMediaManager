from __future__ import annotations

from logger import setup_logger
logger = setup_logger()


import io
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

try:
    import py7zr  # 用于 .7z
    HAS_PY7ZR = True
except Exception:
    HAS_PY7ZR = False


LANG_HINTS = {
    "chs": ["chs", "简", "简体", "sc", "zh-cn", "cn", "chinese-simplified"],
    "cht": ["cht", "繁", "繁体", "tc", "zh-tw", "traditional"],
    "eng": ["eng", "english", "en"],
}

def extract_id_from_any(s):
    """
    自动从各种格式中提取字幕ID：
    输入可能是：
      "123456"
      "ID:123456"
      "/sub/123456"
      "sub_123456.chs"
    输出统一为整数，如果提取失败则返回 None
    """
    if isinstance(s, int):
        return s
    if not isinstance(s, str):
        return None
    # 用正则提取数字序列
    match = re.search(r'\d+', s)
    if match:
        return int(match.group(0))
    return None

def _match_lang_by_filename(name: str, target: str) -> bool:
    name_l = name.lower()
    for kw in LANG_HINTS.get(target, []):
        if kw in name_l:
            return True
    # 没找到强提示时，不排除
    return False


class SubtitleDownloader:
    """
    ASSRT (伪装字幕) 下载器：
    - search(query): 返回可选择的字幕条目列表
    - download(sub_id, movie_path, preferred_lang='chs'): 下载并解压、挑选最佳字幕并重命名到影片同目录
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_search = "https://api.assrt.net/v1/sub/search"
        self.base_detail = "https://api.assrt.net/v1/sub/detail"  # 可能用不上，视搜索返回而定

    def _request_json(self, url: str, params: Dict) -> Dict:
        # 自动加上 token
        params = {"token": self.api_key, **params}

        r = requests.get(url, params=params, timeout=15)

        logger.debug(f"[字幕请求] 最终请求 URL: {r.url}")  # ✅ 包含 token 和完整拼接后的参数

        try:
            data = r.json()
            logger.debug(f"[字幕请求] 返回数据(JSON简略):", {str(data)[:200]})  # 只打印前200字符防止过长
        except Exception:
            logger.error(f"[字幕请求] 返回非JSON内容:", {r.text[:200]})

        r.raise_for_status()
        return r.json()
    def search(self, query: str, count: int = 20, pos: int = 0) -> List[Dict]:
        logger.info(f"[字幕搜索] 关键词: {query}")
        params = {"q": query, "cnt": count, "pos": pos}
        j = self._request_json(self.base_search, params)

        # ASSRT 返回结构情况一：{"status":0, "sub":{"subs":[...], ...}}
        subs_section = j.get("sub")

        if isinstance(subs_section, dict):
            subs = subs_section.get("subs", [])
        elif isinstance(subs_section, list):
            subs = subs_section
        else:
            # 不符合预期的 fallback
            subs = j.get("subs", []) or j.get("data", []) or []

        out = []
        for s in subs:
            # 一定要确保是字典类型
            if not isinstance(s, dict):
                continue
            
            sid = s.get("id") or s.get("sub_id") or None
            if not sid:
                # 有些情况下 id 在 urls 链接中
                sid = extract_id_from_any(str(s))

            if not sid:
                continue

            release = s.get("videoname") or s.get("native_name") or s.get("release") or "未知"
            lang = s.get("lang") or s.get("language") or s.get("langchi") or "未知"
            desc = s.get("desc") or s.get("comment") or ""
            files = s.get("files") or []

            out.append({
                "id": sid,
                "release": release,
                "lang": lang,
                "desc": desc,
                "files": files,
                "files_count": len(files)
            })
        logger.info(f"[字幕搜索] 共找到 {len(out)} 条字幕结果")
        return out
    def _get_download_url(self, sub_meta: Dict) -> Optional[str]:
        """
        从搜索条目中找出文件下载链接（大多数为 zip/7z）
        """
        files = sub_meta.get("files") or []
        for f in files:
            # ASSRT 返回的字段一般有 "url"
            url = f.get("url") or f.get("link")
            if url:
                return url
        # 少数情况下需要 detail 接口，但多数搜索结果里含 files
        return None

    def fetch_detail(self, sub_id: int) -> Dict:
        logger.info(f"[字幕详情] 获取字幕ID: {sub_id}")
        return self._request_json(self.base_detail, {"id": sub_id})

    # ----------------------------- 抽取与重命名 -----------------------------

    def _detect_movie_dir_and_base(self, movie_path: Path) -> Tuple[Path, str]:
        """
        根据现有规则，推断最终应当写入字幕的目录和命名基准：
        优先使用同目录内的 .poster/.nfo 的前缀，其次使用影片文件名的 stem。
        返回: (movie_dir, base_name_without_suffix)
        """
        # 1) 如果影片还在原位置
        if movie_path.exists():
            movie_dir = movie_path.parent
            base = movie_path.stem
        else:
            # 2) 影片可能已被移动到 “Title (Year)” 子目录下
            parent = movie_path.parent
            movie_dir = parent
            base = movie_path.stem

        # 3) 如果目录里有 *.poster.jpg / *.nfo，优先用该前缀（和你视频命名保持一致）
        poster = next((p for p in movie_dir.glob("*.poster.jpg")), None)
        nfo = next((p for p in movie_dir.glob("*.nfo")), None)
        if poster:
            base = poster.name.replace(".poster.jpg", "")
        elif nfo:
            base = nfo.stem

        logger.debug(f"[字幕保存路径] 目录: {movie_dir} 文件名: {base}")
        return movie_dir, base

    def _choose_best_sub_file(self, names: List[str], preferred_lang: str) -> Optional[str]:
        """
        从解压得到的字幕文件列表里选择一个最佳的：
        - 优先 .srt，其次 .ass
        - 优先命中语言关键字（chs/简体）
        """
        # 只考虑字幕扩展名
        cand = [n for n in names if re.search(r"\.(srt|ass)$", n, re.I)]
        if not cand:
            return None

        # 先按语言关键字过滤
        lang_hit = [n for n in cand if _match_lang_by_filename(n, preferred_lang)]
        target_list = lang_hit or cand  # 没命中就退而求其次

        # 按扩展优先级：srt > ass
        srt = [n for n in target_list if n.lower().endswith(".srt")]
        if srt:
            return srt[0]
        return target_list[0]

    def _extract_zip_to(self, content: bytes, out_dir: Path) -> List[str]:
        names = []
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            for m in z.infolist():
                # 只解压文件
                if m.is_dir():
                    continue
                out_path = out_dir / Path(m.filename).name
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with z.open(m) as src, open(out_path, "wb") as dst:
                    dst.write(src.read())
                names.append(out_path.name)
        return names

    def _extract_7z_to(self, content: bytes, out_dir: Path) -> List[str]:
        if not HAS_PY7ZR:
            raise RuntimeError("需要安装 py7zr 以解压 .7z 字幕包：pip install py7zr")
        names = []
        bio = io.BytesIO(content)
        with py7zr.SevenZipFile(bio, mode="r") as z:
            z.extractall(path=out_dir)
        for f in out_dir.glob("*"):
            if f.is_file():
                names.append(f.name)
        return names

    # ----------------------------- 对外下载接口 -----------------------------

    def download(self, sub_id: int, movie_path: Path, preferred_lang: str = "chs") -> Dict:
        """
        标准 ASSRT 下载流程：
        1. 通过 detail 接口获取文件
        2. 优先使用 filelist 里的具体字幕文件
        3. 如果没有 filelist，则下载压缩包（url 字段）
        4. 解压/保存，重命名
        """
        # Step 1: 获取完整 detail
        detail = self.fetch_detail(sub_id)
        sub_section = detail.get("sub") or {}
        subs = sub_section.get("subs") or []
        if not subs:
            logger.error(f"[字幕下载] 未找到字幕条目 ID={sub_id}")
            return {"ok": False, "error": "未找到字幕条目"}

        sub_data = subs[0]  # 默认取第一个字幕源（通常是最相关的）

        # Step 2: 获取目标文件夹与命名基准
        movie_dir, base = self._detect_movie_dir_and_base(movie_path)

        # Step 3: 优先处理 filelist（ASSRT 推荐）
        filelist = sub_data.get("filelist") or []

        if filelist:
            # 从 filelist 直接获取字幕文件 URL（无需解压）
            chosen_file = None
            names = []
            for f in filelist:
                url = f.get("url")
                fname = f.get("f") or "subtitle"
                names.append(fname)
                # 匹配 preferred_lang
                if _match_lang_by_filename(fname, preferred_lang):
                    chosen_file = f
                    break
            # 如果没有语言完全匹配，选第一个
            if not chosen_file:
                chosen_file = filelist[0]

            url = chosen_file.get("url")
            if not url:
                raise RuntimeError("filelist 中没有可下载字幕地址")

            # 下载文件内容
            r = requests.get(url, timeout=30)
            r.raise_for_status()

            suffix = Path(chosen_file.get("f", "")).suffix.lower() or ".srt"
            out_path = movie_dir / f"{base}.{preferred_lang}{suffix}"
            out_path.write_bytes(r.content)
            return {"ok": True, "saved": str(out_path)}

        # Step 4: 处理压缩包下载（url 字段）
        pkg_url = sub_data.get("url")
        if not pkg_url:
            raise RuntimeError("未找到压缩包下载链接")

        r = requests.get(pkg_url, timeout=30)
        r.raise_for_status()
        content = r.content

        # 临时目录用于解压
        tmp_dir = movie_dir / ".subs_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # 根据扩展名称尝试自动解压
        names = []
        try:
            # 尝试 ZIP 解压
            names = self._extract_zip_to(content, tmp_dir)
        except Exception:
            # 尝试 7z
            names = self._extract_7z_to(content, tmp_dir)

        if not names:
            raise RuntimeError("压缩包中没有发现字幕文件")

        # Step 5: 选择最佳文件
        chosen_name = self._choose_best_sub_file(names, preferred_lang)
        if not chosen_name:
            raise RuntimeError("没有找到符合要求的字幕文件")

        src = tmp_dir / chosen_name
        suffix = src.suffix.lower()
        out_path = movie_dir / f"{base}.{preferred_lang}{suffix}"

        out_path.write_bytes(src.read_bytes())

        # 清理临时目录
        for f in tmp_dir.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass
        try:
            tmp_dir.rmdir()
        except Exception:
            pass
        
        logger.info(f"[字幕下载完成] {out_path}")
        return {"ok": True, "saved": str(out_path)}

