#!/usr/bin/env python3

import os
import json
import time
import logging
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# 로깅 설정
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/github_updater.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# GitHub 저장소 정보
GITHUB_REPO_PATH = os.environ.get('GITHUB_REPO_PATH', '/home/pi/work/m5000')
GITHUB_USERNAME = os.environ.get('GITHUB_USERNAME', 'eqpair')
GITHUB_EMAIL = os.environ.get('GITHUB_EMAIL', 'frmn3962@gmail.com')
# SSH 방식으로 변경
GITHUB_REPO_URL = 'git@github.com:eqpair/monitor.git'

# 기본 데이터 디렉토리
DATA_DIR = Path(f"{GITHUB_REPO_PATH}/data")
os.makedirs(DATA_DIR, exist_ok=True)

class GitHubUpdater:
    def __init__(self, monitor):
        self.monitor = monitor
        self.setup_git_config()
        
    def setup_git_config(self):
        """Git 설정 초기화"""
        try:
            # SSH 호스트 키 확인 건너뛰기 설정
            ssh_config_path = os.path.expanduser("~/.ssh/config")
            os.makedirs(os.path.dirname(ssh_config_path), exist_ok=True)
            
            if not os.path.exists(ssh_config_path) or "StrictHostKeyChecking no" not in open(ssh_config_path).read():
                with open(ssh_config_path, "a") as f:
                    f.write("\nHost github.com\n    StrictHostKeyChecking no\n")
                logger.info("SSH 설정 완료")
            
            if not os.path.exists(GITHUB_REPO_PATH):
                logger.info(f"클론 저장소 생성: {GITHUB_REPO_PATH}")
                os.makedirs(GITHUB_REPO_PATH, exist_ok=True)
                self.run_command(f"git clone {GITHUB_REPO_URL} {GITHUB_REPO_PATH}")
            
            # Git 사용자 설정
            os.chdir(GITHUB_REPO_PATH)
            self.run_command(f"git config user.name '{GITHUB_USERNAME}'")
            self.run_command(f"git config user.email '{GITHUB_EMAIL}'")
            logger.info("Git 설정 완료")
            
            # 데이터 디렉토리 생성
            os.makedirs(DATA_DIR, exist_ok=True)
            
        except Exception as e:
            logger.error(f"Git 설정 오류: {str(e)}")
            raise
    
    def run_command(self, command):
        """Shell 명령어 실행"""
        logger.debug(f"명령어 실행: {command}")
        process = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if process.returncode != 0:
            logger.error(f"명령어 실패: {process.stderr}")
            raise Exception(f"명령어 실패: {process.stderr}")
            
        return process.stdout.strip()
    
    async def update_data(self):
        """주식 모니터링 데이터 업데이트 및 GitHub 푸시"""
        try:
            # 모니터링 데이터 가져오기
            all_signals, divergent_signals = await self.monitor.get_signals_with_divergent()
            
            # 데이터 구조화
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data = {
                "timestamp": current_time,
                "last_updated": current_time,
                "all_signals": self._parse_signals(all_signals),
                "divergent_signals": self._parse_signals(divergent_signals)
            }
            
            # 데이터 파일 저장
            data_file = DATA_DIR / "stock_data.json"
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 히스토리 데이터 업데이트
            await self._update_history_data(data)
            
            # GitHub 커밋 및 푸시
            self._commit_and_push()
            
            logger.info(f"GitHub 데이터 업데이트 완료: {current_time}")
            
        except Exception as e:
            logger.error(f"데이터 업데이트 오류: {str(e)}")
    
    def _parse_signals(self, signals_text: str) -> List[Dict[str, Any]]:
        """시그널 텍스트를 구조화된 데이터로 파싱"""
        result = []
        if not signals_text or "No divergent pairs" in signals_text:
            return result
            
        for line in signals_text.split('\n'):
            if not line.strip():
                continue
                
            try:
                # 형식: "종목명: 값/신호 / 가격1, 가격2"
                parts = line.split(':')
                if len(parts) < 2:
                    continue
                    
                stock_name = parts[0].strip()
                signal_part = ':'.join(parts[1:]).strip()
                
                # 신호 부분 파싱
                signal_parts = signal_part.split('/')
                if len(signal_parts) < 2:
                    continue
                
                sz_value = float(signal_parts[0].strip())
                signal_info = signal_parts[1].strip()
                
                # 가격 정보 파싱
                if len(signal_parts) >= 3:
                    price_part = signal_parts[2].strip()
                    prices = price_part.split(',')
                    price_a = float(prices[0].strip()) if len(prices) > 0 else None
                    price_b = float(prices[1].strip()) if len(prices) > 1 else None
                else:
                    price_a = None
                    price_b = None
                
                # 데이터 구조화
                signal_data = {
                    "stock_name": stock_name,
                    "sz_value": sz_value,
                    "signal": signal_info.strip(),
                    "price_a": price_a,
                    "price_b": price_b,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                result.append(signal_data)
                
            except Exception as e:
                logger.warning(f"라인 파싱 오류: {line} - {str(e)}")
                continue
                
        return result
    
    async def _update_history_data(self, current_data):
        """시그널 히스토리 데이터 업데이트"""
        history_file = DATA_DIR / "history.json"
        
        # 기존 히스토리 로드
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                try:
                    history = json.load(f)
                except json.JSONDecodeError:
                    history = {"signals": []}
        else:
            history = {"signals": []}
        
        # 새 신호들만 추가 (중복 방지)
        timestamp = current_data["timestamp"]
        for signal in current_data["all_signals"]:
            signal["timestamp"] = timestamp
            
            # 이미 동일한 시그널이 있는지 확인
            is_duplicate = False
            for existing in history["signals"]:
                if (existing["stock_name"] == signal["stock_name"] and 
                    existing["signal"] == signal["signal"] and
                    existing["sz_value"] == signal["sz_value"]):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                history["signals"].append(signal)
        
        # 히스토리 크기 제한 (최대 500개)
        if len(history["signals"]) > 500:
            history["signals"] = history["signals"][-500:]
        
        # 히스토리 저장
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    
    def _commit_and_push(self):
        """변경사항 커밋 및 GitHub 저장소에 푸시"""
        try:
            os.chdir(GITHUB_REPO_PATH)
            
            # Git 상태 확인
            status = self.run_command("git status --porcelain")
            
            if status:  # 변경사항이 있는 경우
                # 변경사항 스테이징
                self.run_command("git add .")
                
                # 커밋
                commit_message = f"데이터 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                self.run_command(f'git commit -m "{commit_message}"')
                
                # GitHub에 푸시
                self.run_command("git push")
                logger.info("GitHub 저장소에 성공적으로 푸시되었습니다.")
            else:
                logger.info("변경사항이 없습니다. 푸시 생략.")
                
        except Exception as e:
            logger.error(f"GitHub 커밋/푸시 오류: {str(e)}")
            raise

async def start_github_updater():
    """GitHub 업데이터 시작"""
    from main import StockMonitor
    
    monitor = StockMonitor()
    updater = GitHubUpdater(monitor)
    
    while True:
        try:
            await updater.update_data()
        except Exception as e:
            logger.error(f"업데이트 오류: {str(e)}")
        
        # 30분 대기
        await asyncio.sleep(1800)  # 30분마다 업데이트
# github_updater.py에 다음 함수를 추가

async def update_trend_data(self):
    """트렌드 데이터 업데이트"""
    try:
        from trend_collector import TrendCollector
        
        logger.info("트렌드 데이터 수집 시작")
        collector = TrendCollector()
        await collector.collect_all_trends()
        logger.info("트렌드 데이터 수집 완료")
        
        # 트렌드 데이터 디렉토리를 Git에 추가
        trends_dir = os.path.join(DATA_DIR, "trends")
        os.makedirs(trends_dir, exist_ok=True)
        
        # GitHub 커밋 및 푸시는 update_data에서 처리하므로 별도로 처리하지 않음
    
    except Exception as e:
        logger.error(f"트렌드 데이터 업데이트 오류: {str(e)}")

# 그리고 기존 update_data 함수 내에 트렌드 데이터 업데이트 호출 추가
# update_data 함수 내부에 다음 코드 추가 (적절한 위치에)

# 트렌드 데이터 업데이트 (일주일에 한 번)
current_time = datetime.now()
if current_time.weekday() == 0 and current_time.hour < 6:  # 월요일 새벽에 실행
    await self.update_trend_data()

# start_github_updater 함수 수정 (daily_run 매개변수 추가)
async def start_github_updater(daily_run=False):
    """GitHub 업데이터 시작"""
    from main import StockMonitor
    
    monitor = StockMonitor()
    updater = GitHubUpdater(monitor)
    
    if daily_run:
        # 일일 실행 모드 (트렌드 데이터만 업데이트)
        await updater.update_trend_data()
        return
    
    while True:
        try:
            await updater.update_data()
        except Exception as e:
            logger.error(f"업데이트 오류: {str(e)}")
        
        # 30분 대기
        await asyncio.sleep(1800)  # 30분마다 업데이트

# 메인 함수 수정
if __name__ == "__main__":
    import sys
    
    daily_run = False
    if len(sys.argv) > 1 and sys.argv[1] == "--daily":
        daily_run = True
    
    asyncio.run(start_github_updater(daily_run))

if __name__ == "__main__":
    asyncio.run(start_github_updater())