// pair-main.js

// "Open" 상태 페어의 trend 마감가를 가져와서 평가손익까지 계산하는 함수

async function fetchOpenPairsWithPrices() {
    // 1. pair-trades.json에서 Open 페어만 추출
    const tradesRes = await fetch('data/pair-trades.json');
    const trades = await tradesRes.json();
    const openPairs = trades.filter(pair => pair.status === 'Open');

    // 2. 각 페어별로 trend 파일에서 최신 가격(마감가) fetch
    const results = [];
    for (const pair of openPairs) {
        // trend 파일에서 보통주/우선주 마감가 읽기
        let commonClose = null, preferredClose = null;
        try {
            const commonTrendRes = await fetch(`data/trends/${pair.common_code}.json`);
            const commonTrend = await commonTrendRes.json();
            if (commonTrend.common_prices && commonTrend.common_prices.length > 0)
                commonClose = commonTrend.common_prices[commonTrend.common_prices.length - 1];
        } catch { }
        try {
            const preferredTrendRes = await fetch(`data/trends/${pair.preferred_code}.json`);
            const preferredTrend = await preferredTrendRes.json();
            if (preferredTrend.preferred_prices && preferredTrend.preferred_prices.length > 0)
                preferredClose = preferredTrend.preferred_prices[preferredTrend.preferred_prices.length - 1];
        } catch { }
        results.push({
            pair_name: pair.pair_name,
            common_code: pair.common_code,
            preferred_code: pair.preferred_code,
            entry_date: pair.entry_date,
            common_entry: pair.common_entry,
            preferred_entry: pair.preferred_entry,
            common_qty: pair.common_qty,
            preferred_qty: pair.preferred_qty,
            common_close: commonClose,
            preferred_close: preferredClose,
            status: pair.status
        });
    }
    return results;
}

// 예시: HTML에 표시
async function renderOpenPairsTable() {
    const pairs = await fetchOpenPairsWithPrices();
    const tbody = document.getElementById('open-pairs-body');
    tbody.innerHTML = '';
    for (const pair of pairs) {
        // 평가손익 계산
        let pnl = '-';
        if (pair.common_close && pair.preferred_close) {
            const shortPnl = (pair.common_entry - pair.common_close) * pair.common_qty;
            const longPnl = (pair.preferred_close - pair.preferred_entry) * pair.preferred_qty;
            pnl = (shortPnl + longPnl).toLocaleString();
        }
        const tr = document.createElement('tr');
        tr.innerHTML = `
      <td>${pair.pair_name}</td>
      <td>${pair.common_code}</td>
      <td>${pair.preferred_code}</td>
      <td>${pair.entry_date}</td>
      <td>${pair.common_entry.toLocaleString()}<br>${pair.preferred_entry.toLocaleString()}</td>
      <td>${pair.common_qty}<br>${pair.preferred_qty}</td>
      <td>${pair.common_close ? pair.common_close.toLocaleString() : '-'}<br>${pair.preferred_close ? pair.preferred_close.toLocaleString() : '-'}</td>
      <td>${pnl}</td>
      <td>${pair.status}</td>
    `;
        tbody.appendChild(tr);
    }
    if (pairs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9">진행중(Open) 페어가 없습니다.</td></tr>`;
    }
}

// 페이지 로드 시 실행
document.addEventListener('DOMContentLoaded', renderOpenPairsTable);
