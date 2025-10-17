from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from pathlib import Path

def _txt(x): return '' if x is None else str(x)

def write_movie_nfo(meta: dict, folder: Path, basename: str = "movie"):
    """
    将 NFO 写到 folder / f"{basename}.nfo"
    默认 basename = "movie"，但推荐从外部传入影片同名（如 '片名.年份.分辨率'）
    """
    from xml.etree.ElementTree import Element, SubElement, tostring
    from xml.dom import minidom

    def _txt(x): return '' if x is None else str(x)

    root = Element('movie')

    def E(tag, text=None):
        el = SubElement(root, tag)
        if text is not None and text != '':
            el.text = str(text)
        return el

    # 标题 / 原名 / 年份 / 剧情
    E('title', meta.get('title') or meta.get('original_title'))
    if meta.get('original_title'):
        E('originaltitle', meta.get('original_title'))
    year = (meta.get('release_date') or '')[:4]
    if year: E('year', year)
    if meta.get('overview'): E('plot', meta.get('overview'))

    # 评分（TMDB）
    rating = meta.get('vote_average')
    if rating is not None:
        r = SubElement(root, 'ratings')
        tm = SubElement(r, 'rating')
        SubElement(tm, 'name').text = 'tmdb'
        SubElement(tm, 'value').text = str(rating)
        SubElement(tm, 'max').text = '10'

    # 外部ID
    ids = meta.get('external_ids') or {}
    if ids.get('imdb_id'): E('imdbid', ids['imdb_id'])
    E('tmdbid', meta.get('id'))

    # 类型 / 标签
    for g in (meta.get('genres') or []):
        E('genre', g.get('name'))
    kws = (meta.get('keywords') or {}).get('keywords') or []
    for k in kws:
        E('tag', k.get('name'))

    # 导演 / 编剧
    credits = (meta.get('credits') or {})
    for c in credits.get('crew', []):
        job = c.get('job')
        if job == 'Director':
            E('director', c.get('name'))
        if job in ('Writer', 'Screenplay'):
            E('writer', c.get('name'))

    # 演员
    actors = SubElement(root, 'actors')
    for a in credits.get('cast', [])[:20]:
        actor = SubElement(actors, 'actor')
        SubElement(actor, 'name').text = _txt(a.get('name'))
        SubElement(actor, 'role').text = _txt(a.get('character'))

    # Pretty 输出
    xml_bytes = tostring(root, encoding='utf-8')
    pretty = minidom.parseString(xml_bytes).toprettyxml(indent='  ', encoding='utf-8')
    out_path = folder / f"{basename}.nfo"
    out_path.write_bytes(pretty)
    print(f"[NFO 完成] {out_path}")
