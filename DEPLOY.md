# 免费上线方案：GitHub Pages + GitHub Actions

## 推荐方案

当前网页是静态站点，最适合用 **GitHub Pages** 免费托管；每日 9:40 的 AkShare 数据更新用 **GitHub Actions** 免费定时任务完成。

这个方案的优点：

- 网页托管免费。
- 支持自定义域名。
- 支持 HTTPS。
- 不需要服务器。
- GitHub Actions 可以每天 9:40 自动运行 `fetch_akshare_data.py`。
- 更新后的 `assets/market-data.js` 会自动提交，网页刷新即可看到最新数据。

限制：

- GitHub Pages 是静态托管，不能真正安全处理支付。
- 当前 `299 元/月会员` 是前端演示门禁，只能用于产品样机，不能用于真实收费。
- 如果要真实收费，需要接入后端账号、订单、支付回调和服务端鉴权。

## 一、创建 GitHub 仓库

1. 登录 GitHub。
2. 新建仓库，例如：`limit-up-panel`。
3. 建议先设为私有仓库，调试完成后再决定是否公开。

## 二、上传项目文件

把本文件夹里的全部内容上传到仓库根目录，结构应类似：

```text
limit-up-panel/
├── index.html
├── .nojekyll
├── limit-up-panel.html
├── fetch_akshare_data.py
├── PAYMENT_SETUP.md
├── assets/
│   ├── charts.js
│   ├── market-data.js
│   ├── market-data.json
│   └── member-paywall.js
│   └── payment/
│       └── alipay-qr.jpg
├── _shared/
│   ├── fonts/
│   └── js/
└── .github/
    └── workflows/
        └── update-akshare-data.yml
```

如果你熟悉命令行，可以在当前目录执行：

```bash
git init
git add .
git commit -m "上线涨停板智能选股面板"
git branch -M main
git remote add origin https://github.com/你的用户名/limit-up-panel.git
git push -u origin main
```

## 三、开启 GitHub Pages

1. 进入仓库页面。
2. 点击 `Settings`。
3. 左侧点击 `Pages`。
4. `Build and deployment` 选择：
   - Source: `Deploy from a branch`
   - Branch: `main`
   - Folder: `/root`
5. 保存。

几分钟后，GitHub 会给出访问地址：

```text
https://你的用户名.github.io/limit-up-panel/
```

打开后会自动跳转到 `limit-up-panel.html`。

`.nojekyll` 文件必须保留，否则 GitHub Pages 可能不会正确发布 `_shared` 目录里的字体和 ECharts 文件。

## 四、开启 9:40 自动更新

项目已内置：

```text
.github/workflows/update-akshare-data.yml
```

它会在工作日北京时间 9:40 运行：

```yaml
cron: "40 1 * * 1-5"
```

说明：

- GitHub Actions 使用 UTC 时间。
- 北京时间 09:40 等于 UTC 01:40。
- 如果当天接口没有有效数据，脚本会向前回溯最近可用交易日。
- 你也可以在 GitHub 仓库的 `Actions` 页面手动点击 `Run workflow` 测试。

## 五、真实收费的升级路线

当前会员功能已支持“支付宝收款二维码 + 人工核对到账 + 开通口令”的低成本方式，配置方法见：

```text
PAYMENT_SETUP.md
```

但它仍是静态前端门禁，不适合高安全要求的真实收费。原因是：

- 用户可以通过浏览器开发者工具绕过前端隐藏。
- 静态页面无法安全验证订单。
- 静态页面无法校验会员到期。

如果要真的按 `299 元/月` 收费，建议下一步升级为：

```text
Cloudflare Pages
+ Cloudflare Workers
+ D1 数据库
+ 支付宝 / 微信支付 / Stripe 订单回调
+ 服务端接口返回 9:40 个股
```

免费或低成本组合：

| 模块 | 推荐 |
|---|---|
| 前端托管 | Cloudflare Pages 免费版 |
| 后端接口 | Cloudflare Workers 免费额度 |
| 数据库 | Cloudflare D1 免费额度 |
| 定时任务 | Cloudflare Cron Triggers |
| 支付 | 支付宝/微信商户，或 Stripe |

## 六、当前上线版本的定位

当前版本适合：

- 产品展示。
- 会员付费流程演示。
- 私域用户试看。
- 每日 9:40 自动更新行情数据。
- 验证选股面板需求。

当前版本不适合：

- 真实支付收款。
- 强会员防破解。
- 高并发商业服务。
- 对外承诺投资收益。

## 七、风险提示

网页中的个股筛选、仓位、止损和跟踪信号仅用于研究和风控参考，不构成投资建议。涨停板交易风险极高，请勿承诺收益，也不要用该页面直接替代投资决策。
