function formatNumber(num) {
    if (num === null || num === undefined || num === "-") return "-";
    if (isNaN(num)) return num;
    return Number(num).toLocaleString("en-US");
}

function getFeeRate(commission_bps, stamp_bps) {
    return (Number(commission_bps) + Number(stamp_bps)) / 10000;
}

async function fetchPairs() {
    const resp = await fetch('data/pair-trades.json');
    return await resp.json();
}

async function fetchPrice(code) {
    const url = `https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:${code}`;
    try {
        const resp = await fetch(url);
        const data = await resp.json();
        return data.result.areas[0].datas[0].nv;
    } catch {
        return null;
    }
}

function calcDays(entryDate, exitDate) {
    if (!entryDate) return "-";
    const start = new Date(entryDate);
    const end = exitDate ? new Date(exitDate) : new Date();
    const diffDays = Math.floor((end - start) / (1000 * 60 * 60 * 24)) + 1;
    return diffDays > 0 ? diffDays + "일" : "-";
}

// 진입/청산가에 각각 수수료율 적용
function calcPairReturn(entry, cPrice, pPrice) {
    const feeRate = getFeeRate(entry.commission_bps, entry.stamp_bps);
    // 보통주: 숏, 우선주: 롱
    if (entry.status === "청산") {
        const shortRet = ((entry.common_entry * (1 - feeRate) - entry.common_exit * (1 + feeRate)) / entry.common_entry) * 100;
        const longRet = ((entry.preferred_exit * (1 - feeRate) - entry.preferred_entry * (1 + feeRate)) / entry.preferred_entry) * 100;
        return (shortRet + longRet).toFixed(2) + "%";
    } else if (cPrice && pPrice) {
        const shortRet = ((entry.common_entry * (1 - feeRate) - cPrice * (1 + feeRate)) / entry.common_entry) * 100;
        const longRet = ((pPrice * (1 - feeRate) - entry.preferred_entry * (1 + feeRate)) / entry.preferred_entry) * 100;
        return (shortRet + longRet).toFixed(2) + "%";
    }
    return "-";
}

async function renderTable() {
    const pairs = await fetchPairs();
    const tbody = document.querySelector("#pair-table tbody");
    tbody.innerHTML = "";

    for (const entry of pairs) {
        let cNow = "-", pNow = "-", pairRet = "-";
        let rowClass = entry.status === "청산" ? "closed" : "open";
        let days = calcDays(entry.entry_date, entry.exit_date);
        if (entry.status === "보유중") {
            cNow = await fetchPrice(entry.common_code);
            pNow = await fetchPrice(entry.preferred_code);
            pairRet = calcPairReturn(entry, cNow, pNow); // 실시간 수익률
        } else {
            cNow = entry.common_exit;
            pNow = entry.preferred_exit;
            pairRet = calcPairReturn(entry, null, null); // 확정 수익률
        }
        const retClass = (pairRet !== "-" && parseFloat(pairRet) < 0) ? "negative" : "positive";
        tbody.innerHTML += `
      <tr class="${rowClass}">
        <td data-label="페어">${entry.pair_name}</td>
        <td data-label="진입일">${entry.entry_date}</td>
        <td data-label="청산일">${entry.exit_date || "-"}</td>
        <td data-label="진행일수">${days}</td>
        <td data-label="진입가">${formatNumber(entry.common_entry)} / ${formatNumber(entry.preferred_entry)}</td>
        <td data-label="수량">${formatNumber(entry.common_qty)} / ${formatNumber(entry.preferred_qty)}</td>
        <td data-label="수수료(bps)">${formatNumber(entry.commission_bps)} / ${formatNumber(entry.stamp_bps)}</td>
        <td data-label="청산가/현재가">${formatNumber(cNow) || "-"} / ${formatNumber(pNow) || "-"}</td>
        <td data-label="수익률" class="${retClass}">${pairRet}</td>
        <td data-label="상태">${entry.status}</td>
      </tr>
    `;
    }
}

renderTable();
setInterval(renderTable, 30000); // 30초마다 실시간 갱신
