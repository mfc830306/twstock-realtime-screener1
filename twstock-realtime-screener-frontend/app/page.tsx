"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Stock = {
  market?: string;
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume?: number;
  score?: number;
  recommendation_score?: number;
  signal?: string;
  trend_type?: string;
  reason?: string;
  technical_comment?: string;
  operation_rating?: string;
  operation_bias?: string;
  operation_style?: string;
  strategy_action?: string;
  entry_price?: string;
  target_price?: string;
  stop_loss?: string;
  risk_reward?: string;
  risk_note?: string;
  update_time?: string;
  analysis_source?: string;
  book_selection_score?: number;
  book_market_regime?: string;
  book_selection_comment?: string;
};

type FocusedStock = {
  symbol: string;
  name: string;
  market: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  signal: string;
  trend_type: string;
  operation_rating: string;
  operation_bias: string;
  operation_style: string;
  technical_comment: string;
  analysis: string;
  strategy_action: string;
  entry_price: string;
  target_price: string;
  stop_loss: string;
  risk_reward: string;
  risk_note: string;
  update_time: string;
};

type BackendCategory = {
  key: string;
  label: string;
  count: number;
};

type ApiResponse = {
  success: boolean;
  market_status?: string;
  data_date?: string;
  last_update?: string;
  total?: number;
  all_total?: number;
  twse_total?: number;
  otc_total?: number;
  stocks: Stock[];
  recommendations?: Stock[];
  validation?: StrategyValidation | null;
  categories?: BackendCategory[];
  focused_stock?: FocusedStock | null;
  message?: string;
  error?: string;
  source_summary?: {
    twse_data_date?: string;
    tpex_data_date?: string;
  };
};

type ValidationRecord = {
  dataDate: string;
  lastUpdate: string;
  symbols: string[];
  stockLabels: string[];
  stocks: Array<{
    symbol: string;
    name: string;
    signal: string;
    operationRating: string;
    recommendationScore: number;
    bookSelectionScore: number;
    reason: string;
    entryPrice: string;
    targetPrice: string;
    stopLoss: string;
    riskReward: string;
  }>;
  recommendationCount: number;
  historicalKCount: number;
  strongRatingCount: number;
  validSignalCount: number;
  excludedSignalCount: number;
  averageScore: number;
  averageRiskReward: number;
  signalSummary: string[];
};

type ValidationHealth = {
  score: number;
  label: string;
  summary: string;
  accent: string;
  surface: string;
};

type ValidationHistoryStats = {
  totalRecords: number;
  passCount: number;
  averageRecommendationCount: number;
  averageHistoricalRate: number;
  averageStrongRate: number;
  averageValidRate: number;
  averageExcludedRate: number;
  averageScore: number;
  averageRiskReward: number;
  topSignals: string[];
};

type StrategyValidationSummary = {
  sample_count: number;
  avg_return_1d: number;
  avg_return_2d: number;
  avg_return_3d: number;
  avg_return_5d: number;
  avg_return_10d: number;
  avg_return_20d: number;
  median_return_5d: number;
  best_return_5d: number;
  worst_return_5d: number;
  win_rate_1d: number;
  win_rate_2d: number;
  win_rate_3d: number;
  win_rate_5d: number;
  win_rate_10d: number;
  win_rate_20d: number;
  target_hit_rate_5d: number;
  stop_hit_rate_5d: number;
  sprint_hit_rate_5d: number;
  trend_hit_rate_10d: number;
  avg_mfe_5d: number;
  avg_mae_5d: number;
  avg_mfe_10d: number;
  avg_mae_10d: number;
  avg_mfe_20d: number;
  avg_mae_20d: number;
  rocket_hit_rate_20d: number;
  strong_rocket_hit_rate_20d: number;
  breakout_runway_20d: number;
  payoff_ratio_5d: number;
  payoff_ratio_20d: number;
  positive_edge: boolean;
  confidence: string;
};

type StrategyValidationSignal = {
  signal: string;
  return_basis?: string;
  sample_count: number;
  avg_return_3d: number;
  avg_return_5d: number;
  avg_return_10d: number;
  avg_return_20d: number;
  win_rate_5d: number;
  win_rate_10d: number;
  win_rate_20d: number;
  sprint_hit_rate_5d: number;
  trend_hit_rate_10d: number;
  rocket_hit_rate_20d: number;
  strong_rocket_hit_rate_20d: number;
  target_hit_rate_5d: number;
  stop_hit_rate_5d: number;
  confidence: string;
};

type StrategyValidationStock = {
  symbol: string;
  name: string;
  current_signal: string;
  current_rating: string;
  current_score: number;
  sample_count: number;
  avg_return_5d: number;
  win_rate_5d: number;
  avg_return_10d: number;
  win_rate_10d: number;
  avg_return_20d: number;
  win_rate_20d: number;
  sprint_hit_rate_5d: number;
  trend_hit_rate_10d: number;
  rocket_hit_rate_20d: number;
  strong_rocket_hit_rate_20d: number;
  avg_mfe_10d: number;
  avg_mae_10d: number;
  avg_mfe_20d: number;
  avg_mae_20d: number;
  target_hit_rate_5d: number;
  stop_hit_rate_5d: number;
  last_signal_date: string;
  confidence: string;
  book_selection_score?: number;
  validation_basis?: string;
  return_basis?: string;
  validation_scope?: string;
  validation_symbol_count?: number;
};

type StrategyValidationPeriod = {
  label: string;
  lookback_days?: number | null;
  window_note?: string;
  return_basis?: string;
  recommendation_count: number;
  validated_stock_count: number;
  coverage_rate: number;
  average_samples_per_stock: number;
  validation_score: number;
  verdict: string;
  sample_count: number;
  summary: StrategyValidationSummary;
  risk_flags: string[];
  stocks_without_history: string[];
  signal_pool_count?: number;
};

type StrategyValidation = {
  validation_basis?: string;
  return_basis?: string;
  lookback_candles: number;
  holding_days: number[];
  validation_pool_size?: number;
  validation_universe_size?: number;
  recommendation_count: number;
  validated_stock_count: number;
  coverage_rate: number;
  average_samples_per_stock: number;
  validation_score: number;
  verdict: string;
  sample_count: number;
  summary: StrategyValidationSummary;
  signal_breakdown: StrategyValidationSignal[];
  stock_breakdown: StrategyValidationStock[];
  notes: string[];
  risk_flags: string[];
  stocks_without_history: string[];
  strongest_signal?: string;
  weakest_signal?: string;
  recent_20d?: StrategyValidationPeriod;
  recent_60d?: StrategyValidationPeriod;
  full_period?: StrategyValidationPeriod;
};

const BACKEND_BASE = "https://twstock-realtime-screener1.onrender.com/stocks";
const VALIDATION_STORAGE_KEY = "twstock-validation-history-v1";
const VALIDATION_SIGNALS = ["突破前夕", "量增轉強", "整理待發", "溫和轉強"];
const EXCLUDED_VALIDATION_SIGNALS = ["短線過熱", "偏弱觀察", "偏弱整理"];

const PRICE_CATEGORIES = [
  { key: "all", label: "全部" },
  { key: "0-50", label: "0-50" },
  { key: "50-100", label: "50-100" },
  { key: "100-200", label: "100-200" },
  { key: "200-500", label: "200-500" },
  { key: "500+", label: "500+" },
] as const;

type CategoryKey = (typeof PRICE_CATEGORIES)[number]["key"];
type RankType = "recommend" | "up" | "down";

const ITEMS_PER_PAGE = 20;

function formatNumber(num?: number) {
  if (num === undefined || num === null || Number.isNaN(num)) return "-";
  return num.toLocaleString("zh-TW");
}

function formatPrice(num?: number) {
  if (num === undefined || num === null || Number.isNaN(num)) return "-";
  return num.toLocaleString("zh-TW");
}

function formatSigned(num?: number, digits = 2) {
  if (num === undefined || num === null || Number.isNaN(num)) return "-";
  return `${num > 0 ? "+" : num < 0 ? "" : ""}${num.toFixed(digits)}`;
}

function formatRatioPercent(value?: number, digits = 1) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}

function formatDateString(dateText?: string) {
  if (!dateText || dateText === "-") return "-";
  const clean = String(dateText).replace(/\D/g, "");
  if (clean.length === 8) {
    return `${clean.slice(0, 4)}/${clean.slice(4, 6)}/${clean.slice(6, 8)}`;
  }
  return dateText;
}

function getMarketLightColor(status?: string) {
  if (!status) return "#f59e0b";
  if (status.includes("開盤")) return "#22c55e";
  if (status.includes("收盤")) return "#ef4444";
  return "#f59e0b";
}

function normalizeStock(s: Stock): Stock {
  return {
    ...s,
    price: Number(s.price ?? 0),
    change: Number(s.change ?? 0),
    change_percent: Number(s.change_percent ?? 0),
    volume: Number(s.volume ?? 0),
    score: Number(s.score ?? 0),
    recommendation_score: Number(s.recommendation_score ?? 0),
  };
}

function getPageNumbers(currentPage: number, totalPages: number): number[] {
  const pages: number[] = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
    return pages;
  }
  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);
  if (start > 1) pages.push(1);
  if (start > 2) pages.push(-1);
  for (let i = start; i <= end; i++) pages.push(i);
  if (end < totalPages - 1) pages.push(-2);
  if (end < totalPages) pages.push(totalPages);
  return pages;
}

function stockToFocused(stock: Stock): FocusedStock {
  return {
    symbol: stock.symbol,
    name: stock.name,
    market: stock.market || "-",
    price: Number(stock.price || 0),
    change: Number(stock.change || 0),
    change_percent: Number(stock.change_percent || 0),
    volume: Number(stock.volume || 0),
    signal: stock.signal || "-",
    trend_type: stock.trend_type || "-",
    operation_rating: stock.operation_rating || "-",
    operation_bias: stock.operation_bias || "-",
    operation_style: stock.operation_style || "-",
    technical_comment: stock.technical_comment || stock.reason || "-",
    analysis: stock.reason || "-",
    strategy_action: stock.strategy_action || "-",
    entry_price: stock.entry_price || "-",
    target_price: stock.target_price || "-",
    stop_loss: stock.stop_loss || "-",
    risk_reward: stock.risk_reward || "-",
    risk_note: stock.risk_note || "-",
    update_time: stock.update_time || "-",
  };
}

function getRatingColor(rating?: string) {
  if (rating === "A") return "#ffd95f";
  if (rating === "B+") return "#7ee787";
  if (rating === "C") return "#7fb6ff";
  if (rating === "D") return "#ff9c9c";
  return "#dbe8ff";
}

function getConfidenceColor(confidence?: string) {
  if (confidence === "高") return "#7ee787";
  if (confidence === "中") return "#ffd95f";
  return "#ffb4b4";
}

function getValidationVerdictStyle(verdict?: string) {
  if (verdict === "可追蹤飆股" || verdict === "可採信") {
    return {
      accent: "#7ee787",
      surface: "rgba(58, 168, 89, 0.18)",
    };
  }
  if (verdict === "可用但保守") {
    return {
      accent: "#ffd95f",
      surface: "rgba(255, 217, 95, 0.16)",
    };
  }
  if (verdict === "觀察中") {
    return {
      accent: "#7fb6ff",
      surface: "rgba(96, 165, 250, 0.16)",
    };
  }
  if (verdict === "樣本不足") {
    return {
      accent: "#8fa9c9",
      surface: "rgba(143, 169, 201, 0.16)",
    };
  }
  return {
    accent: "#ff9c9c",
    surface: "rgba(255, 130, 130, 0.16)",
  };
}

function getFallbackValidationPeriod(validation: StrategyValidation): StrategyValidationPeriod {
  return {
    label: `近${validation.lookback_candles}日K樣本`,
    lookback_days: null,
    recommendation_count: validation.recommendation_count,
    validated_stock_count: validation.validated_stock_count,
    coverage_rate: validation.coverage_rate,
    average_samples_per_stock: validation.average_samples_per_stock,
    validation_score: validation.validation_score,
    verdict: validation.verdict,
    sample_count: validation.sample_count,
    summary: validation.summary,
    risk_flags: validation.risk_flags,
    stocks_without_history: validation.stocks_without_history,
    return_basis: validation.return_basis,
  };
}

function isValidationPeriodPositive(period?: StrategyValidationPeriod | null) {
  return Boolean(
    period &&
      period.sample_count >= 12 &&
      period.validation_score >= 63 &&
      period.summary.avg_return_5d > 0 &&
      period.summary.avg_return_10d > 0 &&
      period.summary.avg_return_20d > 0 &&
      period.summary.sprint_hit_rate_5d >= 0.15 &&
      period.summary.trend_hit_rate_10d >= 0.12 &&
      period.summary.rocket_hit_rate_20d >= 0.18 &&
      period.summary.breakout_runway_20d > 0
  );
}

function isValidationPeriodWeak(period?: StrategyValidationPeriod | null) {
  if (!period) return true;
  return (
    period.sample_count < 12 ||
    period.validation_score < 50 ||
    period.summary.avg_return_10d <= 0 ||
    period.summary.sprint_hit_rate_5d < 0.1 ||
    period.summary.trend_hit_rate_10d < 0.08 ||
    period.summary.avg_return_20d <= 0 ||
    period.summary.rocket_hit_rate_20d < 0.1
  );
}

function getValidationPeriodSnapshot(period?: StrategyValidationPeriod | null) {
  if (!period || period.sample_count <= 0) {
    return {
      status: "樣本不足",
      accent: "#8fa9c9",
      surface: "rgba(143, 169, 201, 0.12)",
      border: "rgba(143, 169, 201, 0.24)",
    };
  }

  const verdictStyle = getValidationVerdictStyle(period.verdict);
  if (period.verdict === "樣本不足") {
    return {
      status: "樣本待累積",
      accent: "#8fa9c9",
      surface: "rgba(143, 169, 201, 0.12)",
      border: "rgba(143, 169, 201, 0.24)",
    };
  }
  if (isValidationPeriodPositive(period)) {
    return { status: "可追蹤", accent: "#7ee787", surface: "rgba(58, 168, 89, 0.14)", border: "rgba(126, 231, 135, 0.26)" };
  }
  if (
    period.summary.avg_return_10d > 0 &&
    period.summary.trend_hit_rate_10d >= 0.1 &&
    period.summary.rocket_hit_rate_20d >= 0.12
  ) {
    return { status: "改善中", accent: "#ffd95f", surface: "rgba(255, 217, 95, 0.14)", border: "rgba(255, 217, 95, 0.24)" };
  }
  if (period.validation_score >= 50) {
    return { status: "觀察", accent: "#7fb6ff", surface: "rgba(96, 165, 250, 0.14)", border: "rgba(127, 182, 255, 0.24)" };
  }
  return {
    status: "飆股弱",
    accent: verdictStyle.accent,
    surface: verdictStyle.surface,
    border: `${verdictStyle.accent}33`,
  };
}

function getCategoryQuery(category: CategoryKey): {
  market?: string;
  price_min?: number;
  price_max?: number;
} {
  switch (category) {
    case "0-50":
      return { price_max: 50 };
    case "50-100":
      return { price_min: 50, price_max: 100 };
    case "100-200":
      return { price_min: 100, price_max: 200 };
    case "200-500":
      return { price_min: 200, price_max: 500 };
    case "500+":
      return { price_min: 500 };
    default:
      return {};
  }
}

function getSortQuery(rankType: RankType): {
  sort_by: string;
  sort_dir: "asc" | "desc";
} {
  if (rankType === "up") return { sort_by: "change_percent", sort_dir: "desc" };
  if (rankType === "down") return { sort_by: "change_percent", sort_dir: "asc" };
  return { sort_by: "recommendation_score", sort_dir: "desc" };
}

function buildCategoryCountsFromBackend(
  backendCategories: BackendCategory[],
  allTotal: number
): Record<CategoryKey, number> {
  const backendMap = new Map<string, number>();
  for (const item of backendCategories || []) {
    backendMap.set(item.key, Number(item.count || 0));
  }
  return {
    all: allTotal,
    "0-50":
      (backendMap.get("0-10") || 0) +
      (backendMap.get("10-20") || 0) +
      (backendMap.get("20-50") || 0),
    "50-100": backendMap.get("50-100") || 0,
    "100-200": backendMap.get("100-200") || 0,
    "200-500": backendMap.get("200-500") || 0,
    "500+": (backendMap.get("500-1000") || 0) + (backendMap.get("1000+") || 0),
  };
}

function roundTo(num: number, digits = 2) {
  const factor = 10 ** digits;
  return Math.round(num * factor) / factor;
}

function parseRiskRewardValue(text?: string) {
  const match = String(text || "").match(/1\s*:\s*([0-9.]+)/);
  return match ? Number(match[1]) : 0;
}

function safeDivide(numerator: number, denominator: number) {
  if (!denominator) return 0;
  return numerator / denominator;
}

function clampValue(value: number, min = 0, max = 1) {
  return Math.min(max, Math.max(min, value));
}

function formatPercent(value: number, digits = 0) {
  return `${(value * 100).toFixed(digits)}%`;
}

function getValidationBasisText(validation?: StrategyValidation | null) {
  if (!validation) return "尚無後端驗證資料";
  if (validation.validation_basis === "cross_stock_historical_signal_pool_with_book_proxy_prefilter") {
    return "歷史K同訊號/同評級 + 代理分預篩";
  }
  return validation.validation_basis || "跨股票同訊號驗證";
}

function getReturnBasisText(text?: string) {
  if (!text) return "訊號隔日開盤進場，N日報酬看第N個交易日收盤。";
  if (text.includes("訊號隔日開盤")) return text;
  return "訊號隔日開盤進場，N日報酬看第N個交易日收盤。";
}

function isValidationPass(record: ValidationRecord) {
  const base = Math.max(record.recommendationCount, 1);
  const validRate = safeDivide(record.validSignalCount, base);
  const strongRate = safeDivide(record.strongRatingCount, base);
  const excludedRate = safeDivide(record.excludedSignalCount, base);
  const historicalRate = safeDivide(record.historicalKCount, base);

  return validRate >= 0.8 && strongRate >= 0.7 && excludedRate === 0 && historicalRate >= 0.8;
}

function buildValidationHealth(record: ValidationRecord): ValidationHealth {
  const base = Math.max(record.recommendationCount, 1);
  const validRate = safeDivide(record.validSignalCount, base);
  const strongRate = safeDivide(record.strongRatingCount, base);
  const excludedRate = safeDivide(record.excludedSignalCount, base);
  const historicalRate = safeDivide(record.historicalKCount, base);
  const scoreRatio = clampValue(record.averageScore / 100);
  const riskRewardRatio = clampValue(record.averageRiskReward / 2.5);

  const score = Math.round(
    historicalRate * 30 +
      validRate * 25 +
      strongRate * 20 +
      (1 - excludedRate) * 15 +
      scoreRatio * 5 +
      riskRewardRatio * 5
  );

  if (score >= 85) {
    return {
      score,
      label: "邏輯通過",
      summary: "有效訊號、強勢評級與日 K 覆蓋率都維持高檔，這批輸出有符合原本的偏多選股邏輯。",
      accent: "#7ee787",
      surface: "rgba(58, 168, 89, 0.18)",
    };
  }

  if (score >= 70) {
    return {
      score,
      label: "大致可用",
      summary: "整體結構仍在可接受範圍，但有部分訊號或評級比例需要再觀察，信任度不宜拉滿。",
      accent: "#ffd95f",
      surface: "rgba(255, 217, 95, 0.16)",
    };
  }

  return {
    score,
    label: "需要留意",
    summary: "今天的輸出結構偏鬆，代表選股邏輯沒有完整落實在名單上，建議降低主觀信任度。",
    accent: "#ff9c9c",
    surface: "rgba(255, 130, 130, 0.16)",
  };
}

function buildValidationHistoryStats(records: ValidationRecord[]): ValidationHistoryStats | null {
  if (!records.length) return null;

  const signalCount = new Map<string, number>();
  let passCount = 0;
  let recommendationCountSum = 0;
  let historicalRateSum = 0;
  let strongRateSum = 0;
  let validRateSum = 0;
  let excludedRateSum = 0;
  let scoreSum = 0;
  let riskRewardSum = 0;

  for (const record of records) {
    const base = Math.max(record.recommendationCount, 1);
    recommendationCountSum += record.recommendationCount;
    historicalRateSum += safeDivide(record.historicalKCount, base);
    strongRateSum += safeDivide(record.strongRatingCount, base);
    validRateSum += safeDivide(record.validSignalCount, base);
    excludedRateSum += safeDivide(record.excludedSignalCount, base);
    scoreSum += record.averageScore;
    riskRewardSum += record.averageRiskReward;

    if (isValidationPass(record)) {
      passCount += 1;
    }

    for (const stock of record.stocks || []) {
      const signal = stock.signal || "未分類";
      signalCount.set(signal, (signalCount.get(signal) || 0) + 1);
    }
  }

  const totalRecords = records.length;

  return {
    totalRecords,
    passCount,
    averageRecommendationCount: roundTo(recommendationCountSum / totalRecords, 1),
    averageHistoricalRate: roundTo(historicalRateSum / totalRecords, 4),
    averageStrongRate: roundTo(strongRateSum / totalRecords, 4),
    averageValidRate: roundTo(validRateSum / totalRecords, 4),
    averageExcludedRate: roundTo(excludedRateSum / totalRecords, 4),
    averageScore: roundTo(scoreSum / totalRecords),
    averageRiskReward: roundTo(riskRewardSum / totalRecords),
    topSignals: Array.from(signalCount.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4)
      .map(([signal, count]) => `${signal} ${count}次`),
  };
}

function buildValidationRecord(
  source: Stock[],
  dataDate?: string,
  lastUpdate?: string
): ValidationRecord | null {
  if (!source.length) return null;

  const safeSource = source.map(normalizeStock);
  const signalCount = new Map<string, number>();
  for (const stock of safeSource) {
    const signal = stock.signal || "未分類";
    signalCount.set(signal, (signalCount.get(signal) || 0) + 1);
  }

  const scoreValues = safeSource.map((stock) => Number(stock.recommendation_score || stock.score || 0));
  const riskRewardValues = safeSource
    .map((stock) => parseRiskRewardValue(stock.risk_reward))
    .filter((value) => value > 0);

  return {
    dataDate: dataDate || "",
    lastUpdate: lastUpdate || "",
    symbols: safeSource.map((stock) => stock.symbol),
    stockLabels: safeSource.map((stock) => `${stock.symbol} ${stock.name}`),
    stocks: safeSource.map((stock) => ({
      symbol: stock.symbol,
      name: stock.name,
      signal: stock.signal || "-",
      operationRating: stock.operation_rating || "-",
      recommendationScore: Number(stock.recommendation_score || stock.score || 0),
      bookSelectionScore: Number(stock.book_selection_score || 0),
      reason: stock.reason || stock.technical_comment || "-",
      entryPrice: stock.entry_price || "-",
      targetPrice: stock.target_price || "-",
      stopLoss: stock.stop_loss || "-",
      riskReward: stock.risk_reward || "-",
    })),
    recommendationCount: safeSource.length,
    historicalKCount: safeSource.filter((stock) => stock.analysis_source === "historical_k").length,
    strongRatingCount: safeSource.filter(
      (stock) => stock.operation_rating === "A" || stock.operation_rating === "B+"
    ).length,
    validSignalCount: safeSource.filter((stock) =>
      VALIDATION_SIGNALS.includes(stock.signal || "")
    ).length,
    excludedSignalCount: safeSource.filter((stock) =>
      EXCLUDED_VALIDATION_SIGNALS.includes(stock.signal || "")
    ).length,
    averageScore: roundTo(
      scoreValues.reduce((sum, value) => sum + value, 0) / Math.max(scoreValues.length, 1)
    ),
    averageRiskReward: roundTo(
      riskRewardValues.reduce((sum, value) => sum + value, 0) / Math.max(riskRewardValues.length, 1)
    ),
    signalSummary: Array.from(signalCount.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([signal, count]) => `${signal} ${count}檔`),
  };
}

export default function Home() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [recommendations, setRecommendations] = useState<Stock[]>([]);
  const [backendCategories, setBackendCategories] = useState<BackendCategory[]>([]);
  const [marketStatus, setMarketStatus] = useState("-");
  const [dataDate, setDataDate] = useState("-");
  const [lastUpdate, setLastUpdate] = useState("-");
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<CategoryKey>("all");
  const [rankType, setRankType] = useState<RankType>("recommend");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isMobile, setIsMobile] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [focusedStock, setFocusedStock] = useState<FocusedStock | null>(null);
  const [manualSelectedSymbol, setManualSelectedSymbol] = useState("");
  const [total, setTotal] = useState(0);
  const [allTotal, setAllTotal] = useState(0);
  const [showValidationPanel, setShowValidationPanel] = useState(false);
  const [showRecommendationsPanel, setShowRecommendationsPanel] = useState(true);
  const [showValidationDetails, setShowValidationDetails] = useState(false);
  const [strategyValidation, setStrategyValidation] = useState<StrategyValidation | null>(null);
  const [validationHistory, setValidationHistory] = useState<ValidationRecord[]>([]);

  const initialLoadedRef = useRef(false);
  const pagedRequestIdRef = useRef(0);
  const recommendationsRequestIdRef = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm.trim());
      setCurrentPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 900);
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  async function fetchRecommendations() {
    const requestId = ++recommendationsRequestIdRef.current;
    const params = new URLSearchParams({
      limit: "30",
      offset: "0",
      sort_by: "recommendation_score",
      sort_dir: "desc",
    });
    const res = await fetch(`${BACKEND_BASE}?${params.toString()}`, { cache: "no-store" });
    const data: ApiResponse = await res.json();
    if (!data.success) throw new Error(data.error || data.message || "取得推薦資料失敗");

    const source = (data.recommendations?.length ? data.recommendations : data.stocks || []).map(
      normalizeStock
    );
    const safeRecommendations = source
      .filter((stock) => stock.market === "上市" || stock.market === "上櫃")
      .sort(
        (a, b) =>
          (b.recommendation_score || b.score || 0) - (a.recommendation_score || a.score || 0)
      )
      .slice(0, 10);
    if (requestId !== recommendationsRequestIdRef.current) return;
    setRecommendations(safeRecommendations);
    setStrategyValidation(data.validation || null);
  }

  async function fetchPagedStocks(
    override?: Partial<{
      category: CategoryKey;
      page: number;
      rank: RankType;
      keyword: string;
    }>,
    options?: {
      forceRefresh?: boolean;
      manageLoading?: boolean;
    }
  ) {
    const requestId = ++pagedRequestIdRef.current;
    const manageLoading = options?.manageLoading ?? true;

    if (manageLoading) setLoading(true);
    setError("");

    try {
      const category = override?.category ?? selectedCategory;
      const page = override?.page ?? currentPage;
      const rank = override?.rank ?? rankType;
      const keyword = override?.keyword ?? debouncedSearchTerm;

      const categoryQuery = getCategoryQuery(category);
      const sortQuery = getSortQuery(rank);

      const params = new URLSearchParams({
        limit: String(ITEMS_PER_PAGE),
        offset: String((page - 1) * ITEMS_PER_PAGE),
        sort_by: sortQuery.sort_by,
        sort_dir: sortQuery.sort_dir,
      });

      if (keyword) params.set("q", keyword);
      if (options?.forceRefresh) params.set("force_refresh", "true");
      if (categoryQuery.market) params.set("market", categoryQuery.market);
      if (categoryQuery.price_min !== undefined) {
        params.set("price_min", String(categoryQuery.price_min));
      }
      if (categoryQuery.price_max !== undefined) {
        params.set("price_max", String(categoryQuery.price_max));
      }

      const res = await fetch(`${BACKEND_BASE}?${params.toString()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: ApiResponse = await res.json();
      if (requestId !== pagedRequestIdRef.current) return;
      if (!data.success) throw new Error(data.error || data.message || "取得資料失敗");

      const safeStocks = (data.stocks || []).map(normalizeStock);
      setStocks(safeStocks);
      setTotal(Number(data.total || 0));

      if (data.all_total !== undefined) setAllTotal(Number(data.all_total));
      if (data.categories) setBackendCategories(data.categories);
      if (data.recommendations?.length) {
        setRecommendations((data.recommendations || []).map(normalizeStock).slice(0, 10));
        setStrategyValidation(data.validation || null);
      }

      setMarketStatus(data.market_status || "-");
      setDataDate(
        data.data_date ||
          data.source_summary?.twse_data_date ||
          data.source_summary?.tpex_data_date ||
          "-"
      );
      setLastUpdate(data.last_update || new Date().toLocaleString("zh-TW"));

      if (data.focused_stock) {
        setFocusedStock(data.focused_stock);
      } else if (!manualSelectedSymbol && !keyword) {
        setFocusedStock(null);
      }
    } catch (err) {
      if (requestId !== pagedRequestIdRef.current) return;
      setError(err instanceof Error ? err.message : "載入失敗");
    } finally {
      if (manageLoading && requestId === pagedRequestIdRef.current) {
        setLoading(false);
      }
    }
  }

  async function fetchAllData(options?: { forceRefresh?: boolean }) {
    try {
      setLoading(true);
      setError("");
      await fetchPagedStocks(
        {
          category: selectedCategory,
          page: currentPage,
          rank: rankType,
          keyword: debouncedSearchTerm,
        },
        {
          forceRefresh: options?.forceRefresh,
          manageLoading: false,
        }
      );
      await fetchRecommendations();
      initialLoadedRef.current = true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "載入失敗");
    } finally {
      setLoading(false);
    }
  }

  async function fetchRecommendationsSafe(options?: { forceRefresh?: boolean }) {
    const requestId = ++recommendationsRequestIdRef.current;

    try {
      const params = new URLSearchParams({
        limit: "30",
        offset: "0",
        sort_by: "recommendation_score",
        sort_dir: "desc",
      });
      if (options?.forceRefresh) params.set("force_refresh", "true");

      const res = await fetch(`${BACKEND_BASE}?${params.toString()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: ApiResponse = await res.json();
      if (!data.success) throw new Error(data.error || data.message || "載入失敗");

      const source = (data.recommendations?.length ? data.recommendations : data.stocks || []).map(
        normalizeStock
      );
      const safeRecommendations = source
        .filter((stock) => stock.market === "上市" || stock.market === "上櫃")
        .sort(
          (a, b) =>
            (b.recommendation_score || b.score || 0) - (a.recommendation_score || a.score || 0)
        )
        .slice(0, 10);

      if (requestId !== recommendationsRequestIdRef.current) return null;
      setRecommendations(safeRecommendations);
      setStrategyValidation(data.validation || null);
      return data;
    } catch (err) {
      if (requestId !== recommendationsRequestIdRef.current) return null;
      setError(err instanceof Error ? err.message : "載入失敗");
      return null;
    }
  }

  async function fetchPagedStocksSafe(
    override?: Partial<{
      category: CategoryKey;
      page: number;
      rank: RankType;
      keyword: string;
    }>,
    options?: {
      forceRefresh?: boolean;
      manageLoading?: boolean;
    }
  ) {
    const requestId = ++pagedRequestIdRef.current;
    const manageLoading = options?.manageLoading ?? true;

    if (manageLoading) setLoading(true);
    setError("");

    try {
      const category = override?.category ?? selectedCategory;
      const page = override?.page ?? currentPage;
      const rank = override?.rank ?? rankType;
      const keyword = override?.keyword ?? debouncedSearchTerm;

      const categoryQuery = getCategoryQuery(category);
      const sortQuery = getSortQuery(rank);

      const params = new URLSearchParams({
        limit: String(ITEMS_PER_PAGE),
        offset: String((page - 1) * ITEMS_PER_PAGE),
        sort_by: sortQuery.sort_by,
        sort_dir: sortQuery.sort_dir,
      });

      if (keyword) params.set("q", keyword);
      if (options?.forceRefresh) params.set("force_refresh", "true");
      if (categoryQuery.market) params.set("market", categoryQuery.market);
      if (categoryQuery.price_min !== undefined) {
        params.set("price_min", String(categoryQuery.price_min));
      }
      if (categoryQuery.price_max !== undefined) {
        params.set("price_max", String(categoryQuery.price_max));
      }

      const res = await fetch(`${BACKEND_BASE}?${params.toString()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data: ApiResponse = await res.json();
      if (requestId !== pagedRequestIdRef.current) return null;
      if (!data.success) throw new Error(data.error || data.message || "載入失敗");

      const safeStocks = (data.stocks || []).map(normalizeStock);
      setStocks(safeStocks);
      setTotal(Number(data.total || 0));

      if (data.all_total !== undefined) setAllTotal(Number(data.all_total));
      if (data.categories) setBackendCategories(data.categories);
      if (data.recommendations?.length) {
        recommendationsRequestIdRef.current += 1;
        setRecommendations((data.recommendations || []).map(normalizeStock).slice(0, 10));
        setStrategyValidation(data.validation || null);
      }

      setMarketStatus(data.market_status || "-");
      setDataDate(
        data.data_date ||
          data.source_summary?.twse_data_date ||
          data.source_summary?.tpex_data_date ||
          "-"
      );
      setLastUpdate(data.last_update || new Date().toLocaleString("zh-TW"));

      if (data.focused_stock) {
        setFocusedStock(data.focused_stock);
      } else if (!manualSelectedSymbol && !keyword) {
        setFocusedStock(null);
      }

      return data;
    } catch (err) {
      if (requestId !== pagedRequestIdRef.current) return null;
      setError(err instanceof Error ? err.message : "載入失敗");
      return null;
    } finally {
      if (manageLoading && requestId === pagedRequestIdRef.current) {
        setLoading(false);
      }
    }
  }

  async function fetchAllDataSafe(options?: { forceRefresh?: boolean }) {
    setLoading(true);
    setError("");

    const data = await fetchPagedStocksSafe(
      {
        category: selectedCategory,
        page: currentPage,
        rank: rankType,
        keyword: debouncedSearchTerm,
      },
      {
        forceRefresh: options?.forceRefresh,
        manageLoading: false,
      }
    );

    if (!data?.recommendations?.length) {
      await fetchRecommendationsSafe({ forceRefresh: options?.forceRefresh });
    }

    initialLoadedRef.current = true;
    setLoading(false);
  }

  useEffect(() => {
    fetchAllDataSafe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!initialLoadedRef.current) return;
    fetchPagedStocksSafe({
      category: selectedCategory,
      page: currentPage,
      rank: rankType,
      keyword: debouncedSearchTerm,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, debouncedSearchTerm, selectedCategory, rankType]);

  useEffect(() => {
    if (!initialLoadedRef.current) return;
    const timer = setInterval(() => {
      fetchPagedStocksSafe({
        category: selectedCategory,
        page: currentPage,
        rank: rankType,
        keyword: debouncedSearchTerm,
      });
    }, 120000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, selectedCategory, rankType, debouncedSearchTerm]);

  const categoryCounts = useMemo(
    () => buildCategoryCountsFromBackend(backendCategories, allTotal),
    [backendCategories, allTotal]
  );

  const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE));

  useEffect(() => {
    if (currentPage > totalPages) setCurrentPage(totalPages);
  }, [currentPage, totalPages]);

  const pageNumbers = useMemo(
    () => getPageNumbers(currentPage, totalPages),
    [currentPage, totalPages]
  );

  const activeFocusedStock = useMemo(() => {
    if (manualSelectedSymbol) {
      const manualTarget =
        stocks.find((stock) => stock.symbol === manualSelectedSymbol) ||
        recommendations.find((stock) => stock.symbol === manualSelectedSymbol);
      if (manualTarget) return stockToFocused(manualTarget);
    }
    if (focusedStock) return focusedStock;
    if (debouncedSearchTerm && stocks.length === 1) return stockToFocused(stocks[0]);
    return null;
  }, [manualSelectedSymbol, stocks, recommendations, focusedStock, debouncedSearchTerm]);

  const validationRecord = useMemo(
    () => buildValidationRecord(recommendations, dataDate, lastUpdate),
    [recommendations, dataDate, lastUpdate]
  );

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(VALIDATION_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        setValidationHistory(parsed);
      }
    } catch {
      setValidationHistory([]);
    }
  }, []);

  useEffect(() => {
    if (!validationRecord) return;

    setValidationHistory((prev) => {
      const next = [
        validationRecord,
        ...prev.filter((item) => item.dataDate !== validationRecord.dataDate),
      ].slice(0, 12);

      try {
        window.localStorage.setItem(VALIDATION_STORAGE_KEY, JSON.stringify(next));
      } catch {}

      return next;
    });
  }, [validationRecord]);

  const previousValidationRecord = useMemo(() => {
    if (!validationRecord) return null;
    return validationHistory.find((item) => item.dataDate !== validationRecord.dataDate) || null;
  }, [validationHistory, validationRecord]);

  const repeatedPickCount = useMemo(() => {
    if (!validationRecord || !previousValidationRecord) return 0;
    const previousSymbols = new Set(previousValidationRecord.symbols);
    return validationRecord.symbols.filter((symbol) => previousSymbols.has(symbol)).length;
  }, [previousValidationRecord, validationRecord]);

  const validationHealth = useMemo(() => {
    if (!validationRecord) return null;
    return buildValidationHealth(validationRecord);
  }, [validationRecord]);

  const validationHistoryStats = useMemo(() => {
    const records =
      validationHistory.length > 0
        ? validationHistory
        : validationRecord
          ? [validationRecord]
          : [];

    return buildValidationHistoryStats(records);
  }, [validationHistory, validationRecord]);

  const validationHighlights = useMemo(() => {
    if (!validationRecord) return [];

    const base = Math.max(validationRecord.recommendationCount, 1);
    const validRate = safeDivide(validationRecord.validSignalCount, base);
    const strongRate = safeDivide(validationRecord.strongRatingCount, base);
    const excludedRate = safeDivide(validationRecord.excludedSignalCount, base);
    const historicalRate = safeDivide(validationRecord.historicalKCount, base);

    return [
      `有效訊號覆蓋 ${formatPercent(validRate)}，主軸集中在 ${validationRecord.signalSummary.join(" / ") || "未分類"}。`,
      `A / B+ 評級占比 ${formatPercent(strongRate)}，日 K 驗證率 ${formatPercent(historicalRate)}，${
        excludedRate === 0 ? "目前沒有落入排除訊號。" : `排除訊號占比 ${formatPercent(excludedRate)}。`
      }`,
      previousValidationRecord
        ? `和前一次紀錄相比重複入選 ${repeatedPickCount} 檔，這代表邏輯輸出有${repeatedPickCount > 0 ? "延續性" : "明顯換股"}。`
        : "這是目前第一筆驗證紀錄，後續累積幾天後會更容易判斷邏輯穩定度。",
    ];
  }, [previousValidationRecord, repeatedPickCount, validationRecord]);

  const validationSamplePreview = useMemo(() => {
    if (!validationRecord) return "-";

    const labels = validationRecord.stockLabels.slice(0, 3);
    const extra = validationRecord.stockLabels.length - labels.length;
    return `${labels.join(" / ")}${extra > 0 ? ` / +${extra}檔` : ""}`;
  }, [validationRecord]);

  const historicalValidationTone = useMemo(() => {
    if (!strategyValidation) return null;

    const sampleCount = Number(strategyValidation.summary?.sample_count || 0);
    const sprintHitRate5d = Number(strategyValidation.summary?.sprint_hit_rate_5d || 0);
    const trendHitRate10d = Number(strategyValidation.summary?.trend_hit_rate_10d || 0);
    const avgReturn20d = Number(strategyValidation.summary?.avg_return_20d || 0);
    const rocketHitRate20d = Number(strategyValidation.summary?.rocket_hit_rate_20d || 0);
    const verdictStyle = getValidationVerdictStyle(strategyValidation.verdict);

    if (strategyValidation.verdict === "樣本不足") {
      return {
        label: "樣本不足",
        summary: "歷史對照還不夠厚，先把這份結果當成方向參考，不要急著當成實單系統。",
        accent: verdictStyle.accent,
        surface: verdictStyle.surface,
      };
    }

    if (strategyValidation.validation_score >= 78) {
      return {
        label: strategyValidation.verdict || "飆股優勢成立",
        summary: "5日急拉、10日主升、20日延續三段命中率都站得住，這套邏輯已開始具備抓波段股能力。",
        accent: verdictStyle.accent,
        surface: verdictStyle.surface,
      };
    }

    if (strategyValidation.validation_score >= 63) {
      return {
        label: strategyValidation.verdict || "略有飆股優勢",
        summary: `5日急拉 ${formatRatioPercent(sprintHitRate5d)}、10日主升 ${formatRatioPercent(trendHitRate10d)}、20日延續 ${formatRatioPercent(rocketHitRate20d)}，已有打底但還不到可以完全放大部位的程度。`,
        accent: verdictStyle.accent,
        surface: verdictStyle.surface,
      };
    }

    if (sampleCount < 12) {
      return {
        label: "樣本偏少",
        summary: "目前有一些參考價值，但還不足以只靠這份飆股驗證就確認邏輯優勢。",
        accent: verdictStyle.accent,
        surface: verdictStyle.surface,
      };
    }

    return {
      label: strategyValidation.verdict || "飆股優勢未明",
      summary:
        avgReturn20d > 0 || trendHitRate10d >= 0.12 || rocketHitRate20d >= 0.15
          ? "雖然有局部亮點，但整體抓飆股的驗證分數還不夠高，這套邏輯仍要保守看待。"
          : "歷史上這套訊號沒有穩定拉開5日急拉、10日主升與20日延續的命中率，代表邏輯還需要再調整。",
      accent: verdictStyle.accent,
      surface: verdictStyle.surface,
    };
  }, [strategyValidation]);

  const validationPeriods = useMemo(() => {
    if (!strategyValidation) return [];

    const fullPeriod = strategyValidation.full_period || getFallbackValidationPeriod(strategyValidation);
    return [
      { key: "recent_20d", label: "近20日", period: strategyValidation.recent_20d || null },
      { key: "recent_60d", label: "近60日", period: strategyValidation.recent_60d || null },
      { key: "full_period", label: fullPeriod.label, period: fullPeriod },
    ];
  }, [strategyValidation]);

  const combinedValidationSummary = useMemo(() => {
    if (!validationRecord || !validationHealth || !validationHistoryStats) return null;

    const structureGood = validationHealth.score >= 85;
    const positivePeriods = validationPeriods.filter(({ period }) => isValidationPeriodPositive(period));
    const recent20 = validationPeriods.find((item) => item.key === "recent_20d")?.period || null;
    const recent60 = validationPeriods.find((item) => item.key === "recent_60d")?.period || null;
    const fullPeriod = validationPeriods.find((item) => item.key === "full_period")?.period || null;
    const hasSampleIssue = validationPeriods.some(({ period }) => !period || period.verdict === "樣本不足" || period.sample_count <= 0);

    let summary = "";
    if (strategyValidation && historicalValidationTone) {
      if (structureGood && positivePeriods.length === validationPeriods.length) {
        summary = "今天結構、近20日、近60日與較長樣本的歷史K同訊號驗證都站得住，且已用代理分預篩，這套邏輯已接近可實戰的飆股模式。";
      } else if (structureGood && isValidationPeriodPositive(recent20) && !isValidationPeriodPositive(recent60)) {
        summary = "今天結構很乾淨，近20日的三段驗證已開始改善，但近60日與較長樣本還沒完全跟上，因此先觀察不要直接放大。";
      } else if (structureGood && hasSampleIssue) {
        summary = "今天結構很乾淨，但歷史K同訊號與代理分預篩後的飆股樣本還在累積，先不要因為今天型態漂亮就直接當成可實單系統。";
      } else if (structureGood) {
        summary = "今天結構很乾淨，但 5 / 10 / 20 日三段驗證還沒一致轉強，因此暫不建議直接依賴。";
      } else if (positivePeriods.length >= 2) {
        summary = "歷史飆股驗證不差，但今天這批名單沒有完全照規則長出來，因此今天不能直接照單全收。";
      } else {
      summary = "目前近20日、近60日與較長樣本的歷史K同訊號 5 / 10 / 20 日驗證都沒有一致拉開，因此這套邏輯暫時只能觀察。";
      }
    } else {
      summary = `今天結構分數 ${validationHealth.score}/100，但歷史飆股覆蓋仍不足，今天資訊還不完整。`;
    }

    const missingPeriodLabel =
      validationPeriods.find(({ period }) => !period || period.sample_count <= 0 || period.verdict === "樣本不足")?.label || "";
    const weakestPeriod =
      validationPeriods.find(({ period }) => period && isValidationPeriodWeak(period))?.period || null;

    let directRiskMessage: string | null = null;
    if (missingPeriodLabel) {
      directRiskMessage = `${missingPeriodLabel} 的歷史K同訊號飆股樣本還不夠，先累積資料再判斷是否真的有 edge。`;
    } else if (weakestPeriod) {
      directRiskMessage = `${weakestPeriod.label} 的 5 / 10 / 20 日命中率為 ${formatRatioPercent(
        weakestPeriod.summary.sprint_hit_rate_5d
      )} / ${formatRatioPercent(weakestPeriod.summary.trend_hit_rate_10d)} / ${formatRatioPercent(
        weakestPeriod.summary.rocket_hit_rate_20d
      )}，抓波段的優勢還沒拉開。`;
    } else if (fullPeriod?.risk_flags?.length) {
      directRiskMessage = fullPeriod.risk_flags[0];
    }

    return {
      summary,
      risk:
        directRiskMessage ||
        strategyValidation?.risk_flags?.[0] ||
        validationHighlights[0] ||
        "目前沒有額外風險提醒。",
    };
  }, [
    historicalValidationTone,
    strategyValidation,
    validationHealth,
    validationHighlights,
    validationHistoryStats,
    validationRecord,
    validationPeriods,
  ]);

  const validationQuickState = useMemo(() => {
    if (!validationHealth) return null;

    const recent20 = validationPeriods.find((item) => item.key === "recent_20d")?.period || null;
    const recent60 = validationPeriods.find((item) => item.key === "recent_60d")?.period || null;
    const fullPeriod = validationPeriods.find((item) => item.key === "full_period")?.period || null;
    const hasSampleIssue = validationPeriods.some(({ period }) => !period || period.verdict === "樣本不足" || period.sample_count <= 0);

    if (validationHealth.score >= 85 && validationPeriods.length > 0 && validationPeriods.every(({ period }) => isValidationPeriodPositive(period))) {
      return {
        label: "飆股模式成立",
        detail: "今天結構和 5 / 10 / 20 日三段驗證同步站上來。",
        accent: "#7ee787",
        surface: "rgba(58, 168, 89, 0.14)",
      };
    }

    if (validationHealth.score >= 85 && hasSampleIssue) {
      return {
        label: "結構好，樣本待累積",
        detail: "今天名單乾淨，但歷史飆股樣本還不夠厚。",
        accent: "#8fa9c9",
        surface: "rgba(143, 169, 201, 0.14)",
      };
    }

    if (validationHealth.score >= 85 && isValidationPeriodPositive(recent20) && !isValidationPeriodPositive(recent60)) {
      return {
        label: "近期有飆股感",
        detail: "近20日的急拉、主升、延續開始轉強，但近60日和較長樣本還沒完全跟上。",
        accent: "#ffd95f",
        surface: "rgba(255, 217, 95, 0.14)",
      };
    }

    if (validationHealth.score >= 85 && !isValidationPeriodPositive(fullPeriod)) {
      return {
        label: "今天漂亮，飆股驗證未跟上",
        detail: "今天名單乾淨，但驗證還不足以直接照做。",
        accent: "#ff9c9c",
        surface: "rgba(255, 130, 130, 0.16)",
      };
    }

    return {
      label: "先觀察",
      detail: "先看近20日和近60日的歷史K同訊號 5 / 10 / 20 日命中率有沒有同步改善。",
      accent: "#7fb6ff",
      surface: "rgba(96, 165, 250, 0.14)",
    };
  }, [validationHealth, validationPeriods]);

  const validationPeriodCards = useMemo(
    () =>
      [
        {
          key: "today_structure",
          label: "今日結構",
          score: `${validationHealth?.score ?? 0}/100`,
          status: validationHealth?.label || "-",
          accent: validationHealth?.accent || "#8fa9c9",
          surface: validationHealth?.surface || "rgba(143, 169, 201, 0.12)",
          border: `${validationHealth?.accent || "#8fa9c9"}33`,
          metrics: [
            `穩定度 ${validationHistoryStats?.passCount ?? 0}/${validationHistoryStats?.totalRecords ?? 0}`,
            `主訊號 ${validationRecord?.signalSummary.join(" / ") || "-"}`,
          ],
          note: "只看今天推薦名單是否乾淨，不代表歷史命中率。",
        },
        ...validationPeriods.map(({ key, label, period }) => {
          const tone = getValidationPeriodSnapshot(period);
          return {
            key,
            label,
            score: period ? `${period.validation_score}/100` : "-",
            status: tone.status,
            accent: tone.accent,
            surface: tone.surface,
            border: tone.border,
            metrics:
              !period || period.sample_count <= 0
                ? ["尚無足夠樣本", "先累積資料"]
                : [
                    `樣本 ${period.sample_count} 筆 / 覆蓋 ${formatRatioPercent(period.coverage_rate)}`,
                    `5日急拉 ${formatRatioPercent(period.summary.sprint_hit_rate_5d)} / ${formatSigned(period.summary.avg_return_5d)}%`,
                    `10日主升 ${formatRatioPercent(period.summary.trend_hit_rate_10d)} / ${formatSigned(period.summary.avg_return_10d)}%`,
                    `20日延續 ${formatRatioPercent(period.summary.rocket_hit_rate_20d)} / ${formatSigned(period.summary.avg_return_20d)}%`,
                  ],
            note: period?.window_note || period?.return_basis || strategyValidation?.return_basis || "",
          };
        }),
      ],
    [strategyValidation, validationHealth, validationHistoryStats, validationPeriods, validationRecord]
  );

  const toggleValidationPanel = () => {
    setShowValidationPanel((prev) => {
      const next = !prev;
      if (next) {
        setShowRecommendationsPanel(false);
        setShowValidationDetails(false);
      }
      return next;
    });
  };

  const toggleRecommendationsPanel = () => {
    setShowRecommendationsPanel((prev) => {
      const next = !prev;
      if (next) setShowValidationPanel(false);
      return next;
    });
  };

  const panelStyle: React.CSSProperties = {
    background: "linear-gradient(180deg, #0d2f63 0%, #0a2a57 100%)",
    border: "1px solid rgba(80, 140, 220, 0.22)",
    borderRadius: "22px",
    padding: isMobile ? "18px" : "24px",
    minHeight: isMobile ? "auto" : "540px",
    boxShadow: "0 10px 28px rgba(0,0,0,0.12)",
    overflow: "hidden",
  };

  const recommendationPanelStyle: React.CSSProperties = {
    ...panelStyle,
    minHeight: showRecommendationsPanel ? (isMobile ? "auto" : "540px") : "auto",
  };

  const marketLightColor = getMarketLightColor(marketStatus);

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "linear-gradient(180deg, #08264d 0%, #0a2d5e 100%)",
        color: "#ffffff",
      }}
    >
      <div
        style={{
          width: "100%",
          borderBottom: "1px solid rgba(80, 140, 220, 0.15)",
          background: "rgba(7, 33, 70, 0.55)",
          backdropFilter: "blur(6px)",
        }}
      >
        <div
          style={{
            maxWidth: "1400px",
            margin: "0 auto",
            padding: isMobile ? "14px 16px" : "14px 36px",
            display: "flex",
            alignItems: isMobile ? "flex-start" : "center",
            justifyContent: "space-between",
            gap: "16px",
            flexWrap: "wrap",
            flexDirection: isMobile ? "column" : "row",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "14px", flexWrap: "wrap" }}>
            <div
              style={{
                fontSize: isMobile ? "28px" : "34px",
                fontWeight: 900,
                lineHeight: 1,
                letterSpacing: "1px",
                color: "#5ea4ff",
              }}
            >
              TWSTOCK
            </div>
            <div style={{ fontSize: isMobile ? "20px" : "24px", opacity: 0.95, fontWeight: 700 }}>
              - 即時選股系統
            </div>
          </div>

          <div
            style={{
              display: "flex",
              alignItems: isMobile ? "stretch" : "center",
              gap: "12px",
              flexWrap: "wrap",
              justifyContent: "flex-end",
              width: isMobile ? "100%" : "auto",
              flexDirection: isMobile ? "column" : "row",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px 18px",
                padding: "10px 16px",
                borderRadius: "14px",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                color: "#e8f1ff",
                fontSize: "14px",
                fontWeight: 700,
                flexWrap: "wrap",
                width: isMobile ? "100%" : "auto",
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span
                  style={{
                    width: "10px",
                    height: "10px",
                    borderRadius: "50%",
                    background: marketLightColor,
                    boxShadow: `0 0 6px ${marketLightColor}`,
                    display: "inline-block",
                  }}
                />
                市場狀態：{marketStatus}
              </span>
              <span>資料日期：{formatDateString(dataDate)}</span>
              <span>最後更新：{lastUpdate}</span>
            </div>

            <button
              type="button"
              onClick={() => fetchAllDataSafe({ forceRefresh: true })}
              disabled={loading}
              style={{
                border: "none",
                borderRadius: "12px",
                padding: "10px 16px",
                background: "linear-gradient(180deg, #5aa5ff 0%, #3c7ff1 100%)",
                color: "#fff",
                fontWeight: 800,
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.7 : 1,
                minWidth: "78px",
                width: isMobile ? "100%" : "auto",
              }}
            >
              {loading ? "更新中" : "更新"}
            </button>
          </div>
        </div>
      </div>

      <div
        style={{
          maxWidth: "1400px",
          margin: "0 auto",
          padding: isMobile ? "18px 16px 24px" : "26px 36px",
        }}
      >
        {error && (
          <div
            style={{
              marginBottom: "16px",
              background: "rgba(255, 80, 80, 0.15)",
              border: "1px solid rgba(255, 120, 120, 0.35)",
              color: "#ffd4d4",
              padding: "12px 16px",
              borderRadius: "12px",
            }}
          >
            {error}
          </div>
        )}

        <section
          style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr" : "minmax(320px, 390px) minmax(0, 1fr)",
            gap: "20px",
            alignItems: "start",
            marginBottom: "22px",
          }}
        >
          <div style={panelStyle}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "12px",
                marginBottom: "18px",
              }}
            >
              <h2 style={{ fontSize: "24px", fontWeight: 900, margin: 0 }}>價格分類</h2>
              <button
                type="button"
                onClick={toggleValidationPanel}
                style={{
                  border: "1px solid rgba(120, 205, 255, 0.28)",
                  borderRadius: "12px",
                  padding: "8px 12px",
                  background: showValidationPanel
                    ? "linear-gradient(180deg, rgba(106, 187, 255, 0.28) 0%, rgba(56, 116, 214, 0.38) 100%)"
                    : "rgba(255,255,255,0.05)",
                  color: "#e8f4ff",
                  fontWeight: 800,
                  fontSize: "13px",
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                {showValidationPanel ? "收起驗證" : "驗證紀錄"}
              </button>
            </div>

            {false && showValidationPanel && validationRecord && (
              <div
                style={{
                  marginBottom: "18px",
                  padding: "14px",
                  borderRadius: "16px",
                  background: "rgba(255,255,255,0.05)",
                  border: "1px solid rgba(130, 185, 255, 0.16)",
                }}
              >
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
                    gap: "12px",
                    marginBottom: "12px",
                  }}
                >
                  <div
                    style={{
                      borderRadius: "14px",
                      padding: "12px",
                      background: "rgba(20, 58, 112, 0.58)",
                    }}
                  >
                    <div style={{ color: "#8fc3ff", fontSize: "13px", fontWeight: 900, marginBottom: "8px" }}>
                      紀錄摘要
                    </div>
                    <div style={{ color: "#dce9ff", lineHeight: 1.8, fontSize: "13px", fontWeight: 700 }}>
                      <div>資料日期：{formatDateString(validationRecord!.dataDate)}</div>
                      <div>最後更新：{validationRecord!.lastUpdate || "-"}</div>
                      <div>本次推薦：{validationRecord!.recommendationCount} 檔</div>
                      <div>累積紀錄：{validationHistory.length} 次</div>
                    </div>
                  </div>

                  {strategyValidation && (
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "8px",
                        marginBottom: "14px",
                      }}
                    >
                      {[
                        getValidationBasisText(strategyValidation),
                        getReturnBasisText(strategyValidation.return_basis),
                        `驗證池 ${strategyValidation.validation_pool_size ?? "-"} 檔`,
                      ].map((text) => (
                        <span
                          key={text}
                          style={{
                            padding: "6px 10px",
                            borderRadius: "999px",
                            background: "rgba(255,255,255,0.06)",
                            border: "1px solid rgba(255,255,255,0.1)",
                            color: "#cfe3ff",
                            fontSize: "12px",
                            fontWeight: 800,
                          }}
                        >
                          {text}
                        </span>
                      ))}
                    </div>
                  )}

                  <div
                    style={{
                      borderRadius: "14px",
                      padding: "12px",
                      background: "rgba(20, 58, 112, 0.58)",
                    }}
                  >
                    <div style={{ color: "#8fc3ff", fontSize: "13px", fontWeight: 900, marginBottom: "8px" }}>
                      規則驗證
                    </div>
                    <div style={{ color: "#dce9ff", lineHeight: 1.8, fontSize: "13px", fontWeight: 700 }}>
                      <div>日 K 驗證：{validationRecord!.historicalKCount}/{validationRecord!.recommendationCount}</div>
                      <div>強勢評級：{validationRecord!.strongRatingCount}/{validationRecord!.recommendationCount}</div>
                      <div>平均分數：{validationRecord!.averageScore.toFixed(2)}</div>
                      <div>
                        平均風報比：
                        {validationRecord!.averageRiskReward > 0
                          ? ` 1:${validationRecord!.averageRiskReward.toFixed(2)}`
                          : " -"}
                      </div>
                    </div>
                  </div>
                </div>

                <div
                  style={{
                    paddingTop: "10px",
                    borderTop: "1px solid rgba(255,255,255,0.08)",
                    color: "#dce9ff",
                    fontSize: "12px",
                    fontWeight: 700,
                    lineHeight: 1.7,
                  }}
                >
                  <div style={{ marginBottom: "6px" }}>本次股票：</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "8px" }}>
                    {validationRecord!.stockLabels.map((label) => (
                      <span
                        key={label}
                        style={{
                          padding: "4px 8px",
                          borderRadius: "999px",
                          background: "rgba(255,255,255,0.06)",
                          border: "1px solid rgba(255,255,255,0.08)",
                          color: "#e8f2ff",
                          fontSize: "12px",
                          fontWeight: 700,
                        }}
                      >
                        {label}
                      </span>
                    ))}
                  </div>
                  <div>
                    前次重複：{previousValidationRecord ? `${repeatedPickCount} 檔` : "尚無前次紀錄"}
                  </div>
                  <div>主訊號：{validationRecord!.signalSummary.join(" / ") || "-"}</div>
                </div>

                <div
                  style={{
                    marginTop: "12px",
                    paddingTop: "12px",
                    borderTop: "1px solid rgba(255,255,255,0.08)",
                  }}
                >
                  <div
                    style={{
                      color: "#9cccf9",
                      fontSize: "12px",
                      fontWeight: 800,
                      marginBottom: "10px",
                    }}
                  >
                    個股紀錄明細
                  </div>

                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "10px",
                      maxHeight: "380px",
                      overflowY: "auto",
                      paddingRight: "4px",
                    }}
                  >
                    {validationRecord!.stocks.map((stock) => (
                      <div
                        key={`${stock.symbol}-${stock.signal}`}
                        style={{
                          borderRadius: "14px",
                          padding: "12px",
                          background: "rgba(20, 58, 112, 0.46)",
                          border: "1px solid rgba(255,255,255,0.08)",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            gap: "8px",
                            marginBottom: "8px",
                            flexWrap: "wrap",
                          }}
                        >
                          <div style={{ color: "#ffffff", fontWeight: 900, fontSize: "14px" }}>
                            {stock.symbol} {stock.name}
                          </div>
                          <div style={{ color: "#fff5b3", fontWeight: 900, fontSize: "13px" }}>
                            分數 {stock.recommendationScore.toFixed(2)}
                            {stock.bookSelectionScore > 0 ? ` / 代理 ${stock.bookSelectionScore.toFixed(1)}` : ""}
                          </div>
                        </div>

                        <div
                          style={{
                            display: "flex",
                            flexWrap: "wrap",
                            gap: "6px",
                            marginBottom: "8px",
                          }}
                        >
                          <span
                            style={{
                              padding: "4px 8px",
                              borderRadius: "999px",
                              background: "rgba(255,255,255,0.06)",
                              color: "#dce9ff",
                              fontSize: "12px",
                              fontWeight: 800,
                            }}
                          >
                            {stock.signal}
                          </span>
                          <span
                            style={{
                              padding: "4px 8px",
                              borderRadius: "999px",
                              background: "rgba(255,255,255,0.06)",
                              color: "#dce9ff",
                              fontSize: "12px",
                              fontWeight: 800,
                            }}
                          >
                            評級 {stock.operationRating}
                          </span>
                        </div>

                        <div
                          style={{
                            color: "#dce9ff",
                            fontSize: "12px",
                            lineHeight: 1.7,
                            fontWeight: 700,
                            marginBottom: "8px",
                          }}
                        >
                          {stock.reason}
                        </div>

                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
                            gap: "6px 10px",
                            color: "#cfe5ff",
                            fontSize: "12px",
                            fontWeight: 700,
                            lineHeight: 1.6,
                          }}
                        >
                          <div>進場：{stock.entryPrice}</div>
                          <div>目標：{stock.targetPrice}</div>
                          <div>停損：{stock.stopLoss}</div>
                          <div>風報比：{stock.riskReward}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div style={{ marginBottom: "20px" }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "12px" }}>
                {PRICE_CATEGORIES.map((item) => {
                  const active = selectedCategory === item.key;
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => {
                        setSelectedCategory(item.key);
                        setManualSelectedSymbol("");
                        setCurrentPage(1);
                      }}
                      style={{
                        minWidth: isMobile ? "calc(50% - 6px)" : "118px",
                        border: "none",
                        borderRadius: "14px",
                        padding: "14px 14px",
                        fontSize: "15px",
                        fontWeight: 800,
                        cursor: "pointer",
                        color: "#fff",
                        background: active
                          ? "linear-gradient(180deg, #61a8ff 0%, #3e7fe0 100%)"
                          : "linear-gradient(180deg, #2a67b8 0%, #1e4f93 100%)",
                        boxShadow: active ? "0 8px 22px rgba(80, 150, 255, 0.22)" : "none",
                      }}
                    >
                      {item.label} ({categoryCounts[item.key] || 0})
                    </button>
                  );
                })}
              </div>
            </div>

            <input
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setManualSelectedSymbol("");
              }}
              placeholder="搜尋股票代號 / 名稱"
              style={{
                width: "100%",
                height: "46px",
                borderRadius: "14px",
                border: "none",
                outline: "none",
                padding: "0 16px",
                fontSize: "15px",
                marginBottom: "18px",
                background: "#e8edf5",
                color: "#123",
              }}
            />

            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              {(["recommend", "up", "down"] as RankType[]).map((r) => {
                const labels = { recommend: "推薦", up: "漲幅", down: "跌幅" };
                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => {
                      setRankType(r);
                      setCurrentPage(1);
                    }}
                    style={rankType === r ? activeActionBtn : normalActionBtn}
                  >
                    {labels[r]}
                  </button>
                );
              })}
            </div>

            <div
              style={{
                marginTop: "18px",
                borderTop: "1px solid rgba(255,255,255,0.08)",
                paddingTop: "16px",
                color: "#d9e8ff",
                lineHeight: 1.8,
                fontSize: "14px",
              }}
            >
              <div style={{ fontWeight: 900, color: "#9fc3f6", marginBottom: "6px" }}>
                交易模式說明
              </div>
              <div>• 搜尋單一個股時，會自動顯示專業分析卡</div>
              <div>• 點擊推薦股或列表股，也可直接切換分析</div>
              <div>• A / B+ 偏強，C 觀察，D 保守控風險</div>
            </div>
          </div>

          <div style={recommendationPanelStyle}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "12px",
                marginBottom: showRecommendationsPanel ? "10px" : "0",
              }}
            >
              <h2 style={{ fontSize: "24px", fontWeight: 900, margin: 0 }}>🔥 推薦10檔</h2>
              <button
                type="button"
                onClick={toggleRecommendationsPanel}
                style={{
                  border: "1px solid rgba(120, 205, 255, 0.28)",
                  borderRadius: "12px",
                  padding: "8px 12px",
                  background: showRecommendationsPanel
                    ? "linear-gradient(180deg, rgba(106, 187, 255, 0.28) 0%, rgba(56, 116, 214, 0.38) 100%)"
                    : "rgba(255,255,255,0.05)",
                  color: "#e8f4ff",
                  fontWeight: 800,
                  fontSize: "13px",
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                {showRecommendationsPanel ? "收起" : "展開"}
              </button>
            </div>

            {showRecommendationsPanel && (
              <div
                style={{
                  maxHeight: isMobile ? "none" : "470px",
                  overflowY: isMobile ? "visible" : "auto",
                  paddingRight: isMobile ? "0" : "6px",
                }}
              >
              {recommendations.length === 0 ? (
                <div style={{ color: "#cfe2ff", padding: "16px 4px", fontWeight: 700 }}>
                  目前沒有可顯示的推薦資料
                </div>
              ) : (
                recommendations.map((stock) => {
                  const isUp = stock.change >= 0;
                  const changeColor = isUp ? "#ff4d4f" : "#00c853";
                  const isSelected = activeFocusedStock?.symbol === stock.symbol;

                  return (
                    <div
                      key={stock.symbol}
                      onClick={() => {
                        setManualSelectedSymbol(stock.symbol);
                        setSearchTerm(stock.symbol);
                        setFocusedStock(stockToFocused(stock));
                      }}
                      style={{
                        background: isSelected
                          ? "rgba(71, 126, 214, 0.48)"
                          : "rgba(40, 87, 150, 0.45)",
                        border: isSelected
                          ? "1px solid rgba(120, 180, 255, 0.52)"
                          : "1px solid rgba(86, 145, 228, 0.22)",
                        borderRadius: "18px",
                        padding: "16px 18px",
                        marginBottom: "12px",
                        cursor: "pointer",
                        boxShadow: isSelected
                          ? "0 0 0 1px rgba(120,180,255,0.25), 0 12px 24px rgba(0,0,0,0.18)"
                          : "none",
                        transition: "0.2s ease",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "flex-start",
                          gap: "12px",
                          marginBottom: "10px",
                          flexDirection: isMobile ? "column" : "row",
                        }}
                      >
                        <div style={{ width: "100%" }}>
                          <div
                            style={{
                              fontSize: isMobile ? "20px" : "22px",
                              fontWeight: 900,
                              marginBottom: "10px",
                              color: "#7fb6ff",
                            }}
                          >
                            {stock.symbol} {stock.name}
                          </div>

                          <div
                            style={{
                              display: "flex",
                              gap: "14px",
                              flexWrap: "wrap",
                              alignItems: "center",
                              marginBottom: "8px",
                            }}
                          >
                            <span
                              style={{
                                background: "rgba(255, 107, 107, 0.12)",
                                border: "1px solid rgba(255, 107, 107, 0.28)",
                                borderRadius: "999px",
                                padding: "5px 10px",
                                fontSize: "14px",
                                fontWeight: 700,
                                color: "#ff9c9c",
                              }}
                            >
                              {stock.signal || "強勢多方"}
                            </span>

                            {stock.operation_rating && (
                              <span
                                style={{
                                  background: "rgba(255,255,255,0.08)",
                                  borderRadius: "999px",
                                  padding: "5px 10px",
                                  fontSize: "14px",
                                  fontWeight: 800,
                                  color: getRatingColor(stock.operation_rating),
                                }}
                              >
                                評級 {stock.operation_rating}
                              </span>
                            )}

                            <span
                              style={{
                                background: "rgba(255,255,255,0.08)",
                                borderRadius: "999px",
                                padding: "5px 10px",
                                fontSize: "14px",
                                fontWeight: 800,
                                color: "#dbe8ff",
                              }}
                            >
                              {stock.market || "-"}
                            </span>

                            <span style={{ fontWeight: 700, color: "#dce9ff" }}>
                              股價 {formatPrice(stock.price)}
                            </span>
                            <span style={{ fontWeight: 900, color: changeColor }}>
                              漲跌 {formatSigned(stock.change)}
                            </span>
                            <span style={{ fontWeight: 900, color: changeColor }}>
                              漲跌% {formatSigned(stock.change_percent)}%
                            </span>
                          </div>
                        </div>

                        <div
                          style={{
                            color: "#ffd95f",
                            fontSize: "18px",
                            fontWeight: 900,
                            whiteSpace: "nowrap",
                          }}
                        >
                          推薦 {stock.recommendation_score || stock.score || 0}
                          {stock.book_selection_score ? ` / 代理 ${stock.book_selection_score.toFixed(1)}` : ""}
                        </div>
                      </div>

                      <div
                        style={{
                          color: "#dbe8ff",
                          lineHeight: 1.8,
                          fontSize: "15px",
                          marginBottom: "10px",
                        }}
                      >
                        {stock.reason || "價格維持強勢結構，買盤承接力道偏強，屬盤面表態標的。"}
                      </div>

                      <div
                        style={{
                          display: "flex",
                          gap: "16px",
                          flexWrap: "wrap",
                          alignItems: "center",
                          color: "#9fc3f6",
                          fontWeight: 800,
                          fontSize: "15px",
                        }}
                      >
                        <span>進場：{stock.entry_price || "-"}</span>
                        <span>目標：{stock.target_price || "-"}</span>
                        <span>停損：{stock.stop_loss || "-"}</span>
                        <span>風報比：{stock.risk_reward || "-"}</span>
                        {stock.book_selection_comment && <span>代理：{stock.book_selection_comment}</span>}
                      </div>
                    </div>
                  );
                })
              )}
              </div>
            )}

            {!showRecommendationsPanel &&
              showValidationPanel &&
              validationRecord &&
              validationHealth &&
              validationHistoryStats && (
                <div
                  style={{
                    marginTop: "12px",
                    borderRadius: "18px",
                    background: "rgba(20, 58, 112, 0.42)",
                    border: "1px solid rgba(255,255,255,0.08)",
                    padding: isMobile ? "14px" : "18px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      gap: "12px",
                      flexDirection: isMobile ? "column" : "row",
                      marginBottom: "16px",
                    }}
                  >
                    <div>
                      <div style={{ color: "#dff1ff", fontSize: "20px", fontWeight: 900, marginBottom: "6px" }}>
                        邏輯驗證總覽
                      </div>
                      <div style={{ color: "#9cccf9", fontSize: "13px", lineHeight: 1.7, fontWeight: 700 }}>
                        先看今天結構，再比較「歷史K同訊號/同評級 + 代理分預篩」後的 5 / 10 / 20 日命中率，避免快照分和歷史分混在一起。
                      </div>
                    </div>

                    <div
                      style={{
                        padding: "8px 12px",
                        borderRadius: "999px",
                        background: validationHealth.surface,
                        color: validationHealth.accent,
                        fontWeight: 900,
                        fontSize: "13px",
                        border: `1px solid ${validationHealth.accent}33`,
                        whiteSpace: "nowrap",
                      }}
                    >
                      今日結構一致性 {validationHealth.score}/100
                    </div>
                  </div>

                  <div
                    style={{
                      borderRadius: "16px",
                      padding: isMobile ? "14px" : "16px",
                      background: historicalValidationTone?.surface || validationHealth.surface,
                      border: `1px solid ${(historicalValidationTone?.accent || validationHealth.accent)}33`,
                      marginBottom: "16px",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "flex-start",
                          gap: "12px",
                          flexDirection: isMobile ? "column" : "row",
                          marginBottom: "14px",
                        }}
                      >
                        <div>
                          <div style={{ color: "#8fc3ff", fontSize: "12px", fontWeight: 900, marginBottom: "6px" }}>
                            目前狀態
                          </div>
                          <div style={{ color: validationQuickState?.accent || "#dff1ff", fontSize: "24px", fontWeight: 900, marginBottom: "6px" }}>
                            {validationQuickState?.label || "先觀察"}
                          </div>
                          <div style={{ color: "#e6f0ff", fontSize: "13px", lineHeight: 1.8, fontWeight: 700 }}>
                            {validationQuickState?.detail || combinedValidationSummary?.summary || "目前尚無可整合的驗證摘要。"}
                          </div>
                        </div>

                        <div
                          style={{
                            minWidth: isMobile ? "100%" : "260px",
                            padding: "12px 14px",
                            borderRadius: "14px",
                            background: validationQuickState?.surface || "rgba(255,255,255,0.08)",
                            border: `1px solid ${(validationQuickState?.accent || historicalValidationTone?.accent || validationHealth.accent)}33`,
                          }}
                        >
                          <div style={{ color: "#8fc3ff", fontSize: "12px", fontWeight: 900, marginBottom: "6px" }}>
                            核心結論
                          </div>
                          <div
                            style={{
                              color: validationQuickState?.accent || historicalValidationTone?.accent || validationHealth.accent,
                              fontWeight: 900,
                              fontSize: "18px",
                              marginBottom: "4px",
                            }}
                          >
                            {strategyValidation?.full_period?.verdict || strategyValidation?.verdict || validationHealth.label}
                          </div>
                          <div style={{ color: "#cfe3ff", fontSize: "12px", lineHeight: 1.7, fontWeight: 700 }}>
                            {combinedValidationSummary?.summary || "目前尚無摘要。"}
                          </div>
                        </div>
                      </div>

                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: isMobile ? "repeat(2, minmax(0,1fr))" : "repeat(4, minmax(0,1fr))",
                          gap: "10px",
                          marginBottom: "12px",
                        }}
                      >
                      {validationPeriodCards.map((metric) => (
                        <div
                          key={metric.key}
                          style={{
                            borderRadius: "14px",
                            padding: "12px",
                            background: metric.surface,
                            border: `1px solid ${metric.border}`,
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              gap: "8px",
                              marginBottom: "8px",
                            }}
                          >
                            <div style={{ color: "#dff1ff", fontSize: "12px", fontWeight: 900 }}>{metric.label}</div>
                            <div
                              style={{
                                padding: "4px 8px",
                                borderRadius: "999px",
                                fontSize: "11px",
                                fontWeight: 900,
                                color: metric.accent,
                                background: "rgba(255,255,255,0.08)",
                                border: `1px solid ${metric.border}`,
                                whiteSpace: "nowrap",
                              }}
                            >
                              {metric.status}
                            </div>
                          </div>
                          <div style={{ color: "#ffffff", fontSize: "24px", fontWeight: 900, marginBottom: "8px" }}>
                            {metric.score}
                          </div>
                          {metric.metrics.map((item, itemIndex) => (
                            <div
                              key={`${metric.key}-${itemIndex}`}
                              style={{
                                color: itemIndex === 0 ? "#cfe3ff" : "#9fc7f5",
                                fontSize: "12px",
                                lineHeight: 1.65,
                                fontWeight: 700,
                                marginTop: itemIndex === 0 ? 0 : "4px",
                              }}
                            >
                              {item}
                            </div>
                          ))}
                          {metric.note && (
                            <div
                              style={{
                                color: "#8fb8e8",
                                fontSize: "11px",
                                lineHeight: 1.55,
                                fontWeight: 700,
                                marginTop: "8px",
                              }}
                            >
                              {metric.note}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>

                    <div
                      style={{
                        borderRadius: "14px",
                        padding: "10px 12px",
                        background: "rgba(255,255,255,0.04)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        display: "grid",
                        gap: "8px",
                      }}
                    >
                      <div style={{ color: "#8fc3ff", fontSize: "12px", fontWeight: 900 }}>
                        重點提醒
                      </div>
                      <div style={{ color: "#dce9ff", fontSize: "13px", lineHeight: 1.7, fontWeight: 700 }}>
                        {combinedValidationSummary?.risk || "目前沒有額外提醒。"}
                      </div>
                      <div style={{ color: "#b9d7ff", fontSize: "12px", lineHeight: 1.7, fontWeight: 700 }}>
                        今日主訊號：{validationRecord.signalSummary.join(" / ") || "-"}
                        {strategyValidation
                          ? ` / 強訊號：${strategyValidation.strongest_signal || "-"} / 弱訊號：${
                              strategyValidation.weakest_signal || "-"
                            }`
                          : ""}
                      </div>
                      {strategyValidation && (
                        <div style={{ color: "#9fc7f5", fontSize: "12px", lineHeight: 1.7, fontWeight: 700 }}>
                          驗證方法：{getValidationBasisText(strategyValidation)}；報酬口徑：
                          {getReturnBasisText(strategyValidation.return_basis)}
                        </div>
                      )}
                    </div>
                  </div>

                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: "12px",
                      flexDirection: isMobile ? "column" : "row",
                      marginBottom: showValidationDetails ? "12px" : "0",
                    }}
                  >
                    <div style={{ color: "#b9d7ff", fontSize: "13px", lineHeight: 1.7, fontWeight: 700 }}>
                      今日樣本：{validationSamplePreview}
                    </div>

                    <button
                      onClick={() => setShowValidationDetails((prev) => !prev)}
                      style={{
                        border: "1px solid rgba(255,255,255,0.12)",
                        background: "rgba(255,255,255,0.06)",
                        color: "#eaf4ff",
                        borderRadius: "999px",
                        padding: "8px 14px",
                        fontWeight: 900,
                        fontSize: "12px",
                        cursor: "pointer",
                      }}
                    >
                      {showValidationDetails ? "收起今日樣本" : "展開今日樣本"}
                    </button>
                  </div>

                  {showValidationDetails && (
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "12px",
                        maxHeight: isMobile ? "none" : "560px",
                        overflowY: isMobile ? "visible" : "auto",
                        paddingRight: isMobile ? "0" : "4px",
                      }}
                    >
                      {validationRecord.stocks.map((stock) => (
                        <div
                          key={`${stock.symbol}-${stock.signal}`}
                          style={{
                            borderRadius: "16px",
                            padding: "14px 16px",
                            background: "rgba(255,255,255,0.04)",
                            border: "1px solid rgba(255,255,255,0.08)",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              gap: "10px",
                              flexWrap: "wrap",
                              marginBottom: "8px",
                            }}
                          >
                            <div style={{ color: "#ffffff", fontSize: "18px", fontWeight: 900 }}>
                              {stock.symbol} {stock.name}
                            </div>
                            <div style={{ color: "#fff5b3", fontWeight: 900, fontSize: "14px" }}>
                              分數 {stock.recommendationScore.toFixed(2)}
                              {stock.bookSelectionScore > 0 ? ` / 代理 ${stock.bookSelectionScore.toFixed(1)}` : ""}
                            </div>
                          </div>

                          <div
                            style={{
                              display: "flex",
                              flexWrap: "wrap",
                              gap: "8px",
                              marginBottom: "10px",
                            }}
                          >
                            <span
                              style={{
                                padding: "4px 9px",
                                borderRadius: "999px",
                                background: "rgba(255,255,255,0.06)",
                                color: "#dce9ff",
                                fontSize: "12px",
                                fontWeight: 800,
                              }}
                            >
                              {stock.signal}
                            </span>
                            <span
                              style={{
                                padding: "4px 9px",
                                borderRadius: "999px",
                                background: "rgba(255,255,255,0.06)",
                                color: "#dce9ff",
                                fontSize: "12px",
                                fontWeight: 800,
                              }}
                            >
                              評級 {stock.operationRating}
                            </span>
                          </div>

                          <div
                            style={{
                              color: "#dce9ff",
                              fontSize: "13px",
                              lineHeight: 1.8,
                              fontWeight: 700,
                              marginBottom: "10px",
                            }}
                          >
                            {stock.reason}
                          </div>

                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns: isMobile ? "1fr" : "repeat(4, minmax(0,1fr))",
                              gap: "8px",
                              color: "#cfe5ff",
                              fontSize: "12px",
                              fontWeight: 700,
                              lineHeight: 1.6,
                            }}
                          >
                            <div>進場：{stock.entryPrice}</div>
                            <div>目標：{stock.targetPrice}</div>
                            <div>停損：{stock.stopLoss}</div>
                            <div>風報比：{stock.riskReward}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
          </div>
        </section>

        {activeFocusedStock && (
          <section
            style={{
              marginBottom: "22px",
              background: "linear-gradient(180deg, #102f63 0%, #0c2955 100%)",
              border: "1px solid rgba(100,160,255,0.25)",
              borderRadius: "22px",
              padding: isMobile ? "18px" : "24px",
              boxShadow: "0 10px 28px rgba(0,0,0,0.12)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: isMobile ? "flex-start" : "center",
                gap: "12px",
                flexDirection: isMobile ? "column" : "row",
                marginBottom: "14px",
              }}
            >
              <div>
                <h2 style={{ fontSize: "24px", fontWeight: 900, margin: 0, marginBottom: "8px" }}>
                  📊 個股專業分析
                </h2>
                <div style={{ fontSize: isMobile ? "22px" : "26px", fontWeight: 900, color: "#7fb6ff" }}>
                  {activeFocusedStock.symbol} {activeFocusedStock.name}
                </div>
              </div>

              <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
                <span style={analysisTagStyle}>{activeFocusedStock.market}</span>
                <span style={analysisTagStyle}>{activeFocusedStock.signal}</span>
                <span style={analysisTagStyle}>{activeFocusedStock.trend_type}</span>
                <span
                  style={{
                    ...analysisTagStyle,
                    color: getRatingColor(activeFocusedStock.operation_rating),
                    borderColor: "rgba(255,255,255,0.16)",
                  }}
                >
                  評級 {activeFocusedStock.operation_rating}
                </span>
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "1fr" : "repeat(4, minmax(0,1fr))",
                gap: "12px",
                marginBottom: "16px",
              }}
            >
              <div style={metricCardStyle}>
                <div style={metricLabelStyle}>現價</div>
                <div style={metricValueStyle}>{formatPrice(activeFocusedStock.price)}</div>
              </div>
              <div style={metricCardStyle}>
                <div style={metricLabelStyle}>漲跌</div>
                <div
                  style={{
                    ...metricValueStyle,
                    color: activeFocusedStock.change >= 0 ? "#ff8b8b" : "#57e389",
                  }}
                >
                  {formatSigned(activeFocusedStock.change)}
                </div>
              </div>
              <div style={metricCardStyle}>
                <div style={metricLabelStyle}>漲跌%</div>
                <div
                  style={{
                    ...metricValueStyle,
                    color: activeFocusedStock.change_percent >= 0 ? "#ff8b8b" : "#57e389",
                  }}
                >
                  {formatSigned(activeFocusedStock.change_percent)}%
                </div>
              </div>
              <div style={metricCardStyle}>
                <div style={metricLabelStyle}>成交量</div>
                <div style={metricValueStyle}>{formatNumber(activeFocusedStock.volume)}</div>
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
                gap: "14px",
                marginBottom: "14px",
              }}
            >
              <div style={analysisBlockStyle}>
                <div style={analysisBlockTitleStyle}>操作方向</div>
                <div style={analysisBlockTextStyle}>
                  {activeFocusedStock.operation_bias} ｜ {activeFocusedStock.operation_style}
                </div>
              </div>
              <div style={analysisBlockStyle}>
                <div style={analysisBlockTitleStyle}>更新時間</div>
                <div style={analysisBlockTextStyle}>{activeFocusedStock.update_time || "-"}</div>
              </div>
            </div>

            <div style={analysisBlockStyle}>
              <div style={analysisBlockTitleStyle}>技術分析</div>
              <div style={analysisBlockTextStyle}>{activeFocusedStock.technical_comment}</div>
            </div>

            <div style={analysisBlockStyle}>
              <div style={analysisBlockTitleStyle}>分析結論</div>
              <div style={analysisBlockTextStyle}>{activeFocusedStock.analysis}</div>
            </div>

            <div style={analysisBlockStyle}>
              <div style={analysisBlockTitleStyle}>操作戰略</div>
              <div style={analysisBlockTextStyle}>{activeFocusedStock.strategy_action}</div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "1fr" : "repeat(4, minmax(0,1fr))",
                gap: "12px",
                marginTop: "16px",
              }}
            >
              {[
                { label: "建議進場", value: activeFocusedStock.entry_price },
                { label: "目標價", value: activeFocusedStock.target_price },
                { label: "停損價", value: activeFocusedStock.stop_loss },
                { label: "風報比", value: activeFocusedStock.risk_reward },
              ].map(({ label, value }) => (
                <div key={label} style={tradePlanCardStyle}>
                  <div style={tradePlanLabelStyle}>{label}</div>
                  <div style={tradePlanValueStyle}>{value || "-"}</div>
                </div>
              ))}
            </div>

            <div
              style={{
                marginTop: "16px",
                padding: "14px 16px",
                borderRadius: "16px",
                background: "rgba(255, 92, 92, 0.08)",
                border: "1px solid rgba(255, 120, 120, 0.18)",
                color: "#ffb4b4",
                lineHeight: 1.8,
                fontWeight: 700,
              }}
            >
              ⚠️ 風險提醒：{activeFocusedStock.risk_note || "-"}
            </div>
          </section>
        )}

        <section
          style={{
            background: "linear-gradient(180deg, #0d2f63 0%, #0a2a57 100%)",
            border: "1px solid rgba(80, 140, 220, 0.22)",
            borderRadius: "22px",
            padding: isMobile ? "16px" : "20px",
            boxShadow: "0 10px 28px rgba(0,0,0,0.12)",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: isMobile ? "flex-start" : "center",
              gap: "12px",
              marginBottom: "16px",
              flexDirection: isMobile ? "column" : "row",
            }}
          >
            <h2 style={{ fontSize: "22px", fontWeight: 900, margin: 0 }}>
              股票列表 ({total})
            </h2>
            <div style={{ color: "#cfe2ff", fontSize: "14px", fontWeight: 700 }}>
              第 {currentPage} / {totalPages} 頁，每頁 {ITEMS_PER_PAGE} 檔
            </div>
          </div>

          <div style={{ overflowX: "auto", borderRadius: "18px" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                tableLayout: "fixed",
              }}
            >
              <thead>
                <tr style={{ background: "linear-gradient(180deg, #3570bd 0%, #285d9f 100%)" }}>
                  <th style={thStyle}>市場</th>
                  <th style={thStyle}>代號</th>
                  <th style={{ ...thStyle, textAlign: "left" }}>名稱</th>
                  <th style={thStyle}>股價</th>
                  <th style={thStyle}>漲跌</th>
                  <th style={thStyle}>漲跌%</th>
                  <th style={thStyle}>成交量</th>
                  <th style={thStyle}>訊號</th>
                  <th style={thStyle}>評級</th>
                  <th style={thStyle}>分數</th>
                  <th style={thStyle}>風報比</th>
                </tr>
              </thead>

              <tbody>
                {stocks.map((stock) => {
                  const isUp = stock.change >= 0;
                  const color = isUp ? "#ff4d4f" : "#00c853";
                  const isSelected = activeFocusedStock?.symbol === stock.symbol;

                  return (
                    <tr
                      key={stock.symbol}
                      onClick={() => {
                        setManualSelectedSymbol(stock.symbol);
                        setSearchTerm(stock.symbol);
                        setFocusedStock(stockToFocused(stock));
                      }}
                      style={{
                        height: "46px",
                        borderBottom: "1px solid rgba(255,255,255,0.06)",
                        background: isSelected
                          ? "rgba(22, 71, 134, 0.88)"
                          : "rgba(8, 36, 76, 0.55)",
                        cursor: "pointer",
                        transition: "0.18s ease",
                      }}
                    >
                      <td style={tdStyle}>{stock.market || "-"}</td>

                      <td style={tdStyle}>
                        <span
                          style={{
                            fontSize: "13px",
                            fontWeight: 900,
                            color: "#7fb6ff",
                          }}
                        >
                          {stock.symbol}
                        </span>
                      </td>

                      <td
                        style={{
                          ...tdStyle,
                          textAlign: "left",
                          overflow: "hidden",
                        }}
                        title={stock.name}
                      >
                        <span
                          style={{
                            display: "block",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            fontWeight: 700,
                          }}
                        >
                          {stock.name}
                        </span>
                      </td>

                      <td style={tdStyle}>
                        <span style={{ fontWeight: 900 }}>{formatPrice(stock.price)}</span>
                      </td>

                      <td style={tdStyle}>
                        <span style={{ color, fontWeight: 900 }}>
                          {formatSigned(stock.change)}
                        </span>
                      </td>

                      <td style={tdStyle}>
                        <span style={{ color, fontWeight: 800 }}>
                          {formatSigned(stock.change_percent)}%
                        </span>
                      </td>

                      <td style={tdStyle}>{formatNumber(stock.volume)}</td>

                      <td style={tdStyle}>
                        <span
                          style={{
                            display: "inline-block",
                            maxWidth: "100%",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            background: "rgba(255,255,255,0.08)",
                            padding: "3px 6px",
                            borderRadius: "999px",
                            fontSize: "10px",
                            fontWeight: 800,
                          }}
                          title={stock.signal || "-"}
                        >
                          {stock.signal || "-"}
                        </span>
                      </td>

                      <td
                        style={{
                          ...tdStyle,
                          color: getRatingColor(stock.operation_rating),
                          fontWeight: 900,
                        }}
                      >
                        {stock.operation_rating || "-"}
                      </td>

                      <td style={tdStyle}>{stock.recommendation_score || stock.score || 0}</td>

                      <td style={tdStyle}>{stock.risk_reward || "-"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div
              style={{
                marginTop: "18px",
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                gap: "8px",
                flexWrap: "wrap",
              }}
            >
              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                style={{
                  ...pageBtnStyle,
                  opacity: currentPage === 1 ? 0.45 : 1,
                  cursor: currentPage === 1 ? "not-allowed" : "pointer",
                }}
              >
                上一頁
              </button>

              {pageNumbers.map((page, idx) => {
                if (page < 0) {
                  return (
                    <span
                      key={`ellipsis-${idx}`}
                      style={{ color: "#d9e7ff", padding: "0 4px", fontWeight: 800 }}
                    >
                      ...
                    </span>
                  );
                }
                const active = currentPage === page;
                return (
                  <button
                    key={page}
                    type="button"
                    onClick={() => setCurrentPage(page)}
                    style={{
                      ...pageBtnStyle,
                      background: active
                        ? "linear-gradient(180deg, #61a8ff 0%, #3e7fe0 100%)"
                        : "#184889",
                      boxShadow: active ? "0 8px 22px rgba(80, 150, 255, 0.22)" : "none",
                    }}
                  >
                    {page}
                  </button>
                );
              })}

              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                style={{
                  ...pageBtnStyle,
                  opacity: currentPage === totalPages ? 0.45 : 1,
                  cursor: currentPage === totalPages ? "not-allowed" : "pointer",
                }}
              >
                下一頁
              </button>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

const activeActionBtn: React.CSSProperties = {
  border: "none",
  borderRadius: "14px",
  padding: "12px 16px",
  fontSize: "15px",
  fontWeight: 800,
  cursor: "pointer",
  color: "#fff",
  background: "linear-gradient(180deg, #61a8ff 0%, #3e7fe0 100%)",
};

const normalActionBtn: React.CSSProperties = {
  border: "none",
  borderRadius: "14px",
  padding: "12px 16px",
  fontSize: "15px",
  fontWeight: 800,
  cursor: "pointer",
  color: "#fff",
  background: "#184889",
};

const pageBtnStyle: React.CSSProperties = {
  border: "none",
  borderRadius: "12px",
  padding: "10px 14px",
  minWidth: "44px",
  fontSize: "14px",
  fontWeight: 800,
  color: "#fff",
  background: "#184889",
};

const thStyle: React.CSSProperties = {
  padding: "8px 6px",
  textAlign: "center",
  color: "#ffffff",
  fontSize: "12px",
  fontWeight: 800,
  whiteSpace: "nowrap",
  lineHeight: 1.1,
};

const tdStyle: React.CSSProperties = {
  padding: "6px 6px",
  textAlign: "center",
  color: "#ffffff",
  fontSize: "12px",
  fontWeight: 700,
  verticalAlign: "middle",
  lineHeight: 1,
};

const analysisTagStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.08)",
  border: "1px solid rgba(255,255,255,0.1)",
  padding: "6px 10px",
  borderRadius: "999px",
  fontWeight: 800,
  color: "#dbe8ff",
  fontSize: "14px",
};

const metricCardStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: "16px",
  padding: "14px 16px",
};

const metricLabelStyle: React.CSSProperties = {
  color: "#9fc3f6",
  fontSize: "13px",
  fontWeight: 700,
  marginBottom: "8px",
};

const metricValueStyle: React.CSSProperties = {
  color: "#ffffff",
  fontSize: "22px",
  fontWeight: 900,
};

const analysisBlockStyle: React.CSSProperties = {
  marginTop: "12px",
  padding: "14px 16px",
  borderRadius: "16px",
  background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.08)",
};

const analysisBlockTitleStyle: React.CSSProperties = {
  color: "#7fb6ff",
  fontSize: "15px",
  fontWeight: 900,
  marginBottom: "8px",
};

const analysisBlockTextStyle: React.CSSProperties = {
  color: "#dbe8ff",
  lineHeight: 1.85,
  fontSize: "15px",
  fontWeight: 700,
};

const tradePlanCardStyle: React.CSSProperties = {
  background: "linear-gradient(180deg, rgba(45,95,170,0.55) 0%, rgba(22,58,107,0.55) 100%)",
  border: "1px solid rgba(108,162,255,0.16)",
  borderRadius: "16px",
  padding: "14px 16px",
};

const tradePlanLabelStyle: React.CSSProperties = {
  color: "#9fc3f6",
  fontSize: "13px",
  fontWeight: 700,
  marginBottom: "8px",
};

const tradePlanValueStyle: React.CSSProperties = {
  color: "#ffffff",
  fontSize: "16px",
  fontWeight: 900,
  lineHeight: 1.6,
};

