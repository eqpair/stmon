from flask import Flask, request, jsonify, render_template, send_from_directory
import json
import os
import subprocess
from datetime import datetime

app = Flask(__name__, static_url_path='', static_folder='static')

# 저장소 경로 설정
REPO_PATH = '/home/eq/stmon'

# 데이터 파일 경로 설정
TRADES_FILE = f"{REPO_PATH}/data/trades.json"

# Git 명령어 실행 함수
def run_command(command):
    process = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        cwd=REPO_PATH
    )
    return process.stdout, process.stderr

# 변경사항 커밋 및 푸시 함수
def commit_and_push():
    try:
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
            
            return True
        else:
            return False
    except Exception as e:
        print(f"GitHub 커밋/푸시 오류: {str(e)}")
        return False

# 트레이드 엔트리 저장 함수
def save_trade_entry(entry_data):
    try:
        # 기존 데이터 로드 (파일이 없으면 빈 리스트 생성)
        try:
            with open(TRADES_FILE, 'r', encoding='utf-8') as f:
                trades = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            trades = []
        
        # 새 엔트리에 타임스탬프 추가
        entry_data['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 새 엔트리 추가
        trades.append(entry_data)
        
        # 데이터 저장
        with open(TRADES_FILE, 'w', encoding='utf-8') as f:
            json.dump(trades, f, ensure_ascii=False, indent=2)
        
        # GitHub에 변경사항 커밋 및 푸시
        commit_and_push()
        
        return True
    except Exception as e:
        print(f"트레이드 엔트리 저장 오류: {str(e)}")
        return False

# 루트 경로 - 메인 페이지
@app.route('/')
def index():
    return app.send_static_file('index.html')

# API 엔드포인트 - 트레이드 엔트리 저장
@app.route('/api/trade-entry', methods=['POST'])
def add_trade_entry():
    try:
        # 요청 데이터 가져오기
        entry_data = request.json
        
        # 트레이드 엔트리 저장
        result = save_trade_entry(entry_data)
        
        if result:
            return jsonify({"status": "success", "message": "트레이드 엔트리가 저장되었습니다."})
        else:
            return jsonify({"status": "error", "message": "트레이드 엔트리 저장에 실패했습니다."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# API 엔드포인트 - 트레이드 엔트리 목록 가져오기
@app.route('/api/trade-entries', methods=['GET'])
def get_trade_entries():
    try:
        # 기존 데이터 로드
        try:
            with open(TRADES_FILE, 'r', encoding='utf-8') as f:
                trades = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            trades = []
        
        return jsonify(trades)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # 정적 파일 디렉토리 생성
    os.makedirs(f"{REPO_PATH}/static", exist_ok=True)
    
    # 개발 서버 실행 (실제 운영 환경에서는 Gunicorn이나 uWSGI 사용 권장)
    app.run(debug=True, host='0.0.0.0', port=5000)
