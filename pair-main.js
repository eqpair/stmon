// 오늘 날짜 (KST 기준)
const TODAY = new Date('2025-04-28T18:06:00+09:00'); // 서버 없이 고정값 사용, 실제 배포시 new Date()로 대체 가능

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

// 날짜 차이(일수) 계산 (오늘 포함, 청산시 진입~청산, 미청산시 진입~오늘)
function calcDays(entryDate, exitDate) {
    if (!entryDate) return "-";
    const start = new Date(entryDate);
    const end = exitDate ? new Date(exitDate) : TODAY;
    // 하루 = 1000*60*60*24
    const diffDays = Math.floor((end - start) / (1000 * 60 * 60 * 24)) + 1;
    return diffDays > 0 ? diffDays + "일" : "-";
}

function calcPairReturn(entry, cPrice, pPrice) {
    const c_fee = entry.common_fee_pct / 100;
    const p_fee = entry.preferred_fee_pct / 100;
    if (entry.status === "청산") {
        const shortRet = ((entry.common_entry * (1 - c_fee) - entry.common_exit * (1 + c_fee)) / entry.common_entry) * 100;
        const longRet = ((entry.preferred_exit * (1 - p_fee) - entry.preferred_entry * (1 + p_fee)) / entry.preferred_entry) * 100;
        return (shortRet + longRet).toFixed(2) + "%";
    } else if (cPrice && pPrice) {
        const shortRet = ((entry.common_entry * (1 - c_fee) - cPrice * (1 + c_fee)) / entry.common_entry) * 100;
        const longRet = ((pPrice * (1 - p_fee) - entry.preferred_entry * (1 + p_fee)) / entry.preferred_entry) * 100;
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
            pairRet = calcPairReturn(entry, cNow, pNow);
        } else {
            cNow = entry.common_exit;
            pNow = entry.preferred_exit;
            pairRet = calcPairReturn(entry, null, null);
        }
        const retClass = (pairRet !== "-" && parseFloat(pairRet) < 0) ? "negative" : "positive";
        tbody.innerHTML += `
      <tr class="${rowClass}">
        <td>${entry.pair_name}</td>
        <td>${entry.entry_date}</td>
        <td>${entry.exit_date || "-"}</td>
        <td>${days}</td>
        <td>${entry.common_name}</td>
        <td>${entry.preferred_name}</td>
        <td>${entry.common_entry} / ${entry.preferred_entry}</td>
        <td>${entry.common_qty} / ${entry.preferred_qty}</td>
        <td>${entry.common_fee_pct} / ${entry.preferred_fee_pct}</td>
        <td>${cNow || "-"} / ${pNow || "-"}</td>
        <td class="${retClass}">${pairRet}</td>
        <td>${entry.status}</td>
      </tr>
    `;
    }
}

renderTable();
setInterval(renderTable, 30000);
