# test_trade_entry.py
import json
from datetime import datetime
from github_updater import GitHubUpdater

# 테스트 데이터 생성
test_entry = {
    "symbol": "삼성전자",
    "type": "매수",
    "price": 70000,
    "quantity": 10,
    "reason": "테스트 엔트리"
}

# 모의 monitor 객체 생성
class MockMonitor:
    async def get_signals_with_divergent(self):
        return [], []

# GitHubUpdater 인스턴스 생성 및 trade-entry 저장
mock_monitor = MockMonitor()
updater = GitHubUpdater(mock_monitor)

# 저장 함수 호출
try:
    result = updater.save_trade_entry(test_entry)
    print(f"저장 결과: {'성공' if result else '실패'}")
except Exception as e:
    print(f"오류 발생: {str(e)}")
