function formatNumber(num) {
    if (num === null || num === undefined || num === "-") return "-";
    if (isNaN(num)) return num;
    return Number(num).toLocaleString("en-US");
}

// 시장 운영 시간(평일 8:30~16:30, KST) 판정
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

// trend_collector가 저장한 종가(마감가) 가져오기
async function fetchClosingPrice(stockCode, isCommon) {
    try {
        const resp = await fetch(`data/trends/${stockCode}.json`);
        const data = await resp.json();
        if (isCommon && data.common_prices && data.common_prices.length > 0)
            return data.common_prices[data.common_prices.length - 1];
        if (!isCommon && data.preferred_prices && data.preferred_prices.length > 0)
            return data.preferred_prices[data.preferred_prices.length - 1];
        return null;
    } catch {
        return null;
    }
}

// 실시간가(네이버 API)
async function fetchPrice(stockCode) {
    const url = `https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:${stockCode}`;
    try {
        const resp = await fetch(url);
        const data = await resp.json();
        return data.result.areas[0].datas[0].nv;
    } catch {
        return null;
    }
}

// 시장 중이면 실시간가, 마감이면 종가(마감가)
async function getCurrentOrClosingPrice(stockCode, isCommon) {
    if (isMarketTime()) {
        return await fetchPrice(stockCode);
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
function calcInterest(principal, rate_pct, days) {
    if (!principal || !rate_pct || !days) return 0;
    return principal * (rate_pct / 100) * (days / 365);
}

// 수익(원)과 수익률(%) 동시 계산
function calcPairProfitAndReturn(entry, cPrice, pPrice, days) {
    const feeRate = getFeeRate(entry.commission_bps, entry.stamp_bps);
    const common_interest_rate = getInterestRate(entry.benchmark_rate_pct, entry.common_floating_spread_bps);
    const preferred_interest_rate = getInterestRate(entry.benchmark_rate_pct, entry.preferred_floating_spread_bps);

    // 진입/청산가에 수수료, 이자 모두 반영
    let common_exit = entry.status === "청산" ? entry.common_exit : cPrice;
    let preferred_exit = entry.status === "청산" ? entry.preferred_exit : pPrice;

    if (!common_exit || !preferred_exit) return { profit: "-", ret: "-" };

    // 보통주(숏) 수익
    const short_interest = calcInterest(entry.common_entry, common_interest_rate, days) * entry.common_qty;
    const short_profit = (entry.common_entry * (1 - feeRate) - common_exit * (1 + feeRate) - short_interest) * entry.common_qty;

    // 우선주(롱) 수익
    const long_interest = calcInterest(entry.preferred_entry, preferred_interest_rate, days) * entry.preferred_qty;
    const long_profit = (preferred_exit * (1 - feeRate) - entry.preferred_entry * (1 + feeRate) - long_interest) * entry.preferred_qty;

    const total_profit = short_profit + long_profit;

    // 진입 총액 (절대값 합산)
    const total_entry = entry.common_entry * entry.common_qty + entry.preferred_entry * entry.preferred_qty;
    const ret = total_entry !== 0 ? (total_profit / total_entry * 100).toFixed(2) + "%" : "-";

    return { profit: formatNumber(Math.round(total_profit)), ret };
}

async function fetchPairs() {
    const resp = await fetch('data/pair-trades.json');
    return await resp.json();
}

async function renderTable() {
    const pairs = await fetchPairs();
    const tbody = document.querySelector("#pair-table tbody");
    tbody.innerHTML = "";

    for (const entry of pairs) {
        let cNow = "-", pNow = "-", pairRet = "-", pairProfit = "-";
        let rowClass = entry.status === "청산" ? "closed" : "open";
        let days = calcDays(entry.entry_date, entry.exit_date);
        let daysNum = days === "-" ? 0 : Number(days);

        if (entry.status === "보유중") {
            cNow = await getCurrentOrClosingPrice(entry.common_code, true);
            pNow = await getCurrentOrClosingPrice(entry.preferred_code, false);
            const { profit, ret } = calcPairProfitAndReturn(entry, cNow, pNow, daysNum);
            pairProfit = profit;
            pairRet = ret;
        } else {
            cNow = entry.common_exit;
            pNow = entry.preferred_exit;
            const { profit, ret } = calcPairProfitAndReturn(entry, cNow, pNow, daysNum);
            pairProfit = profit;
            pairRet = ret;
        }
        const retClass = (pairRet !== "-" && parseFloat(pairRet) < 0) ? "negative" : "positive";
        const profitClass = (pairProfit !== "-" && parseFloat(pairProfit.replace(/,/g, "")) < 0) ? "negative" : "positive";
        tbody.innerHTML += `
      <tr class="${rowClass}">
        <td data-label="페어">${entry.pair_name}</td>
        <td data-label="진입일">${entry.entry_date}</td>
        <td data-label="청산일">${entry.exit_date || "-"}</td>
        <td data-label="진행일수">${days}</td>
        <td data-label="진입가">${formatNumber(entry.common_entry)} / ${formatNumber(entry.preferred_entry)}</td>
        <td data-label="수량">${formatNumber(entry.common_qty)} / ${formatNumber(entry.preferred_qty)}</td>
        <td data-label="청산가/현재가">${formatNumber(cNow) || "-"} / ${formatNumber(pNow) || "-"}</td>
        <td data-label="수익" class="${profitClass}">${pairProfit}</td>
        <td data-label="수익률" class="${retClass}">${pairRet}</td>
        <td data-label="상태">${entry.status}</td>
      </tr>
    `;
    }
}

renderTable();
setInterval(renderTable, 30000);
