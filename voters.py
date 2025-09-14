import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from web3 import Web3
import json
import re
import threading
import csv

# 合约地址
OP_CONTRACT = "0x41c914ee0c7e1a5edcd0295623e6dc557b5abf3c"
BASE_CONTRACT = "0x16613524e02ad97eDfeF371bC883F2F5d6C480A5"

# RPC 端点
OP_RPC = "https://mainnet.optimism.io"
BASE_RPC = "https://mainnet.base.org"

# 函数选择器
FUNCTION_SELECTOR = "0x7ac09bf7"

# 固定金额 (100 * 10^18)
AMOUNT = 100000000000000000000
AMOUNT_HEX = hex(AMOUNT)

# 解析 calldata 的函数
def parse_vote_data(data):
    if not data.lower().startswith('0x7ac09bf7'):
        return None
    data = data[2:] if data.startswith('0x') else data
    data = data[8:]  # 移除选择器 '7ac09bf7'
    # 现在 data 是参数的 hex 字符串
    offset_addr = data[64:128]
    if offset_addr != '0' * 60 + '0060':
        return None
    offset_amount = data[128:192]
    if offset_amount != '0' * 60 + '00a0':
        return None
    # 地址数组从 192 hex 字符开始
    addr_start = 192
    length_hex = data[addr_start:addr_start+64]
    length = int(length_hex, 16)
    if length != 1:
        return None
    # 地址从 addr_start + 64 开始
    addr_hex = data[addr_start + 64 : addr_start + 128]
    address = '0x' + addr_hex[24:]
    return address

# 构建 calldata
def build_calldata(vote_id, address, amount_hex):
    vote_id_hex = hex(vote_id)[2:].zfill(64)
    address_padded = "000000000000000000000000" + address[2:]
    amount_padded = amount_hex[2:].zfill(64)
    calldata = (
        FUNCTION_SELECTOR +
        vote_id_hex +
        "0000000000000000000000000000000000000000000000000000000000000060" +  # offset addresses
        "00000000000000000000000000000000000000000000000000000000000000a0" +  # offset amounts
        "0000000000000000000000000000000000000000000000000000000000000001" +  # addresses length 1
        address_padded +
        "0000000000000000000000000000000000000000000000000000000000000001" +  # amounts length 1
        amount_padded
    )
    return calldata

# 加载 vote.txt
def load_votes(log_text):
    try:
        with open("vote.txt", "r") as f:
            lines = f.readlines()
        votes = []
        for line in lines:
            line = line.strip()
            if "|" in line:
                private_key, vote_id_str = line.split("|", 1)
                vote_id = int(vote_id_str.strip())
                votes.append((private_key.strip(), vote_id))
        log_text.insert(tk.END, f"加载 {len(votes)} 条记录\n")
        return votes
    except Exception as e:
        messagebox.showerror("错误", f"加载 vote.txt 失败: {e}")
        return []

# 发送交易并检查结果
def send_vote(private_key, vote_id, address, w3, contract_address, user_gas):
    try:
        account = w3.eth.account.from_key(private_key)
        nonce = w3.eth.get_transaction_count(account.address)
        
        tx = {
            'to': w3.to_checksum_address(contract_address),
            'value': 0,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
            'data': build_calldata(vote_id, address, AMOUNT_HEX),
            'chainId': w3.eth.chain_id
        }
        estimated_gas = w3.eth.estimate_gas(tx)
        if user_gas:
            tx['gas'] = user_gas
        else:
            tx['gas'] = int(estimated_gas * 1.2)
        
        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt['status'] == 1:
            return f"成功: {tx_hash.hex()}"
        else:
            return f"失败: {tx_hash.hex()} - 原因: 交易回滚"
    except Exception as e:
        return f"错误: {str(e)}"

# 获取当前估算 gas limit 的函数（使用有效 dummy calldata）
def get_estimated_gas_limit(network):
    if network == "OP":
        w3 = Web3(Web3.HTTPProvider(OP_RPC))
        contract = OP_CONTRACT
    else:
        w3 = Web3(Web3.HTTPProvider(BASE_RPC))
        contract = BASE_CONTRACT
    if w3.is_connected():
        # 使用有效的 dummy calldata（从用户例子）
        dummy_data = '0x7ac09bf70000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000000000000006000000000000000000000000000000000000000000000000000000000000000a000000000000000000000000000000000000000000000000000000000000000010000000000000000000000004dc22588ade05c40338a9d95a6da9dcee68bcd6000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000056bc75e2d63100000'
        dummy_tx = {
            'to': w3.to_checksum_address(contract),
            'value': 0,
            'data': dummy_data,
        }
        try:
            estimated_gas = w3.eth.estimate_gas(dummy_tx)
            return f"{estimated_gas} (留空默认值)"
        except:
            # 如果仍失败，返回典型值
            if network == "OP":
                return "200000 (典型值)"
            else:
                return "250000 (典型值)"
    else:
        return "无法连接"

# GUI 主类
class VoteGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("批量投票脚本")
        self.root.geometry("600x500")
        self.root.configure(bg="#f0f0f0")
        
        # Data 输入
        tk.Label(root, text="粘贴 Data:", bg="#f0f0f0", font=("Arial", 12)).pack(pady=5)
        self.data_entry = tk.Text(root, height=5, width=70)
        self.data_entry.pack(pady=5)
        self.data_entry.bind("<KeyRelease>", self.auto_parse_data)  # 绑定键盘释放事件自动解析
        
        # 地址标签
        parse_frame = tk.Frame(root, bg="#f0f0f0")
        self.address_label = tk.Label(parse_frame, text="投票对象地址: 未解析", bg="#f0f0f0", font=("Arial", 10))
        self.address_label.pack(side=tk.LEFT)
        parse_frame.pack(pady=5)
        
        # 网络选择一行，包括 Gas Limit 和当前估算 Gas Limit
        network_frame = tk.Frame(root, bg="#f0f0f0")
        tk.Label(network_frame, text="选择网络:", bg="#f0f0f0", font=("Arial", 12)).pack(side=tk.LEFT, padx=10)
        self.network_var = tk.StringVar(value="OP")
        self.network_var.trace("w", self.update_gas_limit)  # 当网络变化时更新 gas limit
        tk.Radiobutton(network_frame, text="OP", variable=self.network_var, value="OP", bg="#f0f0f0").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(network_frame, text="Base", variable=self.network_var, value="Base", bg="#f0f0f0").pack(side=tk.LEFT, padx=5)
        tk.Label(network_frame, text="Gas Limit:", bg="#f0f0f0", font=("Arial", 12)).pack(side=tk.LEFT, padx=10)
        self.gas_entry = tk.Entry(network_frame, width=10)
        self.gas_entry.pack(side=tk.LEFT, padx=5)
        # 默认留空，使用120%估算
        self.gas_limit_label = tk.Label(network_frame, text="当前 Gas Limit: 计算中...", bg="#f0f0f0", font=("Arial", 10))
        self.gas_limit_label.pack(side=tk.LEFT, padx=10)
        network_frame.pack(pady=5)
        
        # 批量投票按钮
        tk.Button(root, text="开始批量投票", command=self.batch_vote, font=("Arial", 12)).pack(pady=10)
        
        # 日志
        tk.Label(root, text="日志:", bg="#f0f0f0", font=("Arial", 12)).pack(pady=5)
        self.log_text = scrolledtext.ScrolledText(root, height=10, width=70)
        self.log_text.pack(pady=5, fill=tk.BOTH, expand=True)
        
        # 默认加载 vote.txt
        self.votes = load_votes(self.log_text)
        
        # 初始化 gas limit
        self.update_gas_limit()
    
    def auto_parse_data(self, event=None):
        self.parse_data()
    
    def parse_data(self):
        data = self.data_entry.get("1.0", tk.END).strip()
        address = parse_vote_data(data)
        if address:
            self.address_label.config(text=f"解析地址: {address}")
            self.log_text.insert(tk.END, f"解析成功: {address}\n")
        else:
            self.address_label.config(text="解析地址: 失败")
            self.log_text.insert(tk.END, "解析失败: 数据格式不匹配\n")
    
    def update_gas_limit(self, *args):
        def fetch_gas_limit():
            network = self.network_var.get()
            gas_limit_str = get_estimated_gas_limit(network)
            self.gas_limit_label.config(text=f"当前 Gas Limit: {gas_limit_str}")
        
        threading.Thread(target=fetch_gas_limit).start()  # 使用线程避免阻塞 UI
    
    def batch_vote(self):
        if not self.votes:
            messagebox.showwarning("警告", "vote.txt 中无记录或加载失败")
            return
        
        address_text = self.address_label.cget("text")
        if "未解析" in address_text or "失败" in address_text:
            messagebox.showwarning("警告", "请先解析 Data 获取地址")
            return
        
        address = address_text.split(": ")[1]
        
        try:
            user_gas = int(self.gas_entry.get()) if self.gas_entry.get().strip() else None
        except ValueError:
            user_gas = None
            self.log_text.insert(tk.END, "Gas Limit 输入无效，使用估算值的120%\n")
        
        network = self.network_var.get()
        if network == "OP":
            w3 = Web3(Web3.HTTPProvider(OP_RPC))
            contract = OP_CONTRACT
        else:
            w3 = Web3(Web3.HTTPProvider(BASE_RPC))
            contract = BASE_CONTRACT
        
        if not w3.is_connected():
            messagebox.showerror("错误", f"无法连接到 {network} 网络")
            return
        
        self.log_text.insert(tk.END, f"开始批量投票到 {network} 合约 {contract}\n")
        
        results = []
        for i, (pk, vid) in enumerate(self.votes):
            self.log_text.insert(tk.END, f"处理第 {i+1} 条: 投票ID {vid}\n")
            self.root.update()
            
            result = send_vote(pk, vid, address, w3, contract, user_gas)
            self.log_text.insert(tk.END, f"结果: {result}\n\n")
            results.append((i+1, vid, result))
            self.root.update()
        
        # 在日志中显示表格格式结果
        self.display_results_table(results)
        
        # 输出到 CSV 文件
        self.export_to_csv(results)
    
    def display_results_table(self, results):
        self.log_text.insert(tk.END, "\n投票结果表格:\n")
        self.log_text.insert(tk.END, f"{'序号':<5} {'投票ID':<10} {'结果'}\n")
        self.log_text.insert(tk.END, "-" * 80 + "\n")
        for seq, vid, res in results:
            self.log_text.insert(tk.END, f"{seq:<5} {vid:<10} {res}\n")
        self.log_text.insert(tk.END, "\n")
    
    def export_to_csv(self, results):
        try:
            with open("vote_results.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["序号", "投票ID", "结果"])
                for row in results:
                    writer.writerow(row)
            self.log_text.insert(tk.END, "结果已导出到 vote_results.csv\n")
        except Exception as e:
            self.log_text.insert(tk.END, f"导出 CSV 失败: {e}\n")

if __name__ == "__main__":
    root = tk.Tk()
    app = VoteGUI(root)
    root.mainloop()
