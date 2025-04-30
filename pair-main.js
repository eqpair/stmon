// pair-main.js

// 차입수수료까지 반영한 평가손익 계산 (Open 상태 페어만)

function calcBorrowFee(entry, qty, borrowFeePct, days) {
    if (!entry || !qty || !borrowFeePct || !days) return 0;
    return entry * qty * (borrowFeePct / 100) * (days / 365);
}

function calcPnL(trade, commonPrice, preferredPrice, todayStr) {
    // 날짜 계산
    const entryDate = new Date(trade.entry_date);
    const today = todayStr ? new Date(todayStr) : new Date();
    const days = Math.max(1, Math.round((today - entryDate) / (1000 * 60 * 60 * 24)));

    // 손익 계산
    const shortPnl = (trade.common_entry - commonPrice) * trade.common_qty;
    const longPnl = (preferredPrice - trade.preferred_entry) * trade.preferred_qty;

    // 위탁+거래세 계산
    const comm_bps = (trade.commission_bps || 0) + (trade.stamp_bps || 0);
    const comm = ((trade.common_entry * trade.common_qty + commonPrice * trade.common_qty) +
        (trade.preferred_entry * trade.preferred_qty + preferredPrice * trade.preferred_qty)) * (comm_bps / 10000);

    // 차입수수료 계산 (보통주 숏만 적용)
    const borrowFee = calcBorrowFee(trade.common_entry, trade.common_qty, trade.common_borrow_fee_pct || 0, days);

    // 총손익
    return shortPnl + longPnl - comm - borrowFee;
}

// trend 파일에서 보통주/우선주 현재가(마감가) fetch
async function fetchTrendClose(pair) {
    try {
        const res = await fetch('data/trends/' + pair.common_code + '.json');
        const data = await res.json();
        let commonClose = null, preferredClose = null;
        if (data.common_prices && data.common_prices.length > 0)
            commonClose = data.common_prices[data.common_prices.length - 1];
        if (data.preferred_prices && data.preferred_prices.length > 0)
            preferredClose = data.preferred_prices[data.preferred_prices.length - 1];
        return { commonClose, preferredClose };
    } catch {
        return { commonClose: null, preferredClose: null };
    }
}

// Open 상태 페어만 평가손익 포함 테이블 렌더링
async function renderOpenPairsTable() {
    const res = await fetch('data/pair-trades.json');
    const trades = await res.json();
    const openPairs = trades.filter(pair => pair.status === 'Open');
    const tbody = document.getElementById('open-pairs-body');
    tbody.innerHTML = '';
    const todayStr = new Date().toISOString().slice(0, 10);
    for (const pair of openPairs) {
        // trend에서 현재가 fetch (보통주 코드 기준)
        const trend = await fetchTrendClose(pair);
        const commonPrice = trend.commonClose;
        const preferredPrice = trend.preferredClose;
        // 평가손익 계산
        let pnl = '-';
        if (commonPrice != null && preferredPrice != null) {
            pnl = Math.round(calcPnL(pair, commonPrice, preferredPrice, todayStr)).toLocaleString();
        }
        const tr = document.createElement('tr');
        tr.innerHTML = `
      <td>${pair.pair_name}</td>
      <td>${pair.common_code}</td>
      <td>${pair.preferred_code}</td>
      <td>${pair.entry_date}</td>
      <td>${pair.common_entry.toLocaleString()}<br>${pair.preferred_entry.toLocaleString()}</td>
      <td>${pair.common_qty}<br>${pair.preferred_qty}</td>
      <td>${commonPrice != null ? commonPrice.toLocaleString() : '-'}<br>${preferredPrice != null ? preferredPrice.toLocaleString() : '-'}</td>
      <td>${pnl}</td>
      <td>${pair.status}</td>
      <td>${pair.common_borrow_fee_pct ? pair.common_borrow_fee_pct + '%' : '-'}</td>
    `;
        tbody.appendChild(tr);
    }
    if (openPairs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10">진행중(Open) 페어가 없습니다.</td></tr>`;
    }
}

// 페이지 로드 시 실행
document.addEventListener('DOMContentLoaded', renderOpenPairsTable);
