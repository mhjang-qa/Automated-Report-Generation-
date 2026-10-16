(() => {
  const $ = id => document.getElementById(id);
  const key = 'qa-defect-search-history-v1';
  let active = false, pollTimer, controller, generation = 0, lastQuery = '', offset = 0, displayed = 0;
  let waiting = false, resultIndexStamp = 0, history = [];
  const filterIds = {platform:'searchPlatform', severity:'searchSeverity', status:'searchStatus', target_version:'searchVersion', date_from:'searchDateFrom', date_to:'searchDateTo'};
  try { const saved = JSON.parse(localStorage.getItem(key) || '[]'); history = Array.isArray(saved) ? saved.filter(s => typeof s === 'string').slice(0,8) : []; } catch (_) {}
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  function renderHistory() {
    const target = $('searchHistory'); target.replaceChildren();
    if (!history.length) return;
    target.append(node('span','최근 검색','meta'));
    for (const text of history) {
      const button = node('button', text, 'ghost search-history-item'); button.type = 'button';
      button.onclick = () => { $('defectQuery').value = text; runSearch(); };
      target.append(button);
    }
    const clear = node('button','기록 삭제','ghost'); clear.type = 'button';
    clear.onclick = () => { history = []; try {localStorage.removeItem(key);} catch (_) {} renderHistory(); };
    target.append(clear);
  }
  function remember(query) {
    history = [query, ...history.filter(q => q !== query)].slice(0,8);
    try { localStorage.setItem(key, JSON.stringify(history)); } catch (_) {}
    renderHistory();
  }
  async function api(url, options = {}) {
    const response = await fetch(url, {credentials:'same-origin', ...options});
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.message || '요청에 실패했습니다.');
    return data;
  }
  function showStatus(state) {
    const stamp = state.indexed_at ? new Date(state.indexed_at*1000).toLocaleString('ko-KR') : '';
    $('searchRefresh').disabled = state.status === 'indexing';
    $('searchIndexStatus').textContent = state.status === 'indexing'
      ? `색인 생성 중 · ${state.processed || 0}/${state.total_pages || '?'}건${state.ready ? (state.content_status === 'properties_only' ? ' · 제목/속성 우선 검색 가능, 본문 수집 중' : ' · 이전 색인으로 검색합니다.') : ''}`
      : state.status === 'error' ? `${state.message}${state.ready ? ' 마지막 색인으로 검색할 수 있습니다.' : ''} (재시도 간격 30초)`
      : state.ready ? `색인 ${state.count}건 · ${stamp}${state.warnings?.length ? ' · '+state.warnings.join(' ') : ''}`
      : '첫 검색 또는 색인 갱신을 선택하면 Notion에서 데이터를 수집합니다.';
  }
  async function poll() {
    clearTimeout(pollTimer);
    if (!active) return;
    try {
      const state = await api('/api/defects/status'); showStatus(state);
      if (waiting && state.status === 'error' && !state.ready) {
        waiting = false;
        $('searchMessage').textContent = state.message;
      }
      if (state.ready && (waiting || (lastQuery && state.status === 'ready' && resultIndexStamp && state.indexed_at !== resultIndexStamp))) {
        waiting = false; runSearch();
      }
      if (state.status === 'indexing' || waiting) pollTimer = setTimeout(poll, 2000);
    } catch (error) { $('searchIndexStatus').textContent = '색인 상태 확인 실패: '+error.message; }
  }
  function highlight(element, text, terms) {
    // Build text nodes/mark elements only: Notion content never becomes executable HTML.
    if (!terms.length) { element.textContent = text; return; }
    const escaped = [...new Set(terms)].filter(Boolean).sort((a,b) => b.length-a.length).map(t => t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
    if (!escaped.length) { element.textContent = text; return; }
    const pattern = new RegExp(escaped.join('|'), 'gi');
    let cursor = 0;
    for (const match of text.matchAll(pattern)) {
      element.append(document.createTextNode(text.slice(cursor, match.index)), node('mark',match[0]));
      cursor = match.index+match[0].length;
    }
    element.append(document.createTextNode(text.slice(cursor)));
  }
  function resultCard(result) {
    const card = node('article', undefined, 'search-result');
    const head = node('div', undefined, 'search-result-head');
    head.append(node('span', `${result.score}% · ${result.match_label}`, 'search-score'));
    if (result.duplicate_label) head.append(node('span', '⚠ '+result.duplicate_label, 'search-duplicate'));
    card.append(head);
    const title = node('h3');
    const link = node('a'); link.href = '/notion-open.html?id='+encodeURIComponent(result.id); link.target = '_blank'; link.rel = 'noopener noreferrer';
    highlight(link,result.title,result.matched_keywords); title.append(link); card.append(title);
    const meta = node('dl',undefined,'search-result-meta');
    const labels = {platform:'OS', severity:'심각도', priority:'우선순위', status:'상태',target_version:'목표버전',environment:'환경',created_at:'등록',updated_at:'수정',assignee:'담당자'};
    for (const [field,label] of Object.entries(labels)) if (result[field]) {
      const item = node('div'); item.append(node('dt',label),node('dd',result[field])); meta.append(item);
    }
    card.append(meta);
    const snippet = node('p',undefined,'search-snippet'); highlight(snippet,result.snippet || '',result.matched_keywords); card.append(snippet);
    const tags = node('div',undefined,'search-keywords');
    for (const keyword of result.matched_keywords) tags.append(node('span','#'+keyword));
    card.append(tags);
    const details = node('details'); details.append(node('summary','일치 근거'));
    const reasons = node('ul'); for (const reason of result.reasons) reasons.append(node('li',reason)); details.append(reasons); card.append(details);
    const actions = node('div',undefined,'search-result-actions');
    const open = node('a','Notion에서 열기 ↗'); open.href = link.href; open.target = '_blank'; open.rel = 'noopener noreferrer'; actions.append(open);
    const web = node('a','웹에서 열기'); web.href = 'https://www.notion.so/'+result.id.replaceAll('-',''); web.target='_blank'; web.rel='noopener noreferrer'; actions.append(web);
    card.append(actions); return card;
  }
  function facets(data) {
    for (const [field,id] of Object.entries(filterIds)) {
      if (!data[field]) continue;
      const select = $(id), current = select.value;
      const first = select.options[0].cloneNode(true); select.replaceChildren(first);
      for (const text of [...new Set([...data[field], ...(current ? [current] : [])])]) {
        const option = node('option',text); option.value=text; select.append(option);
      }
      select.value=current;
    }
  }
  async function runSearch(more = false) {
    const query = $('defectQuery').value.trim();
    if (!query) { $('searchMessage').textContent = '검색할 제목, 화면명 또는 현상을 입력해 주세요.'; return; }
    if ($('searchDateFrom').value && $('searchDateTo').value && $('searchDateFrom').value > $('searchDateTo').value) {
      $('searchMessage').textContent = '등록 기간의 시작일과 종료일을 확인하세요.'; return;
    }
    controller?.abort(); controller = new AbortController(); const current = ++generation;
    if (!more) {offset=0; displayed=0; $('searchResults').replaceChildren();}
    lastQuery=query; waiting=false;
    const params = new URLSearchParams({q:query,offset:String(offset),limit:'20'});
    for (const [field,id] of Object.entries(filterIds)) if ($(id).value) params.set(field,$(id).value);
    $('searchResults').setAttribute('aria-busy','true');
    $('defectSearchSubmit').disabled=true; $('searchMore').disabled=true;
    $('searchMessage').textContent='검색 중…';
    try {
      const data = await api('/api/defects/search?'+params,{signal:controller.signal});
      if (current !== generation) return;
      remember(query); showStatus(data.index); facets(data.facets || {});
      resultIndexStamp = data.index.indexed_at || 0;
      if (!data.index.ready) {
        waiting=data.index.status === 'indexing';
        $('searchMessage').textContent=waiting ? 'Notion 색인 생성 중입니다. 완료되면 자동으로 검색합니다.' : data.index.message;
        $('searchMore').classList.add('hidden'); poll(); return;
      }
      for (const result of data.results) $('searchResults').append(resultCard(result));
      displayed += data.results.length; offset=displayed;
      $('searchResultTitle').textContent=`검색 결과 ${data.total}건`;
      $('searchMessage').textContent = data.total ? `관련도 순 · ${displayed}건 표시${data.candidate_limit_reached ? ' · 후보 상한 500건에 도달했습니다. 더 구체적으로 검색하세요.' : ''}` : '정확히 일치하는 결함을 찾지 못했습니다. 검색어를 줄이거나 화면명 / 기능명 / 현상 중심으로 다시 검색해보세요. 필터도 확인해 주세요.';
      $('searchMore').classList.toggle('hidden',!data.has_more);
      if (data.index.status==='indexing') poll();
    } catch (error) {
      if (error.name !== 'AbortError' && current === generation) {
        $('searchMessage').textContent='검색 실패: '+error.message+' 네트워크 연결과 로그인 상태를 확인한 뒤 다시 검색하세요.';
        $('searchMore').classList.add('hidden');
      }
    } finally {
      if (current === generation) { $('defectSearchSubmit').disabled=false; $('searchMore').disabled=false; $('searchResults').setAttribute('aria-busy','false'); }
    }
  }
  $('defectSearchForm').addEventListener('submit', event => {event.preventDefault(); runSearch();});
  $('searchMore').onclick=() => runSearch(true);
  for (const id of Object.values(filterIds)) $(id).addEventListener('change', () => {if (lastQuery) runSearch();});
  $('searchReset').onclick=() => {for (const id of Object.values(filterIds)) $(id).value=''; if (lastQuery) runSearch();};
  $('searchRefresh').onclick=async () => {
    $('searchRefresh').disabled=true;
    try {const data=await api('/api/defects/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}); showStatus(data.index); if (lastQuery) waiting=true; poll();}
    catch (error) {$('searchIndexStatus').textContent=error.message; $('searchRefresh').disabled=false;}
  };
  window.DefectSearch={setActive(value) {active=value; clearTimeout(pollTimer); if (active) poll();}};
  renderHistory();
})();
