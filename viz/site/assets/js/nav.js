// 统一导航高亮器（双行模块条配套）：
// - 依据当前 URL 在 .t-nav-links 中点亮对应模块（全站固定顺序、固定编号，杜绝指示冲突）；
// - 回填顶行 CURRENT 指示位；
// - 将激活项水平滚动至模块条可视中央。
(function () {
  function slug() {
    var s = (location.pathname.split('/').pop() || 'index').toLowerCase();
    s = s.replace(/\.html$/, '');
    return s === '' ? 'index' : s;
  }
  function run() {
    var cur = slug();
    var act = null;
    var links = document.querySelectorAll('.t-nav-links a');
    for (var i = 0; i < links.length; i++) {
      var a = links[i];
      var t = (a.getAttribute('href') || '').replace(/\.html$/, '');
      if (t === cur) { a.classList.add('active'); act = a; }
      else a.classList.remove('active');
    }
    var here = document.getElementById('tNavHere');
    if (here && act) {
      var code = act.getAttribute('data-nav-code') || '';
      var name = act.getAttribute('data-nav-name') || '';
      here.textContent = 'CURRENT · ' + code + ' / ' + name;
    }
    if (act && typeof act.scrollIntoView === 'function') {
      try { act.scrollIntoView({ inline: 'center', block: 'nearest' }); } catch (e) { /* 忽略 */ }
    }
  }
  if (document.readyState !== 'loading') run();
  else document.addEventListener('DOMContentLoaded', run);
})();
