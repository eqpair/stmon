from flask import Flask, request, jsonify, send_from_directory
import os
import json

app = Flask(__name__, static_url_path='', static_folder='templates')
DATA_FILE = os.path.join('data', 'trades.json')

# 기본 HTML 페이지
@app.route('/')
def index():
    return send_from_directory('templates', 'trades.html')

# 정적 파일 제공 (trades.html 외 다른 HTML들도 포함)
@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('templates', path)

# trades.json 불러오기
@app.route('/data/trades.json', methods=['GET'])
def get_trades():
    if not os.path.exists(DATA_FILE):
        return jsonify([])
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))

# 거래 저장 API
@app.route('/save-trade', methods=['POST'])
def save_trade():
    trade = request.json
    trades = []

    # 기존 데이터 불러오기
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                trades = json.load(f)
            except:
                trades = []

    # 새 거래 추가
    trades.append(trade)

    # 저장
    os.makedirs('data', exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(trades, f, indent=2, ensure_ascii=False)

    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
