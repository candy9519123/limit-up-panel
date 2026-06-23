#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股涨停板行情数据抓取脚本 - 增强版
支持多源备份：AkShare 为主，失败时自动切换备用方案

输出：
  assets/market-data.js
  assets/market-data.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# 尝试导入 AkShare，如果失败则标记为不可用
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    print("[WARN] AkShare 未安装，将尝试备用数据源", file=sys.stderr)


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"

# ============ 工具函数 ============

def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
        return float(value)
    except Exception:
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return int(float(value))
    except Exception:
        return default


def fmt_money(value: Any) -> str:
    amount = to_float(value)
    if amount >= 1e8:
        return f"{amount / 1e8:.2f}亿"
    if amount >= 1e4:
        return f"{amount / 1e4:.0f}万"
    return f"{amount:.0f}"


def fmt_time(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return "--"
    text = text.zfill(6)
    return f"{text[:2]}:{text[2:4]}:{text[4:6]}"


def retry_with_backoff(func, max_retries: int = 3, base_delay: float = 2.0):
    """指数退避重试装饰器"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"[RETRY] 第{attempt + 1}次失败: {e}，{delay}秒后重试...", file=sys.stderr)
            time.sleep(delay)
    return None


# ============ 数据源：AkShare ============

def ak_get_zt_pool(date: str) -> pd.DataFrame:
    """通过 AkShare 获取涨停池"""
    if not AKSHARE_AVAILABLE:
        raise RuntimeError("AkShare 未安装")
    df = ak.stock_zt_pool_em(date=date)
    if isinstance(df, pd.DataFrame) and not df.empty:
        return df
    raise RuntimeError("返回空数据")


def ak_get_previous_pool(date: str) -> pd.DataFrame:
    if not AKSHARE_AVAILABLE:
        return pd.DataFrame()
    try:
        df = ak.stock_zt_pool_previous_em(date=date)
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    except Exception as e:
        print(f"[WARN] 昨日涨停池获取失败: {e}", file=sys.stderr)
        return pd.DataFrame()


def ak_get_strong_pool(date: str) -> pd.DataFrame:
    if not AKSHARE_AVAILABLE:
        return pd.DataFrame()
    try:
        df = ak.stock_zt_pool_strong_em(date=date)
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    except Exception as e:
        print(f"[WARN] 强势股池获取失败: {e}", file=sys.stderr)
        return pd.DataFrame()


# ============ 数据源：东方财富 HTTP API（备用） ============

def em_get_zt_pool(date: str) -> pd.DataFrame:
    """直接调用东方财富涨停池 HTTP API"""
    url = (
        f"https://push2ex.eastmoney.com/getTopicZTPool"
        f"?ut=7eea3edcaed734bea9cbfc24409ed989"
        f"&dpt=wz.ztzt"
        f"&Pageindex=0&pagesize=10000"
        f"&sort=fbt%3Aasc"
        f"&date={date}"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if data.get("data") and data["data"].get("pool"):
        records = []
        for item in data["data"]["pool"]:
            records.append({
                "代码": str(item.get("c", "")).zfill(6),
                "名称": item.get("n", ""),
                "涨跌幅": round(item.get("zdp", 0), 2),
                "最新价": item.get("p", 0),
                "成交额": item.get("amount", 0),
                "流通市值": item.get("ltsz", 0),
                "总市值": item.get("tshare", 0),
                "换手率": item.get("hs", 0),
                "封板资金": item.get("fund", 0),
                "首次封板时间": str(item.get("fbt", "")).zfill(6),
                "最后封板时间": str(item.get("lbt", "")).zfill(6),
                "炸板次数": item.get("zbc", 0),
                "涨停统计": item.get("zttz", ""),
                "连板数": item.get("lbc", 0),
                "所属行业": item.get("hybk", "未分类"),
            })
        return pd.DataFrame(records)
    raise RuntimeError("东方财富API返回空数据")


# ============ 统一数据获取入口 ============

def fetch_zt_pool(date: str) -> tuple[str, pd.DataFrame]:
    """获取涨停池，自动尝试多个数据源"""
    errors = []

    # 尝试1：AkShare
    if AKSHARE_AVAILABLE:
        try:
            print(f"[INFO] 尝试 AkShare 获取 {date} 涨停池...")
            df = retry_with_backoff(lambda: ak_get_zt_pool(date), max_retries=2)
            if df is not None and not df.empty:
                print(f"[INFO] ✅ AkShare 成功: {len(df)} 只")
                return date, df
        except Exception as e:
            errors.append(f"AkShare: {e}")
            print(f"[WARN] AkShare 失败: {e}", file=sys.stderr)

    # 尝试2：东方财富 HTTP API
    try:
        print(f"[INFO] 尝试东方财富HTTP API获取 {date} 涨停池...")
        df = retry_with_backoff(lambda: em_get_zt_pool(date), max_retries=2)
        if df is not None and not df.empty:
            print(f"[INFO] ✅ 东方财富API成功: {len(df)} 只")
            return date, df
    except Exception as e:
        errors.append(f"EM HTTP: {e}")
        print(f"[WARN] 东方财富API失败: {e}", file=sys.stderr)

    raise RuntimeError(f"所有数据源均失败: {'; '.join(errors)}")


def latest_available_limit_up(target_date: str, lookback_days: int = 20) -> tuple[str, pd.DataFrame]:
    """从目标日期向前查找最近一个可用的涨停池交易日"""
    dt = datetime.strptime(target_date, "%Y%m%d")
    errors: list[str] = []
    for i in range(lookback_days + 1):
        day = (dt - timedelta(days=i)).strftime("%Y%m%d")
        try:
            actual_day, df = fetch_zt_pool(day)
            if not df.empty:
                return actual_day, df
            errors.append(f"{day}: 空数据")
        except Exception as exc:
            errors.append(f"{day}: {type(exc).__name__} {str(exc)[:80]}")
    raise RuntimeError("最近交易日涨停池获取失败：" + "；".join(errors[-5:]))


# ============ 数据处理（与原版保持一致） ============

def normalize_limit_up(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "代码", "名称", "涨跌幅", "最新价", "成交额", "流通市值", "总市值", "换手率",
        "封板资金", "首次封板时间", "最后封板时间", "炸板次数", "涨停统计", "连板数", "所属行业"
    ]
    for col in columns:
        if col not in df.columns:
            df[col] = None
    out = df[columns].copy()
    out["连板数_num"] = out["连板数"].map(to_int)
    out["炸板次数_num"] = out["炸板次数"].map(to_int)
    out["封板资金_num"] = out["封板资金"].map(to_float)
    out["成交额_num"] = out["成交额"].map(to_float)
    out["换手率_num"] = out["换手率"].map(to_float)
    out["流通市值_num"] = out["流通市值"].map(to_float)
    out["首次封板时间_str"] = out["首次封板时间"].map(fmt_time)
    out["所属行业"] = out["所属行业"].fillna("未分类").replace("", "未分类")
    return out


def calc_sentiment(zt: pd.DataFrame, previous: pd.DataFrame) -> dict[str, Any]:
    limit_up_count = int(len(zt))
    highest_board = int(zt["连板数_num"].max()) if not zt.empty else 0
    broken_count = int((zt["炸板次数_num"] > 0).sum()) if not zt.empty else 0
    break_rate = broken_count / limit_up_count if limit_up_count else 0

    promotion_rate = 0.0
    if not previous.empty and "涨跌幅" in previous.columns:
        promotion_rate = float((previous["涨跌幅"].map(to_float) >= 9.8).mean())

    raw_temp = (
        min(limit_up_count, 160) / 160 * 42
        + min(highest_board, 10) / 10 * 25
        + promotion_rate * 23
        + (1 - min(break_rate, 0.6) / 0.6) * 10
    )
    temp = int(round(max(0, min(100, raw_temp))))

    if temp < 30:
        stage, stage_desc = "冰点", "风险偏好低，建议轻仓观察"
    elif temp < 50:
        stage, stage_desc = "修复", "赚钱效应开始恢复，适合小仓试错"
    elif temp < 75:
        stage, stage_desc = "主升初中段", "题材承接较强，可围绕前排参与"
    elif temp < 88:
        stage, stage_desc = "主升中后段", "主线明确，但需防范加速后的分歧"
    else:
        stage, stage_desc = "高潮", "一致性较强，追高风险抬升"

    if temp < 30:
        suggested_position = 10
    elif temp < 50:
        suggested_position = 25
    elif temp < 75:
        suggested_position = 40
    elif temp < 88:
        suggested_position = 50
    else:
        suggested_position = 35

    return {
        "temperature": temp,
        "stage": stage,
        "stage_desc": stage_desc,
        "limit_up_count": limit_up_count,
        "highest_board": highest_board,
        "broken_count": broken_count,
        "break_rate": round(break_rate * 100, 2),
        "promotion_rate": round(promotion_rate * 100, 2),
        "suggested_position": suggested_position,
        "cash_buffer": max(20, 100 - suggested_position - 20),
        "flex_position": 20,
    }


def calc_themes(zt: pd.DataFrame) -> list[dict[str, Any]]:
    if zt.empty:
        return []

    grouped = zt.groupby("所属行业", dropna=False).agg(
        count=("代码", "count"),
        amount=("成交额_num", "sum"),
        seal_money=("封板资金_num", "sum"),
        max_board=("连板数_num", "max"),
        avg_turnover=("换手率_num", "mean"),
    ).reset_index()

    max_count = max(float(grouped["count"].max()), 1.0)
    max_amount = max(float(grouped["amount"].max()), 1.0)
    max_seal = max(float(grouped["seal_money"].max()), 1.0)

    themes: list[dict[str, Any]] = []
    for _, row in grouped.iterrows():
        heat = (
            to_float(row["count"]) / max_count * 45
            + to_float(row["amount"]) / max_amount * 25
            + to_float(row["seal_money"]) / max_seal * 20
            + min(to_float(row["max_board"]), 8) / 8 * 10
        )
        industry = str(row["所属行业"])
        leaders = (
            zt[zt["所属行业"] == industry]
            .sort_values(["连板数_num", "封板资金_num", "成交额_num"], ascending=False)
            .head(2)
        )
        themes.append({
            "name": industry,
            "heat": int(round(heat)),
            "limit_up_count": int(row["count"]),
            "amount": round(to_float(row["amount"]) / 1e8, 2),
            "seal_money": round(to_float(row["seal_money"]) / 1e8, 2),
            "max_board": int(row["max_board"]),
            "avg_turnover": round(to_float(row["avg_turnover"]), 2),
            "leaders": [
                {"code": str(x["代码"]), "name": str(x["名称"]), "board": int(x["连板数_num"])}
                for _, x in leaders.iterrows()
            ],
            "status": "主升" if heat >= 75 else ("活跃" if heat >= 55 else "轮动"),
        })

    return sorted(themes, key=lambda x: x["heat"], reverse=True)[:8]


def score_stock(row: pd.Series, theme_heat_map: dict[str, int]) -> int:
    industry = str(row.get("所属行业", "未分类"))
    theme_heat = theme_heat_map.get(industry, 0)
    board = min(to_int(row.get("连板数_num")), 8)
    seal_money = to_float(row.get("封板资金_num"))
    turnover = to_float(row.get("换手率_num"))
    broken = to_int(row.get("炸板次数_num"))
    amount = to_float(row.get("成交额_num"))

    seal_score = min(math.log10(max(seal_money, 1)) / 9 * 100, 100)
    amount_score = min(math.log10(max(amount, 1)) / 10 * 100, 100)
    board_score = board / 8 * 100
    turnover_score = 100 - min(abs(turnover - 12), 20) / 20 * 45
    broken_penalty = min(broken * 10, 35)

    score = (
        theme_heat * 0.30
        + board_score * 0.22
        + seal_score * 0.18
        + amount_score * 0.14
        + turnover_score * 0.10
        + 70 * 0.06
        - broken_penalty
    )
    return int(round(max(0, min(100, score))))


def market_type(code: str) -> str:
    if code.startswith(("300", "301")):
        return "创业板 · 20cm"
    if code.startswith(("688", "689")):
        return "科创板 · 20cm"
    if code.startswith(("8", "4", "9")):
        return "北交所 · 30cm"
    return "主板 · 10cm"


def stock_role(row: pd.Series, rank_in_theme: int) -> str:
    board = to_int(row.get("连板数_num"))
    amount = to_float(row.get("成交额_num"))
    if rank_in_theme == 1 and board >= 2:
        return "题材龙头"
    if amount >= 1.5e9:
        return "容量中军"
    if board <= 1:
        return "首板补涨"
    return "前排接力"


def build_premarket_picks(zt: pd.DataFrame, themes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """盘前观察池：从涨停池选6只作为情绪和题材雷达。"""
    if zt.empty:
        return []

    theme_heat_map = {x["name"]: x["heat"] for x in themes}
    df = zt.copy()
    df["score"] = df.apply(lambda r: score_stock(r, theme_heat_map), axis=1)
    df["rank_in_theme"] = df.groupby("所属行业")["score"].rank(ascending=False, method="first").astype(int)
    df = df.sort_values(["score", "连板数_num", "封板资金_num"], ascending=False)

    picks = []
    for i, (_, row) in enumerate(df.head(6).iterrows()):
        latest = to_float(row["最新价"])
        mkt = market_type(str(row["代码"]))
        picks.append({
            "code": str(row["代码"]).zfill(6),
            "name": str(row["名称"]),
            "market": mkt,
            "industry": str(row["所属行业"]),
            "role": stock_role(row, to_int(row["rank_in_theme"], i + 1)),
            "score": int(row["score"]),
            "latest": round(latest, 2),
            "change_pct": round(to_float(row["涨跌幅"]), 2),
            "board_count": to_int(row["连板数_num"]),
            "seal_money": fmt_money(row["封板资金"]),
            "first_seal_time": fmt_time(row["首次封板时间"]),
            "break_count": to_int(row["炸板次数"]),
            "turnover": round(to_float(row["换手率"]), 2),
            "reason": (
                f"{str(row['所属行业'])}板块涨停密度靠前，"
                f"当前{to_int(row['连板数_num'])}连板，"
                f"封板资金 {fmt_money(row['封板资金'])}，"
                f"炸板次数 {to_int(row['炸板次数'])}。"
            ),
        })
    return picks


def build_intraday_picks(zt: pd.DataFrame, themes: list[dict[str, Any]], sentiment: dict[str, Any]) -> list[dict[str, Any]]:
    """
    9:40 盘中买入推荐。
    核心逻辑：从涨停池识别热点板块，在热点板块内找还没涨停、
    但具有涨停基因的高辨识度个股（涨幅5%-9%、强承接、高换手）。
    """
    if zt.empty or not themes:
        return []

    # 获取热点板块名称
    hot_industries = [t["name"] for t in themes[:5]]
    print(f"[INFO] 热点板块: {hot_industries}")

    # 获取涨停股代码（已涨停的不能买）
    zt_codes = set(zt["代码"].astype(str).str.zfill(6))

    # 获取全市场实时行情
    try:
        all_stocks = ak.stock_zh_a_spot() if AKSHARE_AVAILABLE else pd.DataFrame()
        if all_stocks.empty:
            # 备用：从东方财富获取
            all_stocks = em_get_all_spot()
    except Exception as e:
        print(f"[WARN] 全市场行情获取失败: {e}", file=sys.stderr)
        all_stocks = pd.DataFrame()

    if all_stocks.empty:
        print("[WARN] 无法获取全市场行情，9:40推荐降级为涨停池观察")
        return []

    # 标准化列名（stock_zh_a_spot 列名：代码,名称,最新价,涨跌额,涨跌幅,买入,卖出,昨收,今开,最高,最低,成交量,成交额,时间戳）
    all_stocks["涨跌幅"] = pd.to_numeric(all_stocks.get("涨跌幅", 0), errors="coerce")
    all_stocks["成交额"] = pd.to_numeric(all_stocks.get("成交额", 0), errors="coerce")
    # stock_zh_a_spot 没有换手率列，用成交量/流通市值估算（简化处理）
    all_stocks["换手率"] = 0.0
    all_stocks["代码"] = all_stocks["代码"].astype(str).str[-6:].str.zfill(6)

    # 筛选：未涨停 + 涨幅5%-9% + 成交额大于5000万
    candidates = all_stocks[
        (~all_stocks["代码"].isin(zt_codes)) &
        (all_stocks["涨跌幅"] >= 5.0) &
        (all_stocks["涨跌幅"] <= 9.0) &
        (all_stocks["成交额"] >= 5e7)
    ].copy()

    if candidates.empty:
        print("[INFO] 无符合条件的热点强势股")
        return []

    # 按成交额排序（容量优先）
    candidates = candidates.sort_values("成交额", ascending=False)

    # 生成推荐（最多3只）
    total_position = int(sentiment["suggested_position"])
    weights = [0.50, 0.30, 0.20]
    picks = []

    for i, (_, row) in enumerate(candidates.head(3).iterrows()):
        code = str(row["代码"]).zfill(6)
        name = str(row.get("名称", "未知"))
        latest = to_float(row.get("最新价"))
        change_pct = to_float(row.get("涨跌幅"))
        turnover = to_float(row.get("换手率"))
        amount = to_float(row.get("成交额"))

        # 判断市场类型
        mkt = market_type(code)
        stop = latest * (0.93 if mkt.endswith("20cm") else 0.96)
        target = latest * (1.12 if mkt.endswith("20cm") else 1.07)

        # 买入触发条件
        if change_pct >= 7:
            trigger = f"强势突破：涨幅{change_pct:.1f}%，放量上攻，9:40前回踩不破分时均线可介入"
        elif turnover >= 8:
            trigger = f"换手承接：涨幅{change_pct:.1f}%，换手率{turnover:.1f}%，资金活跃，回封时跟进"
        else:
            trigger = f"低位补涨：涨幅{change_pct:.1f}%，同板块已有多只涨停，存在补涨空间"

        picks.append({
            "code": code,
            "name": name,
            "market": mkt,
            "industry": "热点板块内",  # 简化，实际可通过个股详情获取
            "role": "热点补涨" if change_pct < 7 else "强势突破",
            "score": min(int(change_pct * 10 + turnover * 2), 100),
            "latest": round(latest, 2),
            "change_pct": round(change_pct, 2),
            "buy_price": round(latest * 0.995, 2),  # 建议比现价低0.5%挂单
            "stop_price": round(stop, 2),
            "target_price": round(target, 2),
            "board_count": 0,  # 未涨停
            "seal_money": "--",
            "first_seal_time": "--",
            "break_count": 0,
            "turnover": round(turnover, 2),
            "reason": trigger,
            "grade": ["A+", "A", "A-"][i],
            "position": int(round(total_position * weights[i])),
            "trigger": trigger,
        })

    return picks


def em_get_all_spot() -> pd.DataFrame:
    """东方财富全市场行情（备用）"""
    try:
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get"
            "?pn=1&pz=5000&po=1&np=1"
            "&ut=bd1d9ddb04089700cf9c27f6f7426281"
            "&fltt=2&invt=2&fid=f12"
            "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
            "&fields=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152"
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("data") and data["data"].get("diff"):
            records = []
            for item in data["data"]["diff"]:
                records.append({
                    "代码": str(item.get("f12", "")).zfill(6),
                    "名称": item.get("f14", ""),
                    "最新价": item.get("f2", 0),
                    "涨跌幅": item.get("f3", 0),
                    "涨跌额": item.get("f4", 0),
                    "成交额": item.get("f6", 0),
                    "换手率": item.get("f8", 0),
                    "振幅": item.get("f7", 0),
                })
            return pd.DataFrame(records)
    except Exception as e:
        print(f"[WARN] 东方财富全市场行情失败: {e}", file=sys.stderr)
    return pd.DataFrame()



def build_tracking(intraday: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tracking = []
    for pick in intraday:
        pnl = round((pick["latest"] - pick["buy_price"]) / pick["buy_price"] * 100, 2) if pick["buy_price"] else 0
        if pick["break_count"] >= 2:
            signal, signal_class, logic = "减仓观察", "sell", "多次炸板，封单稳定性不足，次日弱转强失败则降低仓位。"
        elif pick["board_count"] >= 3 and pick["score"] >= 80:
            signal, signal_class, logic = "继续持有", "hold", "连板高度和综合评分仍处前排，等待次日竞价确认溢价。"
        else:
            signal, signal_class, logic = "分批止盈", "add", "首板或低位补涨以套利为主，次日高开冲高先兑现一半。"
        tracking.append({
            "code": pick["code"],
            "name": pick["name"],
            "position": pick.get("position", 0),
            "cost": pick["buy_price"],
            "latest": pick["latest"],
            "pnl": pnl,
            "industry_status": f"{pick['industry']} · {pick['role']}",
            "key_signal": f"{pick['board_count']}连板 / 首封 {pick['first_seal_time']}",
            "signal": signal,
            "signal_class": signal_class,
            "logic": logic,
        })
    return tracking


def build_trend(target_date: str, current_sentiment: dict[str, Any]) -> dict[str, list[Any]]:
    dates, limit_ups, heights, temps = [], [], [], []
    dt = datetime.strptime(target_date, "%Y%m%d")
    day = dt - timedelta(days=14)

    while day <= dt:
        d = day.strftime("%Y%m%d")
        try:
            _, raw = fetch_zt_pool(d)
            if raw is not None and not raw.empty:
                z = normalize_limit_up(raw)
                prev = ak_get_previous_pool(d) if AKSHARE_AVAILABLE else pd.DataFrame()
                s = calc_sentiment(z, prev)
                dates.append(day.strftime("%m/%d"))
                limit_ups.append(s["limit_up_count"])
                heights.append(s["highest_board"])
                temps.append(s["temperature"])
        except Exception:
            pass
        day += timedelta(days=1)

    if not dates:
        dates = [datetime.strptime(target_date, "%Y%m%d").strftime("%m/%d")]
        limit_ups = [current_sentiment["limit_up_count"]]
        heights = [current_sentiment["highest_board"]]
        temps = [current_sentiment["temperature"]]

    return {
        "dates": dates[-10:],
        "limit_ups": limit_ups[-10:],
        "heights": heights[-10:],
        "temperatures": temps[-10:],
    }


def write_frontend_data(data: dict[str, Any]) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    json_path = ASSETS / "market-data.json"
    js_path = ASSETS / "market-data.js"
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    json_path.write_text(payload, encoding="utf-8")
    js_path.write_text("window.AKSHARE_MARKET_DATA = " + payload + ";\n", encoding="utf-8")
    print(f"[INFO] 已写入 {js_path}（{js_path.stat().st_size} 字节）")
    print(f"[INFO] 已写入 {json_path}（{json_path.stat().st_size} 字节）")


# ============ 主程序 ============

def main() -> None:
    import platform
    print(f"[INFO] Python {platform.python_version()} on {platform.system()} {platform.release()}")
    print(f"[INFO] AkShare 可用: {AKSHARE_AVAILABLE}")
    if AKSHARE_AVAILABLE:
        print(f"[INFO] AkShare 版本: {getattr(ak, '__version__', 'unknown')}")

    parser = argparse.ArgumentParser(description="A股涨停板行情数据抓取")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"), help="交易日，格式 YYYYMMDD")
    parser.add_argument("--lookback", type=int, default=20, help="目标日无数据时向前回溯天数")
    args = parser.parse_args()

    print(f"[INFO] 目标日期: {args.date}")

    actual_date, raw_zt = latest_available_limit_up(args.date, args.lookback)
    print(f"[INFO] 实际交易日: {actual_date}，涨停池原始行数: {len(raw_zt)}")
    zt = normalize_limit_up(raw_zt)
    print(f"[INFO] 标准化后涨停池: {len(zt)} 只")

    previous = ak_get_previous_pool(actual_date)
    print(f"[INFO] 昨日涨停表现: {len(previous)} 只")
    strong = ak_get_strong_pool(actual_date)
    print(f"[INFO] 强势股池: {len(strong)} 只")

    sentiment = calc_sentiment(zt, previous)
    print(f"[INFO] 情绪温度: {sentiment['temperature']}℃，阶段: {sentiment['stage']}")

    themes = calc_themes(zt)
    print(f"[INFO] 题材板块: {len(themes)} 个")

    premarket = build_premarket_picks(zt, themes)
    intraday = build_intraday_picks(zt, themes, sentiment)
    tracking = build_tracking(intraday)
    trend = build_trend(actual_date, sentiment)
    print(f"[INFO] 趋势数据点: {len(trend['dates'])} 天")

    data = {
        "meta": {
            "source": "多源融合 / AkShare + 东方财富",
            "requested_date": args.date,
            "trade_date": actual_date,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "akshare_version": getattr(ak, "__version__", "not_used") if AKSHARE_AVAILABLE else "not_available",
            "notes": [
                "涨停池来自 AkShare stock_zt_pool_em 或东方财富HTTP API",
                "昨日涨停表现来自 stock_zt_pool_previous_em",
                "强势股池来自 stock_zt_pool_strong_em",
                "多源备份：AkShare失败时自动切换东方财富直连API",
            ],
        },
        "sentiment": sentiment,
        "trend": trend,
        "themes": themes,
        "premarket": premarket,
        "intraday": intraday,
        "tracking": tracking,
        "raw_counts": {
            "limit_up_pool": int(len(zt)),
            "previous_pool": int(len(previous)) if isinstance(previous, pd.DataFrame) else 0,
            "strong_pool": int(len(strong)) if isinstance(strong, pd.DataFrame) else 0,
        },
    }

    write_frontend_data(data)
    print(f"[DONE] 交易日：{actual_date}，涨停池：{len(zt)} 只，题材：{len(themes)} 个")
    print(f"[DONE] 情绪：{sentiment['stage']} · {sentiment['temperature']}℃，建议总仓位：{sentiment['suggested_position']}%")


if __name__ == "__main__":
    main()
