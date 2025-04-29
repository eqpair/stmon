function formatNumber(num) {
    if (num == null || isNaN(num)) return "-";
    return Math.round(num).toLocaleString("en-US");
}

// 날짜 차이 계산(일수)
function calcDays(entryDate, exitDate) {
    if (!entryDate) return "-";
    const start = new Date(entryDate);
    const end = exitDate ? new Date(exitDate) : new Date();
    return Math.max(1, Math.floor((end - start) / (1000 * 60 * 60 * 24)) + 1);
}

// 숏: (진입가 - 현재가) * 수량 (이자 차감)
function calcShortPnL(entry, exit, qty, rate = 0, spread = 0, days = 1) {
    if (!entry || !exit || !qty || entry === "-" || exit === "-") return { pnl: 0, pnlStr: "-", ret: "-" };
    const entryAmt = entry * qty;
    const exitAmt = exit * qty;
    const borrowRate = Number(rate) + (Number(spread) || 0);
    const borrowFee = entryAmt * (borrowRate / 100) * (days / 365);
    const pnl = entryAmt - exitAmt - borrowFee;
    const ret = entryAmt !== 0 ? (pnl / entryAmt * 100).toFixed(2) + "%" : "-";
    return { pnl, pnlStr: formatNumber(pnl), ret };
}

// 롱: (현재가 - 진입가) * 수량 (이자 차감)
function calcLongPnL(entry, exit, qty, rate = 0, spread = 0, days = 1) {
    if (!entry || !exit || !qty || entry === "-" || exit === "-") return { pnl: 0, pnlStr: "-", ret: "-" };
    const entryAmt = entry * qty;
    const exitAmt = exit * qty;
    const lendRate = Number(rate) + (Number(spread) || 0);
    const lendFee = entryAmt * (lendRate / 100) * (days / 365);
    const pnl = exitAmt - entryAmt - lendFee;
    const ret = entryAmt !== 0 ? (pnl / entryAmt * 100).toFixed(2) + "%" : "-";
    return { pnl, pnlStr: formatNumber(pnl), ret };
}

// --- 데이터 불러오기 ---
async function fetchPairs() {
    const resp = await fetch('data/pair-trades.json');
    return await resp.json();
}

// 현재가/청산가 구하기 (진짜 데이터라면 여기에 현시세 API로 교체)
function getCurrentOrExitPrice(entry, isCommon) {
    // 실제 서비스에선 여기서 실시간/종가 API를 불러야 함
    // 지금은 pair-trades.json에서 주는 값만 사용
    return isCommon ? entry.common_exit ?? "-" : entry.preferred_exit ?? "-";
}

// 테이블 렌더링
async function renderTable() {
    const pairs = await fetchPairs();
    const tbody = document.getElementById("pairTableBody");
    tbody.innerHTML = "";
    let alt = 0;

    for (const entry of pairs) {
        const daysNum = calcDays(entry.entry_date, entry.exit_date);

        // 현재가/청산가
        const cNow = entry.status === "보유중"
            ? entry.common_entry // 실제 배포용: 실시간 시세 불러오세요!
            : entry.common_exit ?? "-";
        const pNow = entry.status === "보유중"
            ? entry.preferred_entry // 실제 배포용: 실시간 시세 불러오세요!
            : entry.preferred_exit ?? "-";

        // 반드시! 보통주는 Short, 우선주는 Long
        const short = calcShortPnL(
            entry.common_entry, cNow, entry.common_qty,
            entry.benchmark_rate_pct, entry.common_floating_spread_bps, daysNum
        );
        const long = calcLongPnL(
            entry.preferred_entry, pNow, entry.preferred_qty,
            entry.benchmark_rate_pct, entry.preferred_floating_spread_bps, daysNum
        );

        // 합산: 실제 포지션별 수익 합쳐서
        const pairProfit = short.pnl + long.pnl;
        const pairEntry = (entry.common_entry * entry.common_qty) + (entry.preferred_entry * entry.preferred_qty);
        const pairReturn = pairEntry !== 0 ? (pairProfit / pairEntry * 100).toFixed(2) + "%" : "-";
        const pairProfitStr = formatNumber(pairProfit);

        // 표 2줄: 보통주(Short) / 우선주(Long)
        tbody.innerHTML += `
      <tr class="main-row">
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
        alt++;
    }
}
window.onload = renderTable;
