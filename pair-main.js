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
    return (Number(commission_bps) + Number(stamp_bps)) / 10000;
}
function getInterestRate(benchmark_rate_pct, floating_spread_bps) {
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
function calcInterest(entryAmt, rate_pct, days) {
    if (!entryAmt || !rate_pct || !days) return 0;
    return entryAmt * (rate_pct / 100) * (days / 365);
}
function calcShortPnL(entry, exit, qty, feeRate, interestRate, days) {
    if (!entry || !exit || !qty || entry === "-" || exit === "-")
        return { pnl: 0, pnlStr: "-", ret: "-" };
    const entryAmt = entry * qty;
    const exitAmt = exit * qty;
    const entryFee = entryAmt * feeRate;
    const exitFee = exitAmt * feeRate;
    const interest = calcInterest(entryAmt, interestRate, days);
    const pnl = (entryAmt - entryFee) - (exitAmt + exitFee) - interest;
    const ret = entryAmt !== 0 ? (pnl / entryAmt * 100).toFixed(2) + "%" : "-";
    return { pnl, pnlStr: formatNumber(Math.round(pnl)), ret };
}
function calcLongPnL(entry, exit, qty, feeRate, interestRate, days) {
    if (!entry || !exit || !qty || entry === "-" || exit === "-")
        return { pnl: 0, pnlStr: "-", ret: "-" };
    const entryAmt = entry * qty;
    const exitAmt = exit * qty;
    const entryFee = entryAmt * feeRate;
    const exitFee = exitAmt * feeRate;
    const interest = calcInterest(entryAmt, interestRate, days);
    const pnl = (exitAmt - exitFee) - (entryAmt + entryFee) - interest;
    const ret = entryAmt !== 0 ? (pnl / entryAmt * 100).toFixed(2) + "%" : "-";
    return { pnl, pnlStr: formatNumber(Math.round(pnl)), ret };
}
async function fetchPairs() {
    const resp = await fetch('data/pair-trades.json');
    return await resp.json();
}
async function renderPairCards() {
    const pairs = await fetchPairs();
    const pairList = document.getElementById("pairList");
    pairList.innerHTML = "";
    let totalProfit = 0, totalEntry = 0, openCount = 0;
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
        const common_interest_rate = getInterestRate(entry.benchmark_rate_pct, entry.common_floating_spread_bps);
        const preferred_interest_rate = getInterestRate(entry.benchmark_rate_pct, entry.preferred_floating_spread_bps);
        const short = calcShortPnL(
            entry.common_entry, cNow, entry.common_qty, feeRate, common_interest_rate, daysNum
        );
        const long = calcLongPnL(
            entry.preferred_entry, pNow, entry.preferred_qty, feeRate, preferred_interest_rate, daysNum
        );
        const pairProfit = (typeof short.pnl === "number" ? short.pnl : 0) + (typeof long.pnl === "number" ? long.pnl : 0);
        const pairEntry = (entry.common_entry && entry.common_qty ? entry.common_entry * entry.common_qty : 0) +
            (entry.preferred_entry && entry.preferred_qty ? entry.preferred_entry * entry.preferred_qty : 0);
        const pairReturn = pairEntry !== 0 ? (pairProfit / pairEntry * 100).toFixed(2) + "%" : "-";
        const pairProfitStr = formatNumber(Math.round(pairProfit));
        // 수익이면 빨간색, 손실이면 파란색
        const pairProfitClass = pairProfit > 0 ? "positive" : (pairProfit < 0 ? "negative" : "");
        const pairRetClass = pairReturn !== "-" && parseFloat(pairReturn) > 0 ? "positive" : (pairReturn !== "-" && parseFloat(pairReturn) < 0 ? "negative" : "");
        let rowClass = entry.status === "청산" ? "closed pair-card" : "open pair-card";
        const shortClass = (short.pnlStr !== "-" && parseFloat(short.pnlStr.replace(/,/g, "")) > 0) ? "positive" : ((short.pnlStr !== "-" && parseFloat(short.pnlStr.replace(/,/g, "")) < 0) ? "negative" : "");
        const shortRetClass = (short.ret !== "-" && parseFloat(short.ret) > 0) ? "positive" : ((short.ret !== "-" && parseFloat(short.ret) < 0) ? "negative" : "");
        const longClass = (long.pnlStr !== "-" && parseFloat(long.pnlStr.replace(/,/g, "")) > 0) ? "positive" : ((long.pnlStr !== "-" && parseFloat(long.pnlStr.replace(/,/g, "")) < 0) ? "negative" : "");
        const longRetClass = (long.ret !== "-" && parseFloat(long.ret) > 0) ? "positive" : ((long.ret !== "-" && parseFloat(long.ret) < 0) ? "negative" : "");
        if (entry.status === "보유중") openCount++;
        totalProfit += pairProfit;
        totalEntry += pairEntry;
        const card = document.createElement("div");
        card.className = rowClass;
        card.innerHTML = `
      <div class="pair-header">
        <span class="pair-name">${entry.pair_name}</span>
        <span class="pair-status">${entry.status}</span>
      </div>
      <div class="pair-body">
        <div>합산수익: <span class="${pairProfitClass}">${pairProfitStr}</span></div>
        <div>합산수익률: <span class="${pairRetClass}">${pairReturn}</span></div>
        <div>진입일: ${entry.entry_date || "-"}</div>
        <div>청산일: ${entry.exit_date || "-"}</div>
        <div>보통주(Short): 진입 ${formatNumber(entry.common_entry)}, 현재/청산 ${formatNumber(cNow)}, 수익 <span class="${shortClass}">${short.pnlStr}</span>, 수익률 <span class="${shortRetClass}">${short.ret}</span></div>
        <div>우선주(Long): 진입 ${formatNumber(entry.preferred_entry)}, 현재/청산 ${formatNumber(pNow)}, 수익 <span class="${longClass}">${long.pnlStr}</span>, 수익률 <span class="${longRetClass}">${long.ret}</span></div>
      </div>
    `;
        pairList.appendChild(card);
    }
    document.getElementById("totalProfit").textContent = formatNumber(Math.round(totalProfit));
    document.getElementById("totalReturn").textContent = totalEntry !== 0 ? (totalProfit / totalEntry * 100).toFixed(2) + "%" : "-";
    document.getElementById("openPairs").textContent = openCount;
}
window.addEventListener("DOMContentLoaded", renderPairCards);
