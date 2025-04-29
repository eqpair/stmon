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
function getFloatingRate(benchmark_rate_pct, floating_spread_bps) {
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
function calcShortRate(entry, exit) {
    if (!entry || !exit || entry === "-" || exit === "-") return "-";
    return (((entry - exit) / entry) * 100).toFixed(2) + "%";
}
function calcLongRate(entry, exit) {
    if (!entry || !exit || entry === "-" || exit === "-") return "-";
    return (((exit - entry) / entry) * 100).toFixed(2) + "%";
}
function calcShortPnL(entry, exit, entryQty, exitQty, feeRate, borrowRate, days) {
    if (!entry || !exit || !entryQty || !exitQty || entry === "-" || exit === "-")
        return { pnl: 0, pnlStr: "-", ret: "-" };
    const entryAmt = entry * entryQty;
    const exitAmt = exit * exitQty;
    const commission = (entryAmt + exitAmt) * feeRate;
    const borrowFee = entryAmt * (borrowRate / 100) * (days / 365);
    const pnl = entryAmt - exitAmt - commission - borrowFee;
    return { pnl, pnlStr: formatNumber(Math.round(pnl)) };
}
function calcLongPnL(entry, exit, entryQty, exitQty, feeRate, interestRate, days) {
    if (!entry || !exit || !entryQty || !exitQty || entry === "-" || exit === "-")
        return { pnl: 0, pnlStr: "-", ret: "-" };
    const entryAmt = entry * entryQty;
    const exitAmt = exit * exitQty;
    const commission = (entryAmt + exitAmt) * feeRate;
    const interest = entryAmt * (interestRate / 100) * (days / 365);
    const pnl = exitAmt - entryAmt - commission - interest;
    return { pnl, pnlStr: formatNumber(Math.round(pnl)) };
}
function getFeeRate(commission_bps, stamp_bps) {
    return (Number(commission_bps) + Number(stamp_bps)) / 10000;
}
async function fetchPairs() {
    const resp = await fetch('data/pair-trades.json');
    return await resp.json();
}
async function renderTable() {
    const pairs = await fetchPairs();
    const tbody = document.getElementById("pairTableBody");
    tbody.innerHTML = "";
    let alt = 0;
    for (const entry of pairs) {
        let cNow = "-", pNow = "-";
        let cExitQty = entry.common_exit_qty !== undefined ? entry.common_exit_qty : entry.common_qty;
        let pExitQty = entry.preferred_exit_qty !== undefined ? entry.preferred_exit_qty : entry.preferred_qty;
        let days = calcDays(entry.entry_date, entry.exit_date);
        let daysNum = days === "-" ? 0 : Number(days);
        if (entry.status === "보유중") {
            cNow = await getCurrentOrClosingPrice(entry.common_code, true);
            pNow = await getCurrentOrClosingPrice(entry.preferred_code, false);
            cExitQty = entry.common_qty;
            pExitQty = entry.preferred_qty;
        } else {
            cNow = entry.common_exit !== null && entry.common_exit !== undefined ? entry.common_exit : "-";
            pNow = entry.preferred_exit !== null && entry.preferred_exit !== undefined ? entry.preferred_exit : "-";
        }
        const feeRate = getFeeRate(entry.commission_bps, entry.stamp_bps);
        const short = calcShortPnL(
            entry.common_entry, cNow, entry.common_qty, cExitQty,
            feeRate,
            getFloatingRate(entry.benchmark_rate_pct, entry.common_floating_spread_bps),
            daysNum
        );
        const long = calcLongPnL(
            entry.preferred_entry, pNow, entry.preferred_qty, pExitQty,
            feeRate,
            getFloatingRate(entry.benchmark_rate_pct, entry.preferred_floating_spread_bps),
            daysNum
        );
        const pairProfit = (typeof short.pnl === "number" ? short.pnl : 0) + (typeof long.pnl === "number" ? long.pnl : 0);
        const pairEntry = (entry.common_entry && entry.common_qty ? entry.common_entry * entry.common_qty : 0) +
            (entry.preferred_entry && entry.preferred_qty ? entry.preferred_entry * entry.preferred_qty : 0);
        const pairReturn = pairEntry !== 0 ? (pairProfit / pairEntry * 100).toFixed(2) + "%" : "-";
        const pairProfitClass = pairProfit > 0 ? "positive" : (pairProfit < 0 ? "negative" : "");
        const pairRetClass = pairReturn !== "-" && parseFloat(pairReturn) > 0 ? "positive" : (parseFloat(pairReturn) < 0 ? "negative" : "");
        // 진입가 대비 종료가 기준 수익률
        const shortRate = calcShortRate(entry.common_entry, cNow);
        const longRate = calcLongRate(entry.preferred_entry, pNow);
        let shortRateClass = "", longRateClass = "";
        if (shortRate !== "-" && !isNaN(parseFloat(shortRate))) {
            shortRateClass = parseFloat(shortRate) > 0 ? "positive" : (parseFloat(shortRate) < 0 ? "negative" : "");
        }
        if (longRate !== "-" && !isNaN(parseFloat(longRate))) {
            longRateClass = parseFloat(longRate) > 0 ? "positive" : (parseFloat(longRate) < 0 ? "negative" : "");
        }
        // 청산일이 있으면 소요일수 줄바꿈, 숫자만
        let daysInfo = "";
        if (entry.exit_date && entry.entry_date) {
            const days = calcDays(entry.entry_date, entry.exit_date);
            daysInfo = `<span class="days-block">${days}</span>`;
        }
        const pairBgClass = `pair-bg-${alt % 4}`;
        tbody.innerHTML += `
<tr class="main-row ${pairBgClass}">
  <td rowspan="2">${entry.pair_name}</td>
  <td rowspan="2" class="${pairProfitClass}">${formatNumber(Math.round(pairProfit))}</td>
  <td rowspan="2" class="${pairRetClass}">${pairReturn}</td>
  <td>보통주(Short)</td>
  <td>${entry.entry_date || "-"}</td>
  <td>${formatNumber(entry.common_entry)}</td>
  <td>${formatNumber(entry.common_qty)}</td>
  <td>${formatNumber(cNow)}</td>
  <td>${formatNumber(cExitQty)}</td>
  <td class="${short.pnl > 0 ? 'positive' : (short.pnl < 0 ? 'negative' : '')}">${short.pnlStr}</td>
  <td class="${shortRateClass}">${shortRate}</td>
  <td rowspan="2">${entry.exit_date || "-"}${daysInfo}</td>
  <td rowspan="2">${entry.status}</td>
</tr>
<tr class="sub-row ${pairBgClass}">
  <td>우선주(Long)</td>
  <td>${entry.entry_date || "-"}</td>
  <td>${formatNumber(entry.preferred_entry)}</td>
  <td>${formatNumber(entry.preferred_qty)}</td>
  <td>${formatNumber(pNow)}</td>
  <td>${formatNumber(pExitQty)}</td>
  <td class="${long.pnl > 0 ? 'positive' : (long.pnl < 0 ? 'negative' : '')}">${long.pnlStr}</td>
  <td class="${longRateClass}">${longRate}</td>
</tr>
`;
        alt++;
    }
}
window.addEventListener("DOMContentLoaded", renderTable);
