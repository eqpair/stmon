import json
import os
import subprocess
from datetime import datetime

def save_trade_entry(entry_data, repo_path=None):
    """트레이드 엔트리 데이터를 trades.json 파일에 저장"""
    try:
        if repo_path is None:
            repo_path = '/home/eq/stmon'
        
        # 데이터 파일 경로 설정
        trades_file = f"{repo_path}/data/trades.json"
        
        # 기존 데이터 로드 (파일이 없으면 빈 리스트 생성)
        try:
            with open(trades_file, 'r', encoding='utf-8') as f:
                trades = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            trades = []
        
        # 새 엔트리에 타임스탬프 추가
        entry_data['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 새 엔트리 추가
        trades.append(entry_data)
        
        # 데이터 저장
        with open(trades_file, 'w', encoding='utf-8') as f:
            json.dump(trades, f, ensure_ascii=False, indent=2)
        
        print(f"트레이드 엔트리 저장 성공: {trades_file}")
        
        # Git 명령어 실행
        def run_command(command):
            process = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=repo_path
            )
            return process.stdout, process.stderr

        # Git 상태 확인
        stdout, stderr = run_command("git status --porcelain")
        
        # 변경사항이 있는 경우
        if stdout:
            # 변경사항 스테이징
            run_command("git add .")
            
            # 커밋
            commit_message = f"트레이드 엔트리 추가: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            run_command(f'git commit -m "{commit_message}"')
            
            # GitHub에 푸시
            run_command("git push")
            
            print("GitHub 저장소에 성공적으로 푸시되었습니다.")
        else:
            print("변경사항이 없습니다. 푸시 생략.")
        
        return True
    except Exception as e:
        print(f"트레이드 엔트리 저장 오류: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    # 테스트 데이터
    test_entry = {
        "symbol": "삼성전자",
        "type": "매수",
        "price": 70000,
        "quantity": 10,
        "reason": "테스트 엔트리"
    }
    
    # 저장 함수 호출
    result = save_trade_entry(test_entry)
    print(f"저장 결과: {'성공' if result else '실패'}")
