function formatNumber(num) {
    if (num === null || num === undefined || num === "-") return "-";
    if (isNaN(num)) return num;
    return Number(num).toLocaleString("en-US");
}
function isMarketTime() {
    const now = new Date();
    const day = now.getDay();
    const hour = now.getHours();
    const minute = now.getMinutes();
    const isWeekday = day >= 1 && day <= 5;
    const afterOpen = hour > 8 || (hour === 8 && minute >= 30);
    const beforeClose = hour < 16 || (hour === 16 && minute <= 30);
    return isWeekday && afterOpen && beforeClose;
}
async function fetchClosingPrice(stockCode, isCommon) {
    try {
        const resp = await fetch(`data/trends/${stockCode}.json`);
        const data = await resp.json();
        if (isCommon && data.common_prices && data.common_prices.length > 0)
            return data.common_prices[data.common_prices.length - 1];
        if (!isCommon && data.preferred_prices && data.preferred_prices.length > 0)
            return data.preferred_prices[data.preferred_prices.length - 1];
        return "-";
    } catch {
        return "-";
    }
}
async function fetchRealtimePrice(stockCode) {
    try {
        const resp = await fetch('data/realtime_prices.json');
        const data = await resp.json();
        if (data && data[stockCode]) return data[stockCode];
        return "-";
    } catch {
        return "-";
    }
}
async function getCurrentOrClosingPrice(stockCode, isCommon) {
    if (isMarketTime()) {
        return await fetchRealtimePrice(stockCode);
    } else {
        return await fetchClosingPrice(stockCode, isCommon);
    }
}
function getFeeRate(commission_bps, stamp_bps) {
    // 커미션+스탬프 합산 bps → %
    return (Number(commission_bps) + Number(stamp_bps)) / 10000;
}
function getInterestRate(benchmark_rate_pct, floating_spread_bps) {
    // Benchmark(KWCDC) + 스프레드(bps) → %
    const base = Number(benchmark_rate_pct) || 0;
    const spread = Number(floating_spread_bps) / 100 || 0;
    return base + spread;
}
function calcDays(entryDate, exitDate) {
    if (!entryDate) return "-";
    const start = new Date(entryDate);
    const end = exitDate ? new Date(exitDate) : new Date();
    const diffDays = Math.floor((end - start) / (1000 * 60 * 60 * 24)) + 1;
    return diffDays > 0 ? diffDays : "-";
}
// 보통주(숏) - 차입수수료율: common_borrow_rate가 있으면 그 값, 없으면 benchmark+spread
function calcShortPnL(entry, exit, qty, feeRate, borrowRate, days) {
    if (!entry || !exit || !qty || entry === "-" || exit === "-")
        return { pnl: 0, pnlStr: "-", ret: "-" };
    const entryAmt = entry * qty;
    const exitAmt = exit * qty;
    const commission = (entryAmt + exitAmt) * feeRate;
    const borrowFee = entryAmt * (borrowRate / 100) * (days / 365);
    const pnl = entryAmt - exitAmt - commission - borrowFee;
    const ret = entryAmt !== 0 ? (pnl / entryAmt * 100).toFixed(2) + "%" : "-";
    return { pnl, pnlStr: formatNumber(Math.round(pnl)), ret };
}
// 우선주(롱)
function calcLongPnL(entry, exit, qty, feeRate, interestRate, days) {
    if (!entry || !exit || !qty || entry === "-" || exit === "-")
        return { pnl: 0, pnlStr: "-", ret: "-" };
    const entryAmt = entry * qty;
    const exitAmt = exit * qty;
    const commission = (entryAmt + exitAmt) * feeRate;
    const interest = entryAmt * (interestRate / 100) * (days / 365);
    const pnl = exitAmt - entryAmt - commission - interest;
    const ret = entryAmt !== 0 ? (pnl / entryAmt * 100).toFixed(2) + "%" : "-";
    return { pnl, pnlStr: formatNumber(Math.round(pnl)), ret };
}
async function fetchPairs() {
    const resp = await fetch('data/pair-trades.json');
    return await resp.json();
}
async function renderTable() {
    const pairs = await fetchPairs();
    const tbody = document.getElementById("pairTableBody");
    tbody.innerHTML = "";
    for (const entry of pairs) {
        let cNow = "-", pNow = "-";
        let days = calcDays(entry.entry_date, entry.exit_date);
        let daysNum = days === "-" ? 0 : Number(days);
        if (entry.status === "보유중") {
            cNow = await getCurrentOrClosingPrice(entry.common_code, true);
            pNow = await getCurrentOrClosingPrice(entry.preferred_code, false);
        } else {
            cNow = entry.common_exit !== null && entry.common_exit !== undefined ? entry.common_exit : "-";
            pNow = entry.preferred_exit !== null && entry.preferred_exit !== undefined ? entry.preferred_exit : "-";
        }
        const feeRate = getFeeRate(entry.commission_bps, entry.stamp_bps);
        // ★ 보통주(숏): common_borrow_rate 있으면 그 값, 없으면 benchmark+spread
        const common_borrow_rate =
            entry.common_borrow_rate !== undefined && entry.common_borrow_rate !== null
                ? entry.common_borrow_rate
                : getInterestRate(entry.benchmark_rate_pct, entry.common_floating_spread_bps);
        const preferred_interest_rate = getInterestRate(entry.benchmark_rate_pct, entry.preferred_floating_spread_bps);
        const short = calcShortPnL(entry.common_entry, cNow, entry.common_qty, feeRate, common_borrow_rate, daysNum);
        const long = calcLongPnL(entry.preferred_entry, pNow, entry.preferred_qty, feeRate, preferred_interest_rate, daysNum);
        const pairProfit = (typeof short.pnl === "number" ? short.pnl : 0) + (typeof long.pnl === "number" ? long.pnl : 0);
        const pairEntry = (entry.common_entry && entry.common_qty ? entry.common_entry * entry.common_qty : 0) +
            (entry.preferred_entry && entry.preferred_qty ? entry.preferred_entry * entry.preferred_qty : 0);
        const pairReturn = pairEntry !== 0 ? (pairProfit / pairEntry * 100).toFixed(2) + "%" : "-";
        const pairProfitStr = formatNumber(Math.round(pairProfit));
        const pairProfitClass = pairProfit > 0 ? "positive" : (pairProfit < 0 ? "negative" : "");
        const pairRetClass = pairReturn !== "-" && parseFloat(pairReturn) > 0 ? "positive" : (pairReturn !== "-" && parseFloat(pairReturn) < 0 ? "negative" : "");
        tbody.innerHTML += `
<tr class="main-row">
  <td>${entry.pair_name}</td>
  <td class="${pairProfitClass}">${pairProfitStr}</td>
  <td class="${pairRetClass}">${pairReturn}</td>
  <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
</tr>
<tr class="sub-row">
  <td></td>
  <td></td>
  <td></td>
  <td>보통주(Short)</td>
  <td>${entry.entry_date || "-"}</td>
  <td>${entry.exit_date || "-"}</td>
  <td>${formatNumber(entry.common_entry)}</td>
  <td>${formatNumber(entry.common_qty)}</td>
  <td>${formatNumber(cNow)}</td>
  <td class="${short.pnl > 0 ? 'positive' : (short.pnl < 0 ? 'negative' : '')}">${short.pnlStr}</td>
  <td class="${short.ret !== '-' && parseFloat(short.ret) > 0 ? 'positive' : (short.ret !== '-' && parseFloat(short.ret) < 0 ? 'negative' : '')}">${short.ret}</td>
  <td>${entry.status}</td>
</tr>
<tr class="sub-row">
  <td></td>
  <td></td>
  <td></td>
  <td>우선주(Long)</td>
  <td>${entry.entry_date || "-"}</td>
  <td>${entry.exit_date || "-"}</td>
  <td>${formatNumber(entry.preferred_entry)}</td>
  <td>${formatNumber(entry.preferred_qty)}</td>
  <td>${formatNumber(pNow)}</td>
  <td class="${long.pnl > 0 ? 'positive' : (long.pnl < 0 ? 'negative' : '')}">${long.pnlStr}</td>
  <td class="${long.ret !== '-' && parseFloat(long.ret) > 0 ? 'positive' : (long.ret !== '-' && parseFloat(long.ret) < 0 ? 'negative' : '')}">${long.ret}</td>
  <td>${entry.status}</td>
</tr>
`;
    }
}
window.addEventListener("DOMContentLoaded", renderTable);
