#!/usr/bin/env python3

import json
from datetime import datetime
import os
import logging
import asyncio
import subprocess
from datetime import datetime, timedelta
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
GITHUB_REPO_PATH = os.environ.get('GITHUB_REPO_PATH', '/home/eq/stmon')
GITHUB_USERNAME = os.environ.get('GITHUB_USERNAME', 'eqpair')
GITHUB_EMAIL = os.environ.get('GITHUB_EMAIL', 'frmn3962@gmail.com')
# SSH 방식으로 변경
GITHUB_REPO_URL = 'git@github.com:eqpair/stmon.git'

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
        process = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True,
            cwd=GITHUB_REPO_PATH  # 작업 디렉토리 명시적 지정
        )
        
        if process.returncode != 0:
            logger.error(f"명령어 실패: {process.stderr}")
            raise Exception(f"명령어 실패: {process.stderr}")
            
        return process.stdout.strip()
    
    async def update_data(self):
        try:
            # 기존 코드: 모니터링 데이터 가져오기
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
            
            # 히스토리 데이터the same time, 트렌드 데이터도 업데이트
            from stmon.modules.trend_collector import TrendCollector
            collector = TrendCollector()
            await collector.collect_all_trends()  # 트렌드 데이터 업데이트
            
            # 기존 코드: 히스토리 데이터 업데이트 및 커밋
            await self._update_history_data(data)
            self._commit_and_push()
            
            logger.info(f"GitHub 데이터 업데이트 완료: {current_time}")
        except Exception as e:
            logger.error(f"데이터 업데이트 오류: {str(e)}")
    
    def _parse_signals(self, signals_text: str) -> List[Dict[str, Any]]:
        result = []
        if not signals_text or "No divergent pairs" in signals_text:
            logger.warning(f"신호 데이터 없음 또는 divergent pairs 없음")
            return result
            
        # HTML 태그 제거 헬퍼 함수
        def strip_html_tags(text):
            import re
            return re.sub(r'<[^>]+>', '', text) if text else text
            
        # 데이터를 올바르게 파싱하기 위해 2줄씩 처리
        lines = signals_text.split('\n')
        i = 0
        
        while i < len(lines) - 1:
            try:
                stock_name_line = strip_html_tags(lines[i].strip())  # HTML 태그 제거
                signal_line = lines[i+1].strip() if i+1 < len(lines) else ""
                
                if not stock_name_line or not signal_line:
                    i += 2
                    continue
                    
                # 종목명 처리
                if stock_name_line.startswith('🔴 ') or stock_name_line.startswith('🟠 ') or stock_name_line.startswith('🟢 ') or stock_name_line.startswith('🔵 '):
                    icon_prefix = stock_name_line[:2]  # 아이콘 저장
                    stock_name = stock_name_line[2:].strip()  # 아이콘 제거
                else:
                    icon_prefix = ""
                    stock_name = stock_name_line
                    
                # 가중치 정보 추출
                formatted_stock_name = stock_name
                weight_info = ""
                if ' (' in stock_name and ')' in stock_name:
                    parts = stock_name.split(' (')
                    if len(parts) == 2 and ')' in parts[1]:
                        weight_info = parts[1].replace(')', '')
                        base_name = parts[0]
                        # 웹 표시용 종목명 포맷: 기본명-가중치-
                        formatted_stock_name = f"{base_name}-{weight_info}-"
                
                # 아이콘이 있으면 종목명 앞에 추가
                if icon_prefix:
                    formatted_stock_name = f"{icon_prefix} {formatted_stock_name}"
                    
                # 신호 라인 파싱
                if '/' not in signal_line:
                    i += 2
                    continue
                    
                signal_parts = signal_line.split('/')
                
                # SZ 값 추출
                sz_value = 0.0
                try:
                    sz_value = float(signal_parts[0].strip())
                except ValueError:
                    sz_value = 0.0
                    
                # 신호 추출
                signal = ""
                if len(signal_parts) > 1:
                    signal_info = signal_parts[1].strip()
                    if 'R' in signal_info:
                        signal += 'R'
                    if 'I' in signal_info:
                        signal += 'I'
                    if 'O' in signal_info:
                        signal += 'O'
                        
                # 가격 추출
                price_a = None
                price_b = None
                if len(signal_parts) > 2:
                    price_part = signal_parts[2].strip()
                    price_items = price_part.split(',')
                    if len(price_items) > 0:
                        try:
                            price_a = float(price_items[0].strip())
                        except ValueError:
                            pass
                    if len(price_items) > 1:
                        try:
                            price_b = float(price_items[1].strip())
                        except ValueError:
                            pass
                
                # 데이터 구조화
                signal_data = {
                    "stock_name": formatted_stock_name,
                    "sz_value": sz_value,
                    "signal": signal,
                    "price_a": price_a,
                    "price_b": price_b,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                result.append(signal_data)
                
            except Exception as e:
                logger.warning(f"라인 파싱 오류: {lines[i:i+2]} - {str(e)}")
            
            # 다음 종목으로 이동 (2줄씩)
            i += 2
        
        logger.info(f"파싱된 신호 수: {len(result)}")
        return result
    
    async def _update_history_data(self, current_data):
        """시그널 히스토리 데이터 업데이트 - 1년치 데이터 보존"""
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
        
        # 1년 전 날짜 계산
        one_year_ago = datetime.now() - timedelta(days=365)
        one_year_ago_str = one_year_ago.strftime("%Y-%m-%d")
        
        # 1년치 데이터만 보존 (오래된 데이터 필터링)
        filtered_signals = []
        for signal in history["signals"]:
            # 타임스탬프가 있고, 1년 이내인 데이터만 유지
            if "timestamp" in signal:
                signal_date = signal["timestamp"].split()[0]  # 2023-01-01 형식에서 날짜만 추출
                if signal_date >= one_year_ago_str:
                    filtered_signals.append(signal)
        
        # 필터링된 데이터로 갱신
        history["signals"] = filtered_signals
        
        # 새 신호들 추가 (중복 확인)
        timestamp = current_data["timestamp"]
        
        for signal in current_data["all_signals"]:
            signal["timestamp"] = timestamp
            
            # 기존 중복 검사 로직 사용
            is_duplicate = False
            for existing in history["signals"]:
                if (existing["stock_name"] == signal["stock_name"] and 
                    existing["timestamp"] == signal["timestamp"]):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                history["signals"].append(signal)
        
        # 히스토리 크기 제한 - 1년치 데이터를 위해 충분히 여유있게 설정
        max_signals = 10000  # 1년 365일 * 약 20개 종목 * 하루 1-2회 데이터
        if len(history["signals"]) > max_signals:
            history["signals"] = history["signals"][-max_signals:]
        
        # 히스토리 저장
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    
    async def update_trend_data(self):
        """트렌드 데이터 업데이트"""
        try:
            from stmon.modules.trend_collector import TrendCollector
            
            logger.info("트렌드 데이터 수집 시작")
            collector = TrendCollector()
            await collector.collect_all_trends()
            logger.info("트렌드 데이터 수집 완료")
            
            # 트렌드 데이터 디렉토리를 Git에 추가
            trends_dir = os.path.join(DATA_DIR, "trends")
            os.makedirs(trends_dir, exist_ok=True)
        
        except Exception as e:
            logger.error(f"트렌드 데이터 업데이트 오류: {str(e)}")

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
        logger.info("다음 업데이트까지 30분 대기 중...")
        await asyncio.sleep(600)  # 30분마다 업데이트

# 메인 함수
if __name__ == "__main__":
    import sys
    
    daily_run = False
    if len(sys.argv) > 1 and sys.argv[1] == "--daily":
        daily_run = True
    
    asyncio.run(start_github_updater(daily_run))