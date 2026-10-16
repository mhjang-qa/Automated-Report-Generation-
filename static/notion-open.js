(() => {
  const id = new URLSearchParams(location.search).get('id') || '';
  const message = document.querySelector('#landingMessage');
  if (!/^(?:[a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$/i.test(id)) {
    message.textContent = '올바르지 않은 Notion 페이지 ID입니다.';
    return;
  }
  const pageId = id.replaceAll('-', '');
  const web = `https://www.notion.so/${pageId}`;
  const app = `notion://www.notion.so/${pageId}`;
  const webLink = document.querySelector('#landingWeb');
  const appLink = document.querySelector('#landingApp');
  webLink.href = web;
  appLink.href = app;
  let timer;
  function stop() { clearTimeout(timer); }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stop();
      message.textContent = '앱 열기를 시도했습니다. 앱이 열리지 않았다면 브라우저에서 열기를 선택하세요.';
    }
  });
  window.addEventListener('pagehide', stop);
  webLink.addEventListener('click', stop);
  appLink.addEventListener('click', () => {
    stop();
    timer = setTimeout(() => { if (!document.hidden) location.replace(web); }, 1800);
  });
  timer = setTimeout(() => { if (!document.hidden) location.replace(web); }, 1800);
  try { location.href = app; } catch (_) { location.replace(web); }
})();
