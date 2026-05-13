import sys
import json
import threading
import time
import re
import random
import csv
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QRadioButton,
    QLineEdit,
    QGroupBox,
    QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal
from web3 import Web3
from web3.exceptions import TimeExhausted

# --- 核心 ABI 配置 ---
ABI_EARNED = [{"inputs": [{"name": "token", "type": "address"}, {"name": "tokenId", "type": "uint256"}],
               "name": "earned", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"}]

ABI_CLAIM = [{"inputs": [{"name": "_bribes", "type": "address[]"}, {"name": "_tokens", "type": "address[][]"}, {"name": "_tokenId", "type": "uint256"}],
              "name": "claimBribes", "outputs": [], "stateMutability": "nonpayable", "type": "function"}]

FUNCTION_SELECTOR = "0x7ac09bf7"
AMOUNT = 100000000000000000000
AMOUNT_HEX = hex(AMOUNT)


class Ve33Tools(QMainWindow):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ve33 Tools Professional")
        self.resize(980, 640)
        self.is_running = threading.Event()
        self.receipt_timeout = 180
        self.last_logged_parsed_address = None
        self.last_parse_error = None
        self.failed_records = []

        self.log_signal.connect(self.append_log)

        self.init_ui()
        self.load_data()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

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

        delay_group = QGroupBox("地址间隔(秒)")
        delay_layout = QHBoxLayout()
        self.delay_input = QLineEdit()
        self.delay_input.setPlaceholderText("例如 1.5 或 1-3；留空=无额外间隔")
        delay_layout.addWidget(self.delay_input)
        delay_group.setLayout(delay_layout)

        top_layout.addWidget(net_group)
        top_layout.addWidget(gas_group)
        top_layout.addWidget(delay_group)
        main_layout.addLayout(top_layout)

        vote_group = QGroupBox("投票 Data")
        vote_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        vote_group.setMaximumHeight(125)
        vote_layout = QVBoxLayout()
        vote_layout.setContentsMargins(10, 10, 10, 10)
        vote_layout.setSpacing(6)
        self.data_input = QTextEdit()
        self.data_input.setPlaceholderText("在此粘贴投票交易的 HEX Data...")
        self.data_input.setFixedHeight(62)
        self.data_input.textChanged.connect(self.auto_parse_vote_address)
        vote_layout.addWidget(self.data_input)
        vote_group.setLayout(vote_layout)
        main_layout.addWidget(vote_group, 0)

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

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet(
            "background-color: #2c3e50; color: #ecf0f1; font-family: 'Consolas'; font-size: 13px;"
        )
        main_layout.addWidget(self.log_output, 1)

    def append_log(self, text):
        self.log_output.append(text)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def load_data(self):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                raw_text = f.read()

            clean_text = re.sub(r'(?<!:)//.*', '', raw_text)
            self.config = json.loads(clean_text)

            with open("vote.txt", "r", encoding="utf-8") as f:
                self.votes = [line.strip().split("|") for line in f if "|" in line]

            self.log_signal.emit(f"[*] 就绪。已加载 {len(self.votes)} 个账户。")
        except Exception as e:
            self.log_signal.emit(f"[!] 加载失败: {e}")

    def get_clean_vote_data(self):
        data = self.data_input.toPlainText().strip()
        return re.sub(r'\s+', '', data)

    # 解析逻辑：只解析目标地址，不复用整段原始 data
    def parse_vote_target_address(self):
        data = self.get_clean_vote_data()
        if not data.lower().startswith(FUNCTION_SELECTOR):
            raise ValueError("投票 Data 格式错误")

        data = data[2:] if data.startswith('0x') else data
        data = data[8:]

        if len(data) < 320:
            raise ValueError("投票 Data 长度不足")

        offset_addr = data[64:128]
        if offset_addr != '0' * 60 + '0060':
            raise ValueError("投票 Data 的地址偏移不是 0x60")

        offset_amount = data[128:192]
        if offset_amount != '0' * 60 + '00a0':
            raise ValueError("投票 Data 的金额偏移不是 0xa0")

        addr_start = 192
        length_hex = data[addr_start:addr_start + 64]
        length = int(length_hex, 16)
        if length != 1:
            raise ValueError("当前仅支持单地址投票 Data")

        addr_hex = data[addr_start + 64: addr_start + 128]
        address = '0x' + addr_hex[24:]
        return Web3.to_checksum_address(address)

    #  calldata 生成逻辑
    def build_vote_calldata(self, vote_id, address):
        vote_id_hex = hex(vote_id)[2:].zfill(64)
        address_padded = "000000000000000000000000" + address[2:]
        amount_padded = AMOUNT_HEX[2:].zfill(64)
        calldata = (
            FUNCTION_SELECTOR +
            vote_id_hex +
            "0000000000000000000000000000000000000000000000000000000000000060" +
            "00000000000000000000000000000000000000000000000000000000000000a0" +
            "0000000000000000000000000000000000000000000000000000000000000001" +
            address_padded +
            "0000000000000000000000000000000000000000000000000000000000000001" +
            amount_padded
        )
        return calldata

    def auto_parse_vote_address(self):
        """
        自动解析只负责“能解析就提示成功”。
        不在 textChanged 过程中输出失败日志，避免 OP 标准 inputdata / 粘贴过程中的中间状态造成误报。
        真正点击批量投票时，execute_vote() 会严格拦截无效 Data。
        """
        data = self.get_clean_vote_data()
        if not data:
            self.last_logged_parsed_address = None
            self.last_parse_error = None
            return
        try:
            parsed = self.parse_vote_target_address()
            if parsed != self.last_logged_parsed_address:
                self.log_signal.emit(f"[*] 已解析投票地址: {parsed}")
                self.last_logged_parsed_address = parsed
            self.last_parse_error = None
        except Exception:
            # 粘贴/编辑过程中不输出错误；避免“已解析地址”同时又出现“解析失败”的混乱日志。
            # 如果用户直接开始投票，execute_vote() 会输出明确错误并停止。
            return

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

    def get_wallet_delay_seconds(self):
        raw = self.delay_input.text().strip()
        if not raw:
            return 0.0
        try:
            if "-" in raw:
                left, right = raw.split("-", 1)
                low = float(left.strip())
                high = float(right.strip())
                if low < 0 or high < 0:
                    raise ValueError("间隔不能为负数")
                if low > high:
                    low, high = high, low
                return random.uniform(low, high)
            value = float(raw)
            if value < 0:
                raise ValueError("间隔不能为负数")
            return value
        except Exception as e:
            self.log_signal.emit(f"[!] 地址间隔格式错误: {e}，本次按 0 秒处理")
            return 0.0

    def run_worker(self, task_type):
        net = "Base" if self.rb_base.isChecked() else "OP"
        stats = {"success": 0, "failed": 0, "pending": 0, "skipped": 0}
        self.failed_records = []
        try:
            cfg = self.config["networks"][net]
            w3 = Web3(Web3.HTTPProvider(cfg["rpc_url"]))

            votes_to_process = self.votes.copy()
            random.shuffle(votes_to_process)
            self.log_signal.emit("[*] 已随机打乱钱包顺序，准备执行任务...")

            total = len(votes_to_process)
            for idx, row in enumerate(votes_to_process, start=1):
                if not self.is_running.is_set():
                    break

                pk = row[0].strip() if len(row) > 0 else ""
                tid_raw = row[1].strip() if len(row) > 1 else ""
                acc = None
                tid = None
                result = "failed"
                reason = "未知错误"

                try:
                    tid = int(tid_raw)
                    acc = w3.eth.account.from_key(pk)
                    self.log_signal.emit(f"\n[*] 处理进度 {idx}/{total} | 地址 {acc.address} | tokenId={tid}")

                    if task_type == "vote":
                        result, reason = self.execute_vote(w3, acc, tid, cfg)
                    elif task_type == "claim":
                        result, reason = self.execute_claim(w3, acc, tid, cfg)
                    elif task_type == "rebase":
                        result, reason = self.execute_rebase(w3, acc, tid, net)
                    else:
                        result, reason = "failed", f"未知任务类型: {task_type}"

                except Exception as e:
                    result, reason = "failed", str(e)
                    show_addr = acc.address if acc else self.mask_private_key(pk)
                    self.log_signal.emit(f"-> 地址/ID 处理异常 | 地址/私钥={show_addr} | tokenId={tid_raw} | {reason}")

                if result not in stats:
                    result = "failed"
                stats[result] += 1

                if result in ("failed", "pending"):
                    self.record_problem_address(
                        task_type=task_type,
                        network=net,
                        address=acc.address if acc else self.mask_private_key(pk),
                        token_id=tid if tid is not None else tid_raw,
                        status=result,
                        reason=reason,
                    )

                if idx < total and self.is_running.is_set():
                    delay_seconds = self.get_wallet_delay_seconds()
                    if delay_seconds > 0:
                        self.log_signal.emit(f"[*] 当前地址处理完毕，等待 {delay_seconds:.2f}s 后继续下一个地址...")
                        self.sleep_with_stop(delay_seconds)

            summary = (
                f"[*] 统计: 成功 {stats['success']} / 失败 {stats['failed']} / "
                f"待确认 {stats['pending']} / 跳过 {stats['skipped']}"
            )
            self.log_signal.emit(summary)
            self.output_problem_addresses(task_type, net)
            if self.is_running.is_set():
                self.log_signal.emit("[*] 任务全部执行完毕。")
            else:
                self.log_signal.emit("[!] 任务已手动中止。")

        except Exception as e:
            self.log_signal.emit(f"[!] 运行错误: {e}")

        self.toggle_btns(True)

    def mask_private_key(self, pk):
        if not pk:
            return "空私钥"
        return pk[:8] + "..." + pk[-6:] if len(pk) > 16 else pk

    def record_problem_address(self, task_type, network, address, token_id, status, reason):
        self.failed_records.append({
            "task": task_type,
            "network": network,
            "address": address,
            "token_id": token_id,
            "status": status,
            "reason": str(reason),
        })

    def output_problem_addresses(self, task_type, network):
        if not self.failed_records:
            self.log_signal.emit("[*] 本次没有失败/待确认地址。")
            return

        self.log_signal.emit("\n[!] 本次失败/待确认地址明细：")
        for item in self.failed_records:
            self.log_signal.emit(
                f"- [{item['status']}] {item['address']} | tokenId={item['token_id']} | 原因: {item['reason']}"
            )

        filename = f"{task_type}_{network.lower()}_problem_addresses.csv"
        try:
            with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=["task", "network", "address", "token_id", "status", "reason"])
                writer.writeheader()
                writer.writerows(self.failed_records)
            self.log_signal.emit(f"[!] 失败/待确认地址已独立导出: {filename}")
        except Exception as e:
            self.log_signal.emit(f"[!] 导出失败地址 CSV 失败: {e}")

    def sleep_with_stop(self, seconds):
        end_at = time.time() + seconds
        while self.is_running.is_set() and time.time() < end_at:
            time.sleep(min(0.2, end_at - time.time()))

    def execute_vote(self, w3, acc, tid, cfg):
        try:
            target = self.parse_vote_target_address()
            data = self.build_vote_calldata(tid, target)
        except Exception as e:
            self.log_signal.emit(f"[!] 请先粘贴正确的投票 Data：{e}")
            self.is_running.clear()
            return "skipped", f"投票 Data 无效: {e}"

        self.log_signal.emit(f"[*] 投票 ID {tid}: 目标地址 {target}，投票权重 100%")
        return self.send_tx(w3, acc, cfg["vote_contract"], data, f"投票 ID {tid}")

    def execute_claim(self, w3, acc, tid, cfg):
        self.log_signal.emit(f"[*] 扫描 ID {tid} 奖励...")

        reward_sources = cfg.get("reward_contracts", [])
        tokens_to_scan = cfg.get("common_tokens", [])

        if not reward_sources or not tokens_to_scan:
            self.log_signal.emit("[!] 警告: config.json 中未配置 reward_contracts 或 common_tokens")
            return "skipped", "config.json 中未配置 reward_contracts 或 common_tokens"

        _bribes, _tokens = [], []
        query_errors = 0

        for src in reward_sources:
            if not self.is_running.is_set():
                break

            src_addr = Web3.to_checksum_address(src)
            contract = w3.eth.contract(address=src_addr, abi=ABI_EARNED)
            found = []

            for t in tokens_to_scan:
                if not self.is_running.is_set():
                    break

                token_addr = Web3.to_checksum_address(t)
                try:
                    earned_amount = contract.functions.earned(token_addr, tid).call()
                    if earned_amount > 0:
                        found.append(token_addr)
                        self.log_signal.emit(
                            f"-> ID {tid}: 在 {src_addr} 发现可领代币 {token_addr} | amount={earned_amount}"
                        )
                    time.sleep(0.1)
                except Exception as e:
                    query_errors += 1
                    self.log_signal.emit(
                        f"-> ID {tid}: 扫描失败 | bribe={src_addr} | token={token_addr} | {e}"
                    )

            if found:
                _bribes.append(src_addr)
                _tokens.append(found)

        if _bribes and self.is_running.is_set():
            voter_c = w3.eth.contract(address=Web3.to_checksum_address(cfg["vote_contract"]), abi=ABI_CLAIM)
            tx_data = voter_c.encode_abi("claimBribes", [_bribes, _tokens, tid])
            return self.send_tx(w3, acc, cfg["vote_contract"], tx_data, f"领取奖励 ID {tid}")

        if not self.is_running.is_set():
            return "skipped", "任务已手动中止"

        if query_errors > 0:
            self.log_signal.emit(f"-> ID {tid}: [扫描异常] 未发现可领取奖励，但有 {query_errors} 个查询失败")
            return "failed", f"扫描异常：{query_errors} 个查询失败"

        self.log_signal.emit(f"-> ID {tid}: 无余额。")
        return "skipped", "无可领取余额"

    def execute_rebase(self, w3, acc, tid, net):
        rebase_addr = "0x227f65131a261548b057215bb1d5ab2997964c7d" if net == "Base" else "0x9d4736ec60715e71afe72973f7885dcbc21ea99b"
        data = "0x379607f5" + hex(tid)[2:].zfill(64)
        return self.send_tx(w3, acc, rebase_addr, data, f"Rebase ID {tid}")

    def send_tx(self, w3, acc, to, data, desc):
        """
        默认最多尝试 3 次。
        - receipt.status == 1：成功，停止。
        - receipt.status == 0：链上失败/回滚，不重试。
        - 其他异常/超时/RPC问题：重试，且每次都重新读取 nonce、gasPrice、estimate_gas。
        """
        max_attempts = 3
        last_reason = "未知错误"
        tx_hashes = []

        for attempt in range(1, max_attempts + 1):
            if not self.is_running.is_set():
                return "skipped", "任务已手动中止"

            try:
                tx = {
                    'to': Web3.to_checksum_address(to),
                    'value': 0,
                    'data': data,
                    'from': acc.address,
                    # 每次尝试都重新读取 pending nonce，避免使用过期 nonce
                    'nonce': w3.eth.get_transaction_count(acc.address, 'pending'),
                    # 每次尝试都重新读取最新 gas price
                    'gasPrice': w3.eth.gas_price,
                    'chainId': w3.eth.chain_id,
                }

                gas = self.gas_input.text().strip()
                if gas:
                    tx['gas'] = int(gas)
                else:
                    # 每次尝试都重新 estimate gas，再乘 1.2
                    tx['gas'] = int(w3.eth.estimate_gas(tx) * 1.2)

                if attempt > 1:
                    self.log_signal.emit(
                        f"-> {desc}: [重试 {attempt}/{max_attempts}] nonce={tx['nonce']} gasPrice={tx['gasPrice']} gas={tx['gas']}"
                    )

                signed = w3.eth.account.sign_transaction(tx, acc.key)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                tx_hex = tx_hash.hex()
                tx_hashes.append(tx_hex)

                self.log_signal.emit(f"-> {desc}: [已广播] {tx_hex}，等待链上确认...")

                receipt = w3.eth.wait_for_transaction_receipt(
                    tx_hash,
                    timeout=self.receipt_timeout,
                    poll_latency=2,
                )

                if receipt.status == 1:
                    self.log_signal.emit(
                        f"-> {desc}: [链上成功] {tx_hex} | block={receipt.blockNumber} | gasUsed={receipt.gasUsed}"
                    )
                    return "success", f"链上成功 | tx={tx_hex} | attempts={attempt}"

                # status == 0 是明确链上回滚，不重试
                self.log_signal.emit(
                    f"-> {desc}: [链上失败，不重试] {tx_hex} | block={receipt.blockNumber} | gasUsed={receipt.gasUsed}"
                )
                return "failed", f"链上失败/交易回滚 | tx={tx_hex} | attempts={attempt}"

            except TimeExhausted:
                last_reason = f"超时未确认：{self.receipt_timeout}s 内未拿到回执"
                self.log_signal.emit(f"-> {desc}: [超时] 第 {attempt}/{max_attempts} 次失败：{last_reason}")

                if attempt < max_attempts:
                    time.sleep(1)
                    continue

                reason = f"{last_reason} | attempts={max_attempts} | tx_hashes={';'.join(tx_hashes)}"
                self.log_signal.emit(f"-> {desc}: [最终失败/待确认] {reason}")
                return "pending", reason

            except Exception as e:
                err_text = str(e)
                if isinstance(e.args, tuple) and e.args:
                    err_text = " | ".join(str(x) for x in e.args if x)
                last_reason = err_text
                self.log_signal.emit(f"-> {desc}: [失败] 第 {attempt}/{max_attempts} 次：{err_text}")

                if attempt < max_attempts:
                    time.sleep(1)
                    continue

                reason = f"{last_reason} | attempts={max_attempts} | tx_hashes={';'.join(tx_hashes)}"
                self.log_signal.emit(f"-> {desc}: [最终失败] {reason}")
                return "failed", reason


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Ve33Tools()
    window.show()
    sys.exit(app.exec())
