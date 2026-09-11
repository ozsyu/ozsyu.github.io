
(function () {
  var data = window.ITEMS || [];
  var list = document.getElementById('list');
  var count = document.getElementById('count');
  var state = { sort: 'reviews', band: 'all' };

  var bands = {
    all: function () { return true; },
    low: function (p) { return p.price < LOW; },
    mid: function (p) { return p.price >= LOW && p.price < HIGH; },
    high: function (p) { return p.price >= HIGH; }
  };

  var sorters = {
    reviews: function (a, b) { return b.review_count - a.review_count; },
    cheap: function (a, b) { return a.price - b.price; },
    dear: function (a, b) { return b.price - a.price; },
    rated: function (a, b) {
      if (b.review_average !== a.review_average) return b.review_average - a.review_average;
      return b.review_count - a.review_count;
    }
  };

  var maxRev = data.reduce(function (m, p) { return Math.max(m, p.review_count); }, 1);

  function yen(n) { return n.toLocaleString('ja-JP'); }

  function render() {
    var rows = data.filter(function (p) { return bands[state.band](p); });
    rows.sort(sorters[state.sort]);
    count.textContent = rows.length + '件を表示中（全' + data.length + '件）';

    if (!rows.length) {
      list.innerHTML = '<li class="empty">この価格帯の商品はありません。別の帯を選んでください。</li>';
      return;
    }

    list.innerHTML = rows.map(function (p) {
      var w = Math.max(2, Math.round(p.review_count / maxRev * 100));
      return '<li>'
        + '<img src="' + p.img + '" alt="" loading="lazy">'
        + '<div>'
        +   '<p class="title"><a href="' + p.url + '" target="_blank" rel="nofollow sponsored noopener">'
        +     p.name + '</a></p>'
        +   '<p class="shop">' + p.shop + '</p>'
        + '</div>'
        + '<div class="stats">'
        +   '<div class="price">' + yen(p.price) + '<small>円</small></div>'
        +   '<div class="rev">評価 ' + p.review_average.toFixed(2) + '／レビュー ' + yen(p.review_count) + '件</div>'
        +   '<div class="bar"><i style="width:' + w + '%"></i></div>'
        +   '<a class="go" href="' + p.url + '" target="_blank" rel="nofollow sponsored noopener">楽天で見る</a>'
        + '</div>'
        + '</li>';
    }).join('');
  }

  document.querySelectorAll('[data-sort],[data-band]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var kind = btn.dataset.sort ? 'sort' : 'band';
      var value = btn.dataset.sort || btn.dataset.band;
      state[kind] = value;
      document.querySelectorAll('[data-' + kind + ']').forEach(function (b) {
        b.setAttribute('aria-pressed', String(b === btn));
      });
      render();
    });
  });

  render();
})();
