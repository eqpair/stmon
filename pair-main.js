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

// 각 포지션별 수익/수익률 계산
function calcPositionProfitAndReturn(type, entry, exit, qty, feeRate, interestRate, days) {
    if (!entry || !exit || !qty) return { profit: "-", ret: "-" };
    let profit = 0;
    if (type === "Short") {
        // 보통주(숏): 진입가 > 청산가/현재가 → 수익
        const interest = calcInterest(entry, interestRate, days) * qty;
        profit = (entry * (1 - feeRate) - exit * (1 + feeRate) - interest) * qty;
        const ret = entry !== 0 ? (profit / (entry * qty) * 100).toFixed(2) + "%" : "-";
        return { profit: formatNumber(Math.round(profit)), ret };
    } else {
        // 우선주(롱): 진입가 < 청산가/현재가 → 수익
        const interest = calcInterest(entry, interestRate, days) * qty;
        profit = (exit * (1 - feeRate) - entry * (1 + feeRate) - interest) * qty;
        const ret = entry !== 0 ? (profit / (entry * qty) * 100).toFixed(2) + "%" : "-";
        return { profit: formatNumber(Math.round(profit)), ret };
    }
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
        let cNow = "-", pNow = "-";
        let days = calcDays(entry.entry_date, entry.exit_date);
        let daysNum = days === "-" ? 0 : Number(days);

        // 현재가/종가
        if (entry.status === "보유중") {
            cNow = await getCurrentOrClosingPrice(entry.common_code, true);
            pNow = await getCurrentOrClosingPrice(entry.preferred_code, false);
        } else {
            cNow = entry.common_exit;
            pNow = entry.preferred_exit;
        }

        // 보통주(Short) 계산
        const feeRate = getFeeRate(entry.commission_bps, entry.stamp_bps);
        const common_interest_rate = getInterestRate(entry.benchmark_rate_pct, entry.common_floating_spread_bps);
        const short = calcPositionProfitAndReturn(
            "Short",
            entry.common_entry,
            cNow,
            entry.common_qty,
            feeRate,
            common_interest_rate,
            daysNum
        );

        // 우선주(Long) 계산
        const preferred_interest_rate = getInterestRate(entry.benchmark_rate_pct, entry.preferred_floating_spread_bps);
        const long = calcPositionProfitAndReturn(
            "Long",
            entry.preferred_entry,
            pNow,
            entry.preferred_qty,
            feeRate,
            preferred_interest_rate,
            daysNum
        );

        // 상태별 스타일
        let rowClass = entry.status === "청산" ? "closed" : "open";
        const shortClass = (short.profit !== "-" && parseFloat(short.profit.replace(/,/g, "")) < 0) ? "negative" : "positive";
        const shortRetClass = (short.ret !== "-" && parseFloat(short.ret) < 0) ? "negative" : "positive";
        const longClass = (long.profit !== "-" && parseFloat(long.profit.replace(/,/g, "")) < 0) ? "negative" : "positive";
        const longRetClass = (long.ret !== "-" && parseFloat(long.ret) < 0) ? "negative" : "positive";

        // 페어명 헤더
        tbody.innerHTML += `
      <tr class="pair-header"><td colspan="10">${entry.pair_name}</td></tr>
      <tr class="${rowClass}">
        <td data-label="구분">보통주<br>(Short)</td>
        <td data-label="종목명">${entry.common_name}</td>
        <td data-label="진입일">${entry.entry_date}</td>
        <td data-label="청산일">${entry.exit_date || "-"}</td>
        <td data-label="진입가">${formatNumber(entry.common_entry)}</td>
        <td data-label="수량">${formatNumber(entry.common_qty)}</td>
        <td data-label="청산가/현재가">${formatNumber(cNow) || "-"}</td>
        <td data-label="수익" class="${shortClass}">${short.profit}</td>
        <td data-label="수익률" class="${shortRetClass}">${short.ret}</td>
        <td data-label="상태">${entry.status}</td>
      </tr>
      <tr class="${rowClass}">
        <td data-label="구분">우선주<br>(Long)</td>
        <td data-label="종목명">${entry.preferred_name}</td>
        <td data-label="진입일">${entry.entry_date}</td>
        <td data-label="청산일">${entry.exit_date || "-"}</td>
        <td data-label="진입가">${formatNumber(entry.preferred_entry)}</td>
        <td data-label="수량">${formatNumber(entry.preferred_qty)}</td>
        <td data-label="청산가/현재가">${formatNumber(pNow) || "-"}</td>
        <td data-label="수익" class="${longClass}">${long.profit}</td>
        <td data-label="수익률" class="${longRetClass}">${long.ret}</td>
        <td data-label="상태">${entry.status}</td>
      </tr>
    `;
    }
}

renderTable();
setInterval(renderTable, 30000);
