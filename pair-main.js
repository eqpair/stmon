function formatNumber(num) {
    if (num === null || num === undefined || num === "-") return "-";
    if (isNaN(num)) return num;
    return Number(num).toLocaleString("en-US");
}

// 진입~청산일 계산
function calcDays(entryDate, exitDate) {
    if (!entryDate) return "-";
    const start = new Date(entryDate);
    const end = exitDate ? new Date(exitDate) : new Date();
    const diffDays = Math.floor((end - start) / (1000 * 60 * 60 * 24)) + 1;
    return diffDays > 0 ? diffDays : "-";
}

// Settlement Ticket 기준 산식
function calcShortPnL(entry, exit, qty, floatingRate, spread, days) {
    if (!entry || !exit || !qty || entry === "-" || exit === "-") return { pnl: 0, pnlStr: "-", ret: "-" };
    const entryAmt = entry * qty;
    const exitAmt = exit * qty;
    const borrowRate = Number(floatingRate) + (Number(spread) || 0);
    const borrowFee = entryAmt * (borrowRate / 100) * (days / 365);
    const equityPnL = entryAmt - exitAmt;
    const pnl = equityPnL - borrowFee;
    const ret = entryAmt !== 0 ? (pnl / entryAmt * 100).toFixed(2) + "%" : "-";
    return { pnl, pnlStr: formatNumber(Math.round(pnl)), ret };
}

function calcLongPnL(entry, exit, qty, floatingRate, spread, days) {
    if (!entry || !exit || !qty || entry === "-" || exit === "-") return { pnl: 0, pnlStr: "-", ret: "-" };
    const entryAmt = entry * qty;
    const exitAmt = exit * qty;
    const lendRate = Number(floatingRate) + (Number(spread) || 0);
    const lendFee = entryAmt * (lendRate / 100) * (days / 365);
    const equityPnL = exitAmt - entryAmt;
    const pnl = equityPnL - lendFee;
    const ret = entryAmt !== 0 ? (pnl / entryAmt * 100).toFixed(2) + "%" : "-";
    return { pnl, pnlStr: formatNumber(Math.round(pnl)), ret };
}

// 데이터 로딩 (첨부하신 pair-trades.json 구조 반영)
async function fetchPairs() {
    const resp = await fetch('data/pair-trades.json');
    return await resp.json();
}

// 테이블 렌더링
async function renderTable() {
    const pairs = await fetchPairs();
    const tbody = document.getElementById("pairTableBody");
    tbody.innerHTML = "";
    let alt = 0;
    for (const entry of pairs) {
        let cNow = "-", pNow = "-";
        let days = calcDays(entry.entry_date, entry.exit_date);
        let daysNum = days === "-" ? 0 : Number(days);
        let status = entry.status;
        if (status === "Open") {
            cNow = entry.common_entry;
            pNow = entry.preferred_entry;
        } else {
            cNow = entry.common_exit !== null && entry.common_exit !== undefined ? entry.common_exit : "-";
            pNow = entry.preferred_exit !== null && entry.preferred_exit !== undefined ? entry.preferred_exit : "-";
        }
        const short = calcShortPnL(
            entry.common_entry, cNow, entry.common_qty,
            entry.benchmark_rate_pct, entry.common_floating_spread_bps / 100, daysNum
        );
        const long = calcLongPnL(
            entry.preferred_entry, pNow, entry.preferred_qty,
            entry.benchmark_rate_pct, entry.preferred_floating_spread_bps / 100, daysNum
        );
        const pairProfit = (typeof short.pnl === "number" ? short.pnl : 0) + (typeof long.pnl === "number" ? long.pnl : 0);
        const pairEntry = (entry.common_entry && entry.common_qty ? entry.common_entry * entry.common_qty : 0) + (entry.preferred_entry && entry.preferred_qty ? entry.preferred_entry * entry.preferred_qty : 0);
        const pairReturn = pairEntry !== 0 ? (pairProfit / pairEntry * 100).toFixed(2) + "%" : "-";
        const pairProfitStr = formatNumber(Math.round(pairProfit));
        const pairProfitClass = pairProfit > 0 ? "positive" : (pairProfit < 0 ? "negative" : "");
        const pairRetClass = pairReturn !== "-" && parseFloat(pairReturn) > 0 ? "positive" : (pairReturn !== "-" && parseFloat(pairReturn) < 0 ? "negative" : "");

        let daysInfo = "";
        if (entry.exit_date && entry.entry_date) {
            const days = calcDays(entry.entry_date, entry.exit_date);
            daysInfo = `(${days}일)`;
        }

        const pairName = entry.pair_name;
        // 테이블에 3행(Short/Long/합산) 출력
        tbody.innerHTML += `
      <tr class="main-row pair-bg-${alt % 10}">
        <td rowspan="3">${pairName}</td>
        <td rowspan="3" class="${pairProfitClass}">${pairProfitStr}</td>
        <td rowspan="3" class="${pairRetClass}">${pairReturn}</td>
        <td>보통주(Short)</td>
        <td>${entry.entry_date}</td>
        <td>${formatNumber(entry.common_entry)}</td>
        <td>${formatNumber(entry.common_qty)}</td>
        <td>${formatNumber(cNow)}</td>
        <td class="${short.pnl < 0 ? "negative" : "positive"}">${short.pnlStr}</td>
        <td class="${short.ret.includes('-') ? "negative" : "positive"}">${short.ret}</td>
        <td>${entry.exit_date ? entry.exit_date + daysInfo : "-"}</td>
        <td>${status}</td>
      </tr>
      <tr class="sub-row bold">
        <td>우선주(Long)</td>
        <td>${entry.entry_date}</td>
        <td>${formatNumber(entry.preferred_entry)}</td>
        <td>${formatNumber(entry.preferred_qty)}</td>
        <td>${formatNumber(pNow)}</td>
        <td class="${long.pnl < 0 ? "negative" : "positive"}">${long.pnlStr}</td>
        <td class="${long.ret.includes('-') ? "negative" : "positive"}">${long.ret}</td>
        <td>${entry.exit_date ? entry.exit_date + daysInfo : "-"}</td>
        <td>${status}</td>
      </tr>
      <tr class="sub-row">
        <td colspan="6" style="text-align:right;">합산</td>
        <td class="${pairProfitClass}">${pairProfitStr}</td>
        <td class="${pairRetClass}">${pairReturn}</td>
        <td colspan="2"></td>
      </tr>
    `;
        alt++;
    }
}
