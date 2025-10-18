// 元素引用
const grid = document.getElementById('grid');
const rootInput = document.getElementById('root');
const btnScan = document.getElementById('btn-scan');
const dlg = document.getElementById('dlg-search');
const q = document.getElementById('q');
const year = document.getElementById('year');
const btnDoSearch = document.getElementById('btn-do-search');
const results = document.getElementById('results');
const currentFile = document.getElementById('current-file');
const btnDownloadSub = document.getElementById('btn-download-sub');

rootInput.value = window.DEFAULT_ROOT || '';
let currentItem = null;

// 扫描目录
btnScan.onclick = async () => {
  const root = rootInput.value.trim();
  const r = await fetch(`/api/scan?root=${encodeURIComponent(root)}`);
  const j = await r.json();
  if (!j.ok) return alert(j.error || '扫描失败');
  renderGrid(j.items);
};

function renderGrid(items) {
  grid.innerHTML = '';
  items.forEach(it => {
    const c = document.createElement('div');
    c.className = 'card';
    c.dataset.path = it.path; // ✅ 唯一标识
    const s = [];
    if (it.has_poster) s.push('海报');
    if (it.has_nfo) s.push('NFO');
    if (it.has_fanart) s.push('背景');
    c.innerHTML = `
      <div class="title">${it.name}</div>
      <div class="meta">${s.join(' / ') || '未刮削'}</div>
      <div class="actions"><button class="btn-search">手动搜索</button></div>`;
    c.querySelector('.btn-search').onclick = () => openSearch(it);
    grid.appendChild(c);
  });
}

// 打开搜索弹窗
function openSearch(item) {
  currentItem = item;
  currentFile.textContent = `当前文件: ${item.name}`;
  q.value = guessTitle(item.name);
  year.value = '';
  results.innerHTML = '';
  dlg.showModal();
}

// 点击搜索按钮
btnDoSearch.onclick = async () => {
  const qs = q.value.trim().replace(/[._]+/g, ' ');
  const yr = year.value.trim();
  if (!qs) return alert('请输入搜索关键词');
  results.innerHTML = '<p>正在搜索，请稍候...</p>';
  try {
    const r = await fetch(`/api/search?q=${encodeURIComponent(qs)}&year=${encodeURIComponent(yr)}`);
    const j = await r.json();
    if (!j.ok) return alert(j.error || '搜索失败');
    renderResults(j.results);
  } catch (e) {
    alert('搜索出错: ' + e);
  }
};

btnDownloadSub.onclick = async () => {
  if (!currentItem) return alert('未选定影片');

  // 用当前右栏 title 作为关键字，或者用 guessTitle(currentItem.name)
  const kv = q.value.trim().replace(/[._]+/g, ' ');
  const query = kv.replace(/\(\d{4}\)/, '').trim();

  try {
    // 1) 搜索字幕
    const sRes = await fetch(`/api/subtitles/search?q=${encodeURIComponent(query)}`);
    const sJson = await sRes.json();
    if (!sJson.ok) return alert(sJson.error || '字幕搜索失败');

    const list = sJson.results || [];
    if (!list.length) return alert('未找到可用字幕');

    // 简易选择器：弹出一个 prompt 让用户输入序号
    let menu = list
      .slice(0, 10) // 只展示前 10 条
      .map((it, i) => `[${i+1}] ${it.release} (${it.lang || ''})`)
      .join('\n');

    let idx = 0;
    if (list.length > 1) {
      const ans = prompt(`选择字幕序号：\n${menu}\n\n输入 1-${Math.min(list.length,10)}：`, '1');
      if (!ans) return;
      idx = Math.max(1, Math.min(parseInt(ans, 10) || 1, Math.min(list.length,10))) - 1;
    }

    const chosen = list[idx];
    // 2) 下载
    const dRes = await fetch('/api/subtitles/download', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ path: currentItem.path, sub_id: chosen.id, lang: 'chs' })
    });
    const dJson = await dRes.json();
    if (!dJson.ok) return alert(dJson.error || '字幕下载失败');

    alert(`字幕已保存：\n${dJson.saved}`);
  } catch (e) {
    console.error('字幕下载异常', e);
    alert('字幕下载异常，请查看控制台日志');
  }
};


// 渲染搜索结果
function renderResults(list) {
  results.innerHTML = '';
  if (!list.length) {
    results.innerHTML = '<p>未找到匹配结果</p>';
    return;
  }
  list.forEach(r => {
    const d = document.createElement('div');
    d.className = 'result';
    d.innerHTML = `
      <img src="${r.poster || ''}" alt="poster">
      <div>
        <div class="r-title">${r.title} <span class="year">${(r.release_date || '').slice(0,4)}</span></div>
        <div>${r.overview || ''}</div>
        <button class="btn-choose">选择</button>
      </div>`;
    d.querySelector('.btn-choose').onclick = () => chooseResult(r.id);
    results.appendChild(d);
  });
}

// 点击选择按钮
async function chooseResult(id) {
  if (!currentItem) return alert('未选定影片');
  const body = { path: currentItem.path, tmdb_id: id };
  const res = await fetch('/api/scrape', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const j = await res.json();
  if (!j.ok) return alert(j.error || '提交失败');

  dlg.close();
  showMoviePreview(j.info, j.job_id, currentItem);
}

// 展示影片简介 + 实时进度
function showMoviePreview(info, jobId, item) {
  const card = document.querySelector(`.card[data-path="${item.path}"]`);
  if (!card) return;

  card.innerHTML = `
    <div class="poster"><img src="${info.poster_url || ''}" alt="poster"></div>
    <div class="movie-info">
      <h3>${info.title} (${info.year || '—'})</h3>
      <p class="genres">${info.genres?.join(', ') || ''}</p>
      <p class="rating">评分：${info.rating ? info.rating.toFixed(1) : '暂无'}</p>
      <p class="overview">${info.overview || '暂无简介'}</p>
      <div class="progress">正在刮削元数据，请稍候...</div>
    </div>
  `;

  pollJobStatus(jobId, card, item.path);
}


// 轮询进度 + 完成状态
function pollJobStatus(jobId, card, path) {
  const progress = card.querySelector('.progress');
  let stopped = false;
  let timer = null;

  async function checkStatus() {
    if (stopped) return;
    try {
      const res = await fetch(`/api/job?id=${encodeURIComponent(jobId)}&t=${Date.now()}`, {
        cache: "no-store"
      });

      // 如果 HTTP 状态异常
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // 尝试解析 JSON
      const data = await res.json();
      console.log('[pollJobStatus]', data);

      // 如果返回异常
      if (!data || typeof data.running === "undefined") {
        throw new Error("invalid json");
      }

      const s = data.cache || {};

      // ✅ 刮削完成
      if (!data.running) {
        stopped = true;
        clearInterval(timer);
        if (s.poster && s.nfo && s.fanart) {
          progress.textContent = "✅ 刮削完成";
          progress.style.color = "lime";
        } else if (s.poster || s.nfo || s.fanart) {
          progress.textContent = "⚠️ 部分文件缺失";
          progress.style.color = "orange";
        } else {
          progress.textContent = "❌ 未生成文件";
          progress.style.color = "red";
        }

        // 局部刷新状态
        refreshSingleCard(path);
        return;
      }

      // ⏳ 仍在运行中
      progress.textContent = `刮削中... ${[
        s.poster ? "海报✓" : "海报…",
        s.nfo ? "NFO✓" : "NFO…",
        s.fanart ? "背景✓" : "背景…"
      ].join(" ")}`;
    } catch (e) {
      stopped = true;
      clearInterval(timer);
      console.error("[pollJobStatus 错误]", e);
      progress.textContent = "❌ 网络异常，请重试";
      progress.style.color = "red";
    }
  }

  // 启动定时轮询
  timer = setInterval(checkStatus, 2000);
  // 马上执行一次，避免延迟 2s 才显示
  checkStatus();
}

async function refreshSingleCard(path) {
  try {
    const r = await fetch(`/api/scan?root=${encodeURIComponent(rootInput.value.trim())}`);
    const j = await r.json();
    if (!j.ok) return;

    const updated = j.items.find(x => x.path === path);
    if (!updated) return;

    const card = document.querySelector(`.card[data-path="${path}"]`);
    if (!card) return;

    const s = [];
    if (updated.has_poster) s.push('海报');
    if (updated.has_nfo) s.push('NFO');
    if (updated.has_fanart) s.push('背景');
    const progress = card.querySelector('.progress');
    if (progress) {
      progress.textContent = `✅ ${s.join(' / ')}`;
      progress.style.color = 'lime';
    }
  } catch (e) {
    console.warn('[refreshSingleCard] 局部刷新失败', e);
  }
}

// 标题清洗
function guessTitle(filename) {
  return filename
    .replace(/\.[^.]+$/, '')
    .replace(/[._]/g, ' ')
    .replace(/\b(\d{3,4}p|web[- ]?dl|bluray|uhd|hdr|10bit|hevc|dts[- ]?x|ma|atmos|beast|x264|x265|aac|ddp|remux|repack|dual|audio|dolby|vision)\b/ig, '')
    .replace(/\s+/g, ' ')
    .trim();
}
