(function () {
  var PRICE = 299;
  var MEMBER_KEY = 'limit_up_panel_member';
  var USER_KEY = 'limit_up_panel_user';
  var ACTIVATION_CODE_HASHES = [
    // 默认口令：ZT940-299（已停用，保留兼容）
    'f2854638f5a49865976aac6968ae8ae5f0d27c589e02b66595a6e736fd1a5ef7',
    // 2026年6月口令：ZT940-202606
    '8adeb42c2f43fa970e741d4023538c7a53116439babb8eb95f98819adb98f015',
    // 2026年7月口令：ZT940-202607
    'ac56a08ae3989f4d4763e8f24a6d8192a6e4d30ba7dc13968c19c8e24a80bf87',
    // 2026年8月口令：ZT940-202608
    '8210f81f931500463f3dfd3736d681b5a75cad5c402ca5a6feef9588a18948d2',
    // 2026年9月口令：ZT940-202609
    '1ea1ea6d24c0727ad17b9fd1d7272ebaf79ad19827f5584f67072f237ba1fcba'
  ];

  function $(selector) {
    return document.querySelector(selector);
  }

  function readJson(key) {
    try {
      return JSON.parse(localStorage.getItem(key) || 'null');
    } catch (e) {
      return null;
    }
  }

  function writeJson(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function formatDate(timestamp) {
    var d = new Date(timestamp);
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + day;
  }

  function getMember() {
    return readJson(MEMBER_KEY);
  }

  function isPaidMember() {
    var member = getMember();
    return Boolean(member && member.expiresAt && Date.now() < member.expiresAt);
  }

  function getUserName() {
    var user = readJson(USER_KEY);
    return user && user.account ? user.account : '';
  }

  function openModal() {
    var modal = $('#member-modal');
    if (modal) {
      modal.classList.add('active');
      modal.setAttribute('aria-hidden', 'false');
    }
  }

  function closeModal() {
    var modal = $('#member-modal');
    if (modal) {
      modal.classList.remove('active');
      modal.setAttribute('aria-hidden', 'true');
    }
  }

  function loginOnly() {
    var account = ($('#member-phone') && $('#member-phone').value.trim()) || '游客账号';
    writeJson(USER_KEY, {
      account: account,
      loginAt: Date.now()
    });
    updatePaywall();
    closeModal();
  }

  function sha256(text) {
    if (!window.crypto || !window.crypto.subtle) {
      return Promise.reject(new Error('当前浏览器不支持本地口令校验'));
    }
    var encoder = new TextEncoder();
    return window.crypto.subtle.digest('SHA-256', encoder.encode(text)).then(function (buffer) {
      return Array.prototype.map.call(new Uint8Array(buffer), function (x) {
        return x.toString(16).padStart(2, '0');
      }).join('');
    });
  }

  function setButtonLoading(button, loading) {
    if (!button) return;
    button.disabled = loading;
    button.textContent = loading ? '正在校验口令...' : '验证口令并开通';
  }

  function activateMonthlyMember() {
    var account = ($('#member-phone') && $('#member-phone').value.trim()) || '';
    var code = ($('#member-code') && $('#member-code').value.trim()) || '';
    var button = $('#member-pay-demo');

    if (!account) {
      alert('请先填写手机号、账号或付款备注，方便核对到账。');
      return;
    }
    if (!code) {
      alert('请填写支付后获得的开通口令。');
      return;
    }

    setButtonLoading(button, true);
    sha256(code).then(function (hash) {
      if (ACTIVATION_CODE_HASHES.indexOf(hash) === -1) {
        alert('开通口令不正确，请确认已支付并向管理员索取正确口令。');
        return;
      }

      var now = Date.now();
      var expiresAt = now + 30 * 24 * 60 * 60 * 1000;
      writeJson(USER_KEY, {
        account: account,
        loginAt: now
      });
      writeJson(MEMBER_KEY, {
        plan: 'monthly',
        price: PRICE,
        paidAt: now,
        expiresAt: expiresAt,
        paymentProvider: 'alipay_qr_manual',
        paymentRemark: account,
        orderNo: 'ALIPAY-QR-' + now
      });
      updatePaywall();
      closeModal();
      alert('会员已开通，有效期至 ' + formatDate(expiresAt) + '。');
    }).catch(function (error) {
      alert(error.message || '口令校验失败，请换浏览器重试。');
    }).finally(function () {
      setButtonLoading(button, false);
    });
  }

  function logout() {
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(MEMBER_KEY);
    updatePaywall();
  }

  function updatePaywall() {
    var paid = isPaidMember();
    var member = getMember();
    var userName = getUserName();
    var gate = $('#member-gate');
    var picks = $('#intraday-picks');
    var tip = $('#member-only-tip');
    var status = $('#member-status');
    var open = $('#member-open');
    var trackingGate = $('#tracking-gate');
    var trackingContent = $('#tracking-content');
    var trackingTip = $('#member-only-tip-tracking');

    if (gate) gate.classList.toggle('active', !paid);
    if (picks) picks.classList.toggle('locked-preview', !paid);
    if (tip) tip.classList.toggle('active', paid);
    if (trackingGate) trackingGate.classList.toggle('active', !paid);
    if (trackingContent) trackingContent.classList.toggle('locked-preview', !paid);
    if (trackingTip) trackingTip.classList.toggle('active', paid);

    if (status) {
      status.classList.toggle('paid', paid);
      if (paid) {
        status.textContent = '会员已开通 · 到期 ' + formatDate(member.expiresAt);
      } else if (userName) {
        status.textContent = '已登录未付费 · 9:40个股及次日跟踪锁定';
      } else {
        status.textContent = '未登录 · 9:40个股及次日跟踪锁定';
      }
    }

    if (open) {
      open.textContent = paid ? '会员中心 / 退出' : '会员登录 / 开通';
      open.onclick = paid
        ? function () {
            if (confirm('是否退出并清除本机会员演示状态？')) logout();
          }
        : openModal;
    }
  }

  function bindEvents() {
    var close = $('#member-close');
    var modal = $('#member-modal');
    var login = $('#member-login');
    var payDemo = $('#member-pay-demo');
    var gatePay = $('#gate-pay');
    var trackingGatePay = $('#tracking-gate-pay');

    if (close) close.addEventListener('click', closeModal);
    if (modal) {
      modal.addEventListener('click', function (event) {
        if (event.target === modal) closeModal();
      });
    }
    if (login) login.addEventListener('click', loginOnly);
    if (payDemo) payDemo.addEventListener('click', activateMonthlyMember);
    if (gatePay) gatePay.addEventListener('click', openModal);
    if (trackingGatePay) trackingGatePay.addEventListener('click', openModal);

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') closeModal();
    });
  }

  bindEvents();
  updatePaywall();
})();
