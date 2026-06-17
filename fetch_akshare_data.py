#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通过 AkShare 拉取 A 股涨停板行情，并生成前端可直接引用的 market-data.js。

使用方式：
  python fetch_akshare_data.py
  python fetch_akshare_data.py --date 20260615

输出：
  assets/market-data.js
  assets/market-data.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"


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


def pct_text(value: Any, digits: int = 2) -> str:
    return f"{to_float(value):.{digits}f}%"


def latest_available_limit_up(target_date: str, lookback_days: int = 20) -> tuple[str, pd.DataFrame]:
    """从目标日期向前查找最近一个可用的涨停池交易日。"""
    dt = datetime.strptime(target_date, "%Y%m%d")
    errors: list[str] = []
    for i in range(lookback_days + 1):
        day = (dt - timedelta(days=i)).strftime("%Y%m%d")
        try:
            df = ak.stock_zt_pool_em(date=day)
            if isinstance(df, pd.DataFrame) and not df.empty:
                return day, df
            errors.append(f"{day}: 空数据")
        except Exception as exc:
            errors.append(f"{day}: {type(exc).__name__} {str(exc)[:80]}")
    raise RuntimeError("最近交易日涨停池获取失败：" + "；".join(errors[-5:]))


def safe_ak_call(func_name: str, **kwargs: Any) -> pd.DataFrame:
    try:
        func = getattr(ak, func_name)
        df = func(**kwargs)
        if isinstance(df, pd.DataFrame):
            return df
    except Exception as exc:
        print(f"[WARN] {func_name} 调用失败：{type(exc).__name__}: {exc}", file=sys.stderr)
    return pd.DataFrame()


def normalize_limit_up(df: pd.DataFrame) -> pd.DataFrame:
    """统一关键字段并补齐缺失列。"""
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
        stage = "冰点"
        stage_desc = "风险偏好低，建议轻仓观察"
    elif temp < 50:
        stage = "修复"
        stage_desc = "赚钱效应开始恢复，适合小仓试错"
    elif temp < 75:
        stage = "主升初中段"
        stage_desc = "题材承接较强，可围绕前排参与"
    elif temp < 88:
        stage = "主升中后段"
        stage_desc = "主线明确，但需防范加速后的分歧"
    else:
        stage = "高潮"
        stage_desc = "一致性较强，追高风险抬升"

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


def build_picks(zt: pd.DataFrame, themes: list[dict[str, Any]], sentiment: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if zt.empty:
        return [], []

    theme_heat_map = {x["name"]: x["heat"] for x in themes}
    df = zt.copy()
    df["score"] = df.apply(lambda r: score_stock(r, theme_heat_map), axis=1)
    df["rank_in_theme"] = df.groupby("所属行业")["score"].rank(ascending=False, method="first").astype(int)
    df = df.sort_values(["score", "连板数_num", "封板资金_num"], ascending=False)

    def make_pick(row: pd.Series, idx: int, intraday: bool = False) -> dict[str, Any]:
        latest = to_float(row["最新价"])
        stop = latest * (0.93 if market_type(str(row["代码"])).endswith("20cm") else 0.96)
        target = latest * (1.12 if market_type(str(row["代码"])).endswith("20cm") else 1.07)
        role = stock_role(row, to_int(row["rank_in_theme"], idx + 1))
        industry = str(row["所属行业"])
        board = to_int(row["连板数_num"])
        reason = (
            f"{industry}板块涨停密度靠前，当前{board}连板，"
            f"首次封板 {fmt_time(row['首次封板时间'])}，封板资金 {fmt_money(row['封板资金'])}，"
            f"炸板次数 {to_int(row['炸板次数'])}。"
        )
        return {
            "code": str(row["代码"]).zfill(6),
            "name": str(row["名称"]),
            "market": market_type(str(row["代码"]).zfill(6)),
            "industry": industry,
            "role": role,
            "score": int(row["score"]),
            "latest": round(latest, 2),
            "change_pct": round(to_float(row["涨跌幅"]), 2),
            "buy_price": round(latest, 2),
            "stop_price": round(stop, 2),
            "target_price": round(target, 2),
            "board_count": board,
            "seal_money": fmt_money(row["封板资金"]),
            "first_seal_time": fmt_time(row["首次封板时间"]),
            "break_count": to_int(row["炸板次数"]),
            "turnover": round(to_float(row["换手率"]), 2),
            "reason": reason,
        }

    premarket = [make_pick(row, i) for i, (_, row) in enumerate(df.head(6).iterrows())]

    total_position = int(sentiment["suggested_position"])
    weights = [0.50, 0.30, 0.20]
    intraday = []
    for i, (_, row) in enumerate(df.head(3).iterrows()):
        pick = make_pick(row, i, intraday=True)
        pick["grade"] = ["A+", "A", "A-"][i]
        pick["position"] = int(round(total_position * weights[i]))
        pick["trigger"] = (
            f"09:40 强度过滤：涨幅 {pick['change_pct']}%，"
            f"封板资金 {pick['seal_money']}，所属行业 {pick['industry']}。"
        )
        intraday.append(pick)

    return premarket, intraday


def build_tracking(intraday: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tracking = []
    for pick in intraday:
        pnl = round((pick["latest"] - pick["buy_price"]) / pick["buy_price"] * 100, 2) if pick["buy_price"] else 0
        if pick["break_count"] >= 2:
            signal = "减仓观察"
            signal_class = "sell"
            logic = "多次炸板，封单稳定性不足，次日弱转强失败则降低仓位。"
        elif pick["board_count"] >= 3 and pick["score"] >= 80:
            signal = "继续持有"
            signal_class = "hold"
            logic = "连板高度和综合评分仍处前排，等待次日竞价确认溢价。"
        else:
            signal = "分批止盈"
            signal_class = "add"
            logic = "首板或低位补涨以套利为主，次日高开冲高先兑现一半。"
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
    """拉取最近 10 个自然日内可用涨停池，构建情绪趋势。"""
    dates: list[str] = []
    limit_ups: list[int] = []
    heights: list[int] = []
    temps: list[int] = []
    dt = datetime.strptime(target_date, "%Y%m%d")
    day = dt - timedelta(days=14)

    while day <= dt:
        d = day.strftime("%Y%m%d")
        try:
            raw = ak.stock_zt_pool_em(date=d)
            if isinstance(raw, pd.DataFrame) and not raw.empty:
                z = normalize_limit_up(raw)
                prev = safe_ak_call("stock_zt_pool_previous_em", date=d)
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
    js_path.write_text(
        "window.AKSHARE_MARKET_DATA = " + payload + ";\n",
        encoding="utf-8",
    )
    print(f"[INFO] 已写入 {js_path}（{js_path.stat().st_size} 字节）")
    print(f"[INFO] 已写入 {json_path}（{json_path.stat().st_size} 字节）")


def main() -> None:
    import platform
    print(f"[INFO] Python {platform.python_version()} on {platform.system()} {platform.release()}")
    print(f"[INFO] AkShare {getattr(ak, '__version__', 'unknown')}")

    parser = argparse.ArgumentParser(description="AkShare 涨停板行情接入脚本")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"), help="交易日，格式 YYYYMMDD")
    parser.add_argument("--lookback", type=int, default=20, help="目标日无数据时向前回溯天数")
    args = parser.parse_args()

    print(f"[INFO] 目标日期: {args.date}")

    actual_date, raw_zt = latest_available_limit_up(args.date, args.lookback)
    print(f"[INFO] 实际交易日: {actual_date}，涨停池原始行数: {len(raw_zt)}")
    zt = normalize_limit_up(raw_zt)
    print(f"[INFO] 标准化后涨停池: {len(zt)} 只")

    previous = safe_ak_call("stock_zt_pool_previous_em", date=actual_date)
    print(f"[INFO] 昨日涨停表现: {len(previous)} 只")
    strong = safe_ak_call("stock_zt_pool_strong_em", date=actual_date)
    print(f"[INFO] 强势股池: {len(strong)} 只")

    sentiment = calc_sentiment(zt, previous)
    print(f"[INFO] 情绪温度: {sentiment['temperature']}℃，阶段: {sentiment['stage']}")

    themes = calc_themes(zt)
    print(f"[INFO] 题材板块: {len(themes)} 个")

    premarket, intraday = build_picks(zt, themes, sentiment)
    tracking = build_tracking(intraday)
    trend = build_trend(actual_date, sentiment)
    print(f"[INFO] 趋势数据点: {len(trend['dates'])} 天")

    data = {
        "meta": {
            "source": "AkShare / 东方财富涨停池",
            "requested_date": args.date,
            "trade_date": actual_date,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "akshare_version": getattr(ak, "__version__", "unknown"),
            "notes": [
                "涨停池来自 stock_zt_pool_em",
                "昨日涨停表现来自 stock_zt_pool_previous_em",
                "强势股池来自 stock_zt_pool_strong_em",
                "概念板块快照若网络代理不可用，将由涨停池所属行业聚合替代",
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
