import sys
import json
import threading
import time
import re
import random
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTextEdit, QPushButton, QRadioButton, 
                             QLabel, QLineEdit, QGroupBox, QButtonGroup)
from PyQt6.QtCore import pyqtSignal, QObject, Qt
from web3 import Web3

# --- 核心 ABI 配置 ---
ABI_EARNED = [{"inputs": [{"name": "token", "type": "address"}, {"name": "tokenId", "type": "uint256"}],
               "name": "earned", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"}]

ABI_CLAIM = [{"inputs": [{"name": "_bribes", "type": "address[]"}, {"name": "_tokens", "type": "address[][]"}, {"name": "_tokenId", "type": "uint256"}],
              "name": "claimBribes", "outputs": [], "stateMutability": "nonpayable", "type": "function"}]

class Ve33Tools(QMainWindow):
    # 1. 定义一个专门用来传递日志文本的跨线程信号
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ve33 Tools Professional - Auto Scan Edition")
        self.resize(900, 700)
        self.is_running = threading.Event() # 停止标志位
        
        # 将信号连接到自定义的日志打印函数上
        self.log_signal.connect(self.append_log)
        
        self.init_ui()
        self.load_data()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- 顶部设置区 ---
        top_layout = QHBoxLayout()
        
        net_group = QGroupBox("网络")
        net_layout = QHBoxLayout()
        self.rb_base = QRadioButton("Base")
        self.rb_base.setChecked(True)
        self.rb_op = QRadioButton("OP")
        net_layout.addWidget(self.rb_base)
        net_layout.addWidget(self.rb_op)
        net_group.setLayout(net_layout)
        
        gas_group = QGroupBox("Gas Limit")
        gas_layout = QHBoxLayout()
        self.gas_input = QLineEdit()
        self.gas_input.setPlaceholderText("默认自动")
        gas_layout.addWidget(self.gas_input)
        gas_group.setLayout(gas_layout)

        top_layout.addWidget(net_group)
        top_layout.addWidget(gas_group)
        main_layout.addLayout(top_layout)

        # --- 投票 Data 解析区 ---
        vote_group = QGroupBox("投票 Data 解析")
        vote_layout = QVBoxLayout()
        self.data_input = QTextEdit()
        self.data_input.setPlaceholderText("在此粘贴投票交易的 HEX Data...")
        self.data_input.setFixedHeight(80)
        self.data_input.textChanged.connect(self.auto_parse_vote_address)
        self.target_addr_label = QLabel("解析地址: 未解析")
        self.target_addr_label.setStyleSheet("color: #3498db; font-weight: bold;")
        vote_layout.addWidget(self.data_input)
        vote_layout.addWidget(self.target_addr_label)
        vote_group.setLayout(vote_layout)
        main_layout.addWidget(vote_group)

        # --- 操作按钮区 ---
        btn_layout = QHBoxLayout()
        self.btn_vote = QPushButton("批量投票")
        self.btn_claim = QPushButton("自动扫描领取奖励")
        self.btn_rebase = QPushButton("批量 Rebase")
        self.btn_stop = QPushButton("停止运行")
        
        self.btn_vote.setStyleSheet("background-color: #3498db; color: white; height: 35px;")
        self.btn_claim.setStyleSheet("background-color: #2ecc71; color: white; height: 35px;")
        self.btn_rebase.setStyleSheet("height: 35px;")
        self.btn_stop.setStyleSheet("background-color: #e74c3c; color: white; height: 35px;")
        
        self.btn_vote.clicked.connect(lambda: self.start_task("vote"))
        self.btn_claim.clicked.connect(lambda: self.start_task("claim"))
        self.btn_rebase.clicked.connect(lambda: self.start_task("rebase"))
        self.btn_stop.clicked.connect(self.stop_task)
        
        btn_layout.addWidget(self.btn_vote)
        btn_layout.addWidget(self.btn_claim)
        btn_layout.addWidget(self.btn_rebase)
        btn_layout.addWidget(self.btn_stop)
        main_layout.addLayout(btn_layout)

        # --- 日志区 ---
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("background-color: #2c3e50; color: #ecf0f1; font-family: 'Consolas'; font-size: 13px;")
        main_layout.addWidget(self.log_output)

    # 2. 安全的日志打印方法（带自动滚动）
    def append_log(self, text):
        self.log_output.append(text)
        # 强制将滚动条拉到最底部
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def load_data(self):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                raw_text = f.read()
            
            # 使用高级正则，忽略 https:// 里的双斜杠，只删掉真正的 // 注释
            clean_text = re.sub(r'(?<!:)//.*', '', raw_text)
            self.config = json.loads(clean_text)
        
            with open("vote.txt", "r", encoding="utf-8") as f:
                self.votes = [line.strip().split("|") for line in f if "|" in line]
            
            # 全局统一使用信号发送日志
            self.log_signal.emit(f"[*] 就绪。已加载 {len(self.votes)} 个账户。")
        
        except Exception as e:
            self.log_signal.emit(f"[!] 加载失败: {e}")

    def auto_parse_vote_address(self):
        data = self.data_input.toPlainText().strip()
        if not data.startswith("0x7ac09bf7"):
            self.target_addr_label.setText("解析地址: 格式错误")
            return
        try:
            addr_hex = data[264:328]
            addr = "0x" + addr_hex[-40:]
            self.target_addr_label.setText(f"解析地址: {Web3.to_checksum_address(addr)}")
        except:
            self.target_addr_label.setText("解析地址: 解析失败")

    def stop_task(self):
        self.is_running.clear()
        self.log_signal.emit("\n[!] 正在请求停止，请等待当前操作中断...")

    def start_task(self, task_type):
        self.is_running.set()
        self.toggle_btns(False)
        threading.Thread(target=self.run_worker, args=(task_type,), daemon=True).start()

    def toggle_btns(self, state):
        self.btn_vote.setEnabled(state)
        self.btn_claim.setEnabled(state)
        self.btn_rebase.setEnabled(state)

    def run_worker(self, task_type):
        net = "Base" if self.rb_base.isChecked() else "OP"
        try:
            cfg = self.config["networks"][net]
            w3 = Web3(Web3.HTTPProvider(cfg["rpc_url"]))
            
            # 3. 核心修改：复制并随机打乱执行顺序
            votes_to_process = self.votes.copy()
            random.shuffle(votes_to_process)
            
            self.log_signal.emit(f"[*] 已打乱钱包顺序，准备执行任务...")
            
            for pk, tid in votes_to_process:
                if not self.is_running.is_set(): break
                
                tid = int(tid.strip())
                acc = w3.eth.account.from_key(pk.strip())
                
                try:
                    if task_type == "vote":
                        self.execute_vote(w3, acc, tid, cfg)
                    elif task_type == "claim":
                        self.execute_claim(w3, acc, tid, cfg)
                    elif task_type == "rebase":
                        self.execute_rebase(w3, acc, tid, net)
                except Exception as e:
                    self.log_signal.emit(f"-> ID {tid} 异常: {e}")
                
            if self.is_running.is_set():
                self.log_signal.emit("[*] 任务全部执行完毕。")
            else:
                self.log_signal.emit("[!] 任务已手动中止。")
                
        except Exception as e:
            self.log_signal.emit(f"[!] 运行错误: {e}")
            
        self.toggle_btns(True)

    def execute_vote(self, w3, acc, tid, cfg):
        target_text = self.target_addr_label.text()
        if "0x" not in target_text: 
            self.log_signal.emit("[!] 请先粘贴正确的 Data 解析出地址。")
            self.is_running.clear()
            return
            
        target = target_text.split(": ")[1]
        
        selector = "0x7ac09bf7"
        data = selector + hex(tid)[2:].zfill(64) + \
               "0000000000000000000000000000000000000000000000000000000000000060" + \
               "00000000000000000000000000000000000000000000000000000000000000a0" + \
               "0000000000000000000000000000000000000000000000000000000000000001" + \
               target[2:].zfill(64) + \
               "0000000000000000000000000000000000000000000000000000000000000001" + \
               "0000000000000000000000000000000000000000000000000000000000000064"

        self.send_tx(w3, acc, cfg["vote_contract"], data, f"投票 ID {tid}")

    def execute_claim(self, w3, acc, tid, cfg):
        self.log_signal.emit(f"[*] 扫描 ID {tid} 奖励...")
        
        reward_sources = cfg.get("reward_contracts", [])
        tokens_to_scan = cfg.get("common_tokens", [])
        
        if not reward_sources or not tokens_to_scan:
            self.log_signal.emit(f"[!] 警告: config.json 中未配置 reward_contracts 或 common_tokens")
            return
            
        _bribes, _tokens = [], []
        for src in reward_sources:
            if not self.is_running.is_set(): break
            
            src_addr = Web3.to_checksum_address(src)
            found = []
            
            for t in tokens_to_scan:
                if not self.is_running.is_set(): break
                
                try:
                    c = w3.eth.contract(address=src_addr, abi=ABI_EARNED)
                    if c.functions.earned(Web3.to_checksum_address(t), tid).call() > 0:
                        found.append(Web3.to_checksum_address(t))
                        
                    # 防限流机制：每次查询后休息 0.1 秒
                    time.sleep(0.1) 
                except Exception as e: 
                    continue
                    
            if found:
                _bribes.append(src_addr)
                _tokens.append(found)

        if _bribes and self.is_running.is_set():
            voter_c = w3.eth.contract(address=Web3.to_checksum_address(cfg["vote_contract"]), abi=ABI_CLAIM)
            tx_data = voter_c.encode_abi("claimBribes", [_bribes, _tokens, tid])
            self.send_tx(w3, acc, cfg["vote_contract"], tx_data, f"领取奖励 ID {tid}")
        elif not _bribes and self.is_running.is_set():
            self.log_signal.emit(f"-> ID {tid}: 无余额。")

    def execute_rebase(self, w3, acc, tid, net):
        rebase_addr = "0x227f65131a261548b057215bb1d5ab2997964c7d" if net == "Base" else "0x9d4736ec60715e71afe72973f7885dcbc21ea99b"
        data = "0x379607f5" + hex(tid)[2:].zfill(64)
        self.send_tx(w3, acc, rebase_addr, data, f"Rebase ID {tid}")

    def send_tx(self, w3, acc, to, data, desc):
        try:
            tx = {
                'to': Web3.to_checksum_address(to),
                'data': data,
                'from': acc.address,
                'nonce': w3.eth.get_transaction_count(acc.address),
                'gasPrice': w3.eth.gas_price,
                'chainId': w3.eth.chain_id
            }
            gas = self.gas_input.text()
            tx['gas'] = int(gas) if gas else int(w3.eth.estimate_gas(tx) * 1.2)
            signed = w3.eth.account.sign_transaction(tx, acc.key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            self.log_signal.emit(f"-> {desc}: [成功] {tx_hash.hex()}")
        except Exception as e:
            self.log_signal.emit(f"-> {desc}: [失败] {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Ve33Tools()
    window.show()
    sys.exit(app.exec())
