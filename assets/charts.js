(function () {
  var data = window.AKSHARE_MARKET_DATA || {};
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var blue = style.getPropertyValue('--blue').trim();
  var green = style.getPropertyValue('--green').trim();

  var sentiment = data.sentiment || {
    temperature: 78,
    stage: '主升中段',
    stage_desc: '示例数据',
    limit_up_count: 112,
    highest_board: 7,
    break_rate: 18,
    promotion_rate: 52,
    suggested_position: 50,
    cash_buffer: 30,
    flex_position: 20
  };

  var trendData = data.trend || {
    dates: ['06/02','06/03','06/04','06/05','06/06','06/09','06/10','06/11','06/12','06/13'],
    limit_ups: [42, 35, 51, 58, 47, 62, 70, 84, 92, 85],
    heights: [3, 2, 4, 4, 3, 5, 5, 6, 6, 6],
    temperatures: [38, 32, 50, 55, 48, 62, 68, 74, 80, 75]
  };

  var themes = data.themes || [];
  var premarket = data.premarket || [];
  var intraday = data.intraday || [];
  var tracking = data.tracking || [];

  function $(selector) {
    return document.querySelector(selector);
  }

  function setText(selector, value) {
    var el = $(selector);
    if (el) el.textContent = value;
  }

  function formatTradeDate(d) {
    if (!d || d.length !== 8) return d || '--';
    return d.slice(0, 4) + '-' + d.slice(4, 6) + '-' + d.slice(6, 8);
  }

  function badgeClass(value) {
    if (value >= 75 || /主升|加速/.test(String(value))) return 'hot';
    if (value >= 50 || /活跃|修复|分歧/.test(String(value))) return 'warm';
    return 'cool';
  }

  function stageIndex(stage) {
    stage = String(stage || '');
    if (stage.indexOf('冰点') >= 0) return 0;
    if (stage.indexOf('修复') >= 0) return 1;
    if (stage.indexOf('主升') >= 0) return 2;
    if (stage.indexOf('高潮') >= 0) return 3;
    if (stage.indexOf('退潮') >= 0) return 4;
    return 2;
  }

  function renderHeader() {
    var metaCells = document.querySelectorAll('.top-meta .meta-cell strong');
    if (metaCells[0]) metaCells[0].textContent = formatTradeDate(data.meta && data.meta.trade_date);
    if (metaCells[1]) {
      metaCells[1].textContent = sentiment.stage + ' · ' + sentiment.temperature + '℃';
      metaCells[1].style.color = sentiment.temperature >= 70 ? accent : sentiment.temperature >= 45 ? accent2 : blue;
    }
    var pulse = $('.pulse');
    if (pulse) {
      pulse.textContent = 'AKSHARE · ' + (data.meta ? data.meta.source : '演示数据');
    }
  }

  function renderKpis() {
    var cards = document.querySelectorAll('.kpi-card');
    var kpis = [
      {
        label: '涨停家数',
        value: String(sentiment.limit_up_count || 0),
        cls: 'up',
        delta: '来自 AkShare 涨停池 · ' + (data.raw_counts ? data.raw_counts.limit_up_pool : 0) + ' 条'
      },
      {
        label: '最高连板',
        value: String(sentiment.highest_board || 0) + '板',
        cls: sentiment.highest_board >= 5 ? 'up' : 'warm',
        delta: sentiment.highest_board >= 5 ? '高度打开 · 风险偏好较强' : '高度一般 · 关注低位首板'
      },
      {
        label: '炸板率',
        value: (sentiment.break_rate || 0).toFixed ? sentiment.break_rate.toFixed(2) + '%' : sentiment.break_rate + '%',
        cls: sentiment.break_rate <= 25 ? 'warm' : 'down',
        delta: sentiment.break_rate <= 25 ? '封板较稳 · 可提高攻击性' : '炸板偏高 · 追板需降低仓位'
      },
      {
        label: '昨日涨停晋级率',
        value: (sentiment.promotion_rate || 0).toFixed ? sentiment.promotion_rate.toFixed(2) + '%' : sentiment.promotion_rate + '%',
        cls: sentiment.promotion_rate >= 35 ? 'up' : 'warm',
        delta: '昨日涨停今日继续涨停占比'
      }
    ];

    cards.forEach(function (card, i) {
      var item = kpis[i];
      if (!item) return;
      var label = card.querySelector('.label');
      var value = card.querySelector('.value');
      var delta = card.querySelector('.delta');
      if (label) label.textContent = item.label;
      if (value) {
        value.className = 'value ' + item.cls;
        value.textContent = item.value;
      }
      if (delta) {
        delta.className = 'delta ' + (item.cls === 'down' ? 'down' : 'up');
        delta.textContent = item.delta;
      }
    });
  }

  function renderStage() {
    var spans = document.querySelectorAll('.stage-strip span');
    var active = stageIndex(sentiment.stage);
    spans.forEach(function (span, i) {
      span.classList.toggle('active', i === active);
    });
    var desc = $('.gauge-box p');
    if (desc) {
      desc.innerHTML = '情绪指数 <strong style="color: var(--accent);">' + sentiment.temperature + '℃</strong>，当前处于 <strong style="color: var(--accent2);">' + sentiment.stage + '</strong>。' + sentiment.stage_desc + '；模型建议总仓位 <strong style="color: var(--accent);">' + sentiment.suggested_position + '%</strong>。';
    }
  }

  function renderThemes() {
    var list = $('#theme-list');
    if (!list || !themes.length) return;
    var header = '<div class="theme-row" style="border-bottom: 1px solid var(--rule); color: var(--muted); font-size: 0.7rem; font-family: var(--font-mono); letter-spacing: 0.08em;">' +
      '<div>RK</div><div>题材 / 龙头</div><div class="heat">热度</div><div class="role">金额</div><div>涨停</div><div>状态</div></div>';
    var rows = themes.map(function (t, i) {
      var leaders = (t.leaders || []).map(function (x) { return x.name + '(' + x.board + '板)'; }).join(' / ') || '暂无';
      return '<div class="theme-row">' +
        '<div class="rank">' + (i + 1) + '</div>' +
        '<div class="name"><strong>' + t.name + '</strong><div class="desc">前排 · ' + leaders + '</div></div>' +
        '<div class="heat"><div class="heat-bar"><div style="width: ' + Math.max(8, Math.min(100, t.heat)) + '%;"></div></div></div>' +
        '<div class="role"><span class="badge warm">' + (t.amount || 0) + '亿</span></div>' +
        '<div>' + t.limit_up_count + '只</div>' +
        '<div><span class="badge ' + badgeClass(t.status) + '">' + t.status + '</span></div>' +
      '</div>';
    }).join('');
    list.innerHTML = header + rows;
  }

  function pickCard(pick, intradayMode) {
    var hot = pick.score >= 75 ? ' hot' : '';
    var grade = intradayMode ? '<div class="pick-score" style="color: var(--accent);">' + (pick.grade || 'A') + '</div>' : '<div class="pick-score">' + pick.score + '<small>SCORE</small></div>';
    var positionCell = intradayMode
      ? '<div class="cell"><div class="l">仓位</div><div class="v up">' + (pick.position || 0) + '%</div></div>'
      : '<div class="cell"><div class="l">目标</div><div class="v up">' + pick.target_price + '</div></div>';
    var subtitle = intradayMode
      ? pick.code + ' · ' + pick.change_pct + '% · 首封 ' + pick.first_seal_time
      : pick.code + ' · ' + pick.market;
    return '<div class="pick-card' + hot + '"' + (intradayMode ? ' style="background: rgba(0,0,0,0.25);"' : '') + '>' +
      '<div class="pick-head"><div><div class="name">' + pick.name + '</div><div class="code">' + subtitle + '</div></div>' + grade + '</div>' +
      '<div class="pick-tags"><span class="badge ' + badgeClass(pick.score) + '">' + pick.industry + '</span><span class="badge role-leader">' + pick.role + '</span></div>' +
      '<div class="pick-meta">' +
        '<div class="cell"><div class="l">买入价</div><div class="v">' + pick.buy_price + '</div></div>' +
        '<div class="cell"><div class="l">止损</div><div class="v down">' + pick.stop_price + '</div></div>' +
        positionCell +
      '</div>' +
      '<div class="pick-reason"><strong>AkShare行情：</strong>' + (intradayMode ? pick.trigger : pick.reason) + '</div>' +
    '</div>';
  }

  function renderPicks() {
    var pre = $('#premarket-picks');
    if (pre && premarket.length) {
      pre.innerHTML = premarket.map(function (p) { return pickCard(p, false); }).join('');
    }
    var intra = $('#intraday-picks');
    if (intra && intraday.length) {
      intra.innerHTML = intraday.map(function (p) { return pickCard(p, true); }).join('');
    }
    var alloc = document.querySelectorAll('.alloc-summary .cell .v');
    if (alloc[0]) alloc[0].textContent = sentiment.suggested_position + '%';
    if (alloc[1]) alloc[1].textContent = sentiment.cash_buffer + '%';
    if (alloc[2]) alloc[2].textContent = sentiment.flex_position + '%';
    if (alloc[3]) alloc[3].textContent = Math.max.apply(null, intraday.map(function (p) { return p.position || 0; }).concat([0])) + '%';
    var positionText = $('.spotlight .alloc-summary + p');
    if (positionText) {
      positionText.innerHTML = '情绪 ' + sentiment.temperature + '℃、阶段为 ' + sentiment.stage + '：<strong style="color: var(--accent);">建议总仓位 ' + sentiment.suggested_position + '%</strong>，机动仓位 ' + sentiment.flex_position + '%，现金缓冲 ' + sentiment.cash_buffer + '%。若炸板率继续升高，优先降低追板仓位。';
    }
  }

  function renderTracking() {
    var body = $('#tracking-body');
    if (!body || !tracking.length) return;
    body.innerHTML = tracking.map(function (x) {
      var pnlColor = x.pnl >= 0 ? 'var(--accent)' : 'var(--green)';
      return '<tr>' +
        '<td class="name-cell"><strong>' + x.name + '</strong><span>' + x.code + ' · ' + x.position + '%仓位</span></td>' +
        '<td>' + x.cost + '</td>' +
        '<td style="color: ' + pnlColor + ';">' + x.latest + '</td>' +
        '<td style="color: ' + pnlColor + ';">' + (x.pnl >= 0 ? '+' : '') + x.pnl + '%</td>' +
        '<td><span class="badge warm">' + x.industry_status + '</span></td>' +
        '<td>' + x.key_signal + '</td>' +
        '<td><span class="signal ' + x.signal_class + '">' + x.signal + '</span></td>' +
        '<td>' + x.logic + '</td>' +
      '</tr>';
    }).join('');
  }

  function renderStaticData() {
    renderHeader();
    renderKpis();
    renderStage();
    renderThemes();
    renderPicks();
    renderTracking();
  }

  renderStaticData();

  // ---------- Chart 1: 情绪温度计 ----------
  var gaugeEl = document.getElementById('chart-gauge');
  if (gaugeEl) {
    var gauge = echarts.init(gaugeEl, null, { renderer: 'svg' });
    gauge.setOption({
      animation: false,
      tooltip: { show: false },
      series: [{
        type: 'gauge',
        center: ['50%', '70%'],
        radius: '105%',
        startAngle: 200,
        endAngle: -20,
        min: 0,
        max: 100,
        splitNumber: 5,
        progress: { show: true, width: 16, itemStyle: { color: accent } },
        pointer: { show: true, length: '60%', width: 4, itemStyle: { color: accent } },
        axisLine: {
          lineStyle: {
            width: 16,
            color: [[0.2, blue], [0.4, accent2 + 'AA'], [0.7, accent2], [0.9, accent], [1, accent + 'CC']]
          }
        },
        axisTick: { distance: -22, length: 4, lineStyle: { color: muted } },
        splitLine: { distance: -24, length: 8, lineStyle: { color: muted, width: 2 } },
        axisLabel: { color: muted, fontSize: 10, distance: -2 },
        title: { show: false },
        detail: {
          valueAnimation: false,
          fontSize: 30,
          fontWeight: 700,
          color: accent,
          offsetCenter: [0, '15%'],
          formatter: '{value}℃'
        },
        data: [{ value: sentiment.temperature }]
      }]
    });
    window.addEventListener('resize', function () { gauge.resize(); });
  }

  // ---------- Chart 2: 近10日情绪轨迹 ----------
  var trendEl = document.getElementById('chart-emotion-trend');
  if (trendEl) {
    var trend = echarts.init(trendEl, null, { renderer: 'svg' });
    trend.setOption({
      animation: false,
      tooltip: {
        trigger: 'axis',
        appendToBody: true,
        backgroundColor: bg2,
        borderColor: rule,
        textStyle: { color: ink, fontSize: 12 }
      },
      legend: {
        data: ['涨停家数', '最高连板', '情绪温度'],
        textStyle: { color: muted, fontSize: 11 },
        top: 0,
        right: 0,
        itemWidth: 14,
        itemHeight: 8
      },
      grid: { left: 36, right: 40, top: 36, bottom: 28 },
      xAxis: {
        type: 'category',
        data: trendData.dates,
        axisLine: { lineStyle: { color: rule } },
        axisLabel: { color: muted, fontSize: 10 },
        axisTick: { show: false }
      },
      yAxis: [
        {
          type: 'value',
          axisLine: { show: false },
          axisLabel: { color: muted, fontSize: 10 },
          splitLine: { lineStyle: { color: rule, type: 'dashed' } }
        },
        {
          type: 'value',
          axisLine: { show: false },
          axisLabel: { color: muted, fontSize: 10 },
          splitLine: { show: false },
          max: Math.max(8, Math.max.apply(null, trendData.heights || [0]) + 1)
        }
      ],
      series: [
        {
          name: '涨停家数',
          type: 'bar',
          data: trendData.limit_ups,
          itemStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [{ offset: 0, color: accent }, { offset: 1, color: accent + '33' }]
            }
          },
          barWidth: 12
        },
        {
          name: '最高连板',
          type: 'line',
          yAxisIndex: 1,
          data: trendData.heights,
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { color: accent2, width: 2 },
          itemStyle: { color: accent2 }
        },
        {
          name: '情绪温度',
          type: 'line',
          data: trendData.temperatures,
          smooth: true,
          symbol: 'none',
          lineStyle: { color: blue, width: 2, type: 'dashed' },
          itemStyle: { color: blue }
        }
      ]
    });
    window.addEventListener('resize', function () { trend.resize(); });
  }

  // ---------- Chart 3: 题材热度 TOP 8 ----------
  var themeEl = document.getElementById('chart-theme');
  if (themeEl) {
    var theme = echarts.init(themeEl, null, { renderer: 'svg' });
    var themeNames = (themes.length ? themes : [
      { name: '具身智能机器人', heat: 96, amount: 18.5 },
      { name: '固态电池', heat: 88, amount: 14.2 },
      { name: 'AI算力光模块', heat: 80, amount: 12.6 }
    ]).map(function (x) { return x.name; });
    var heats = (themes.length ? themes : [
      { heat: 96 }, { heat: 88 }, { heat: 80 }
    ]).map(function (x) { return x.heat; });
    var amounts = (themes.length ? themes : [
      { amount: 18.5 }, { amount: 14.2 }, { amount: 12.6 }
    ]).map(function (x) { return x.amount || 0; });

    theme.setOption({
      animation: false,
      tooltip: {
        trigger: 'axis',
        appendToBody: true,
        axisPointer: { type: 'shadow' },
        backgroundColor: bg2,
        borderColor: rule,
        textStyle: { color: ink, fontSize: 12 }
      },
      legend: {
        data: ['热度指数', '成交额'],
        textStyle: { color: muted, fontSize: 11 },
        top: 0,
        right: 0,
        itemWidth: 14,
        itemHeight: 8
      },
      grid: { left: 100, right: 50, top: 36, bottom: 20 },
      xAxis: [{
        type: 'value',
        name: '热度',
        nameTextStyle: { color: muted, fontSize: 10 },
        axisLine: { show: false },
        axisLabel: { color: muted, fontSize: 10 },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } },
        max: 100
      }],
      yAxis: {
        type: 'category',
        data: themeNames.slice().reverse(),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: ink, fontSize: 11 }
      },
      series: [
        {
          name: '热度指数',
          type: 'bar',
          data: heats.slice().reverse(),
          itemStyle: {
            color: function (p) {
              var v = p.value;
              if (v >= 75) return accent;
              if (v >= 50) return accent2;
              return blue;
            },
            borderRadius: [0, 4, 4, 0]
          },
          barWidth: 14,
          label: { show: true, position: 'right', color: ink, fontSize: 11, fontFamily: 'JetBrainsMono' }
        },
        {
          name: '成交额',
          type: 'scatter',
          data: amounts.slice().reverse().map(function (v, i) { return [Math.min(100, v / Math.max.apply(null, amounts.concat([1])) * 100), i]; }),
          symbolSize: function (val) { return Math.max(8, val[0] * 0.55); },
          itemStyle: { color: accent2 + '88', borderColor: accent2, borderWidth: 1 }
        }
      ]
    });
    window.addEventListener('resize', function () { theme.resize(); });
  }
})();
