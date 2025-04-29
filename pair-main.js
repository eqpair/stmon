function formatNumber(num) {
    if (num == null || isNaN(num)) return "-";
    return Math.round(num).toLocaleString("en-US");
}

// Short
function calcShortPnL(entry, exit, qty, floatingRate, spread, days) {
    if (!entry || !exit || !qty || entry === "-" || exit === "-") return { pnl: 0, pnlStr: "-", ret: "-" };
    const entryAmt = entry * qty;
    const exitAmt = exit * qty;
    const borrowRate = Number(floatingRate) + (Number(spread) || 0);
    const borrowFee = entryAmt * (borrowRate / 100) * (days / 365);
    const pnl = entryAmt - exitAmt - borrowFee;
    const ret = entryAmt !== 0 ? (pnl / entryAmt * 100).toFixed(2) + "%" : "-"; // 진입총액 기준
    return { pnl, pnlStr: formatNumber(pnl), ret };
}

// Long
function calcLongPnL(entry, exit, qty, floatingRate, spread, days) {
    if (!entry || !exit || !qty || entry === "-" || exit === "-") return { pnl: 0, pnlStr: "-", ret: "-" };
    const entryAmt = entry * qty;
    const exitAmt = exit * qty;
    const lendRate = Number(floatingRate) + (Number(spread) || 0);
    const lendFee = entryAmt * (lendRate / 100) * (days / 365);
    const pnl = exitAmt - entryAmt - lendFee;
    const ret = entryAmt !== 0 ? (pnl / entryAmt * 100).toFixed(2) + "%" : "-";
    return { pnl, pnlStr: formatNumber(pnl), ret };
}

// 나머지 함수는 동일

async function renderTable() {
    const pairs = await fetchPairs();
    const tbody = document.getElementById("pairTableBody");
    tbody.innerHTML = "";
    for (const entry of pairs) {
        // 진입가/청산가/수량 등 데이터에서 확인
        const daysNum = calcDays(entry.entry_date, entry.exit_date);
        const cNow = entry.status === "보유중"
            ? entry.common_entry // 실거래라면 실시간 시세로 교체 필요
            : entry.common_exit ?? "-";
        const pNow = entry.status === "보유중"
            ? entry.preferred_entry
            : entry.preferred_exit ?? "-";
        // 보통주(Short)
        const short = calcShortPnL(
            entry.common_entry, cNow, entry.common_qty,
            entry.benchmark_rate_pct, entry.common_floating_spread_bps, daysNum
        );
        // 우선주(Long)
        const long = calcLongPnL(
            entry.preferred_entry, pNow, entry.preferred_qty,
            entry.benchmark_rate_pct, entry.preferred_floating_spread_bps, daysNum
        );
        // 합산
        const pairProfit = short.pnl + long.pnl;
        const pairEntry = (entry.common_entry * entry.common_qty) + (entry.preferred_entry * entry.preferred_qty);
        const pairReturn = pairEntry !== 0 ? (pairProfit / pairEntry * 100).toFixed(2) + "%" : "-";
        const pairProfitStr = formatNumber(pairProfit);

        tbody.innerHTML += `
      <tr>
        <td rowspan="2">${entry.pair_name}</td>
        <td rowspan="2">${pairProfitStr}</td>
        <td rowspan="2">${pairReturn}</td>
        <td>보통주(Short)</td>
        <td>${entry.entry_date || "-"}</td>
        <td>${formatNumber(entry.common_entry)}</td>
        <td>${formatNumber(entry.common_qty)}</td>
        <td>${formatNumber(cNow)}</td>
        <td>${short.pnlStr}</td>
        <td>${short.ret}</td>
        <td rowspan="2">${entry.exit_date ? entry.exit_date + `(${daysNum}일)` : "-"}</td>
        <td rowspan="2">${entry.status}</td>
      </tr>
      <tr>
        <td>우선주(Long)</td>
        <td>${entry.entry_date || "-"}</td>
        <td>${formatNumber(entry.preferred_entry)}</td>
        <td>${formatNumber(entry.preferred_qty)}</td>
        <td>${formatNumber(pNow)}</td>
        <td>${long.pnlStr}</td>
        <td>${long.ret}</td>
      </tr>
    `;
    }
}
window.onload = renderTable;
