#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aero（新系统）sAERO 批量分配 / 领取 —— Qt 界面版 v3

界面（极简）：
- inputdata 粘贴框：粘贴一笔 allocate 交易的 inputdata，点「解析」提取目标池地址
  （日志显示解析结果，并设为分配目标池；不解析时用默认 WETH/cbBTC 池）。
- 按钮行：分配・试运行 / 分配・执行 / 领取・试运行 / 领取・执行 / 停止，
  同行有地址间隔（随机秒数区间）与「随机打乱」「强投」勾选与 Gas（0=自动估算；实测一笔 allocate 约需 105 万 gas，RPC 估算报错时填 2000000 手动值）。
- 下方为日志框。私钥固定读脚本同目录（或当前目录）的 vote.txt，每次运行前重新读取；
  RPC 固定 mainnet.base.org，不在界面显示。

逻辑（与 aero_allocate_batch.py 一致，均已链上核实）：
- 分配：枚举每钱包全部 sAERO 仓位，全额投目标池，调 Allocator.allocate
  （编码已用两笔真实交易逐字节复刻验证）；链级已全额分配默认跳过（防刷新 47h 冷却），
  勾选「强投」可强制；是否可投以 eth_call 模拟为准。
- 领取：调 Allocator.claimRewards 领手续费（earnedFees）+ 激励（earnedIncentives），
  池与奖励管理器全部按仓位链上分配自动识别，无需设置池/代币合约。
- 新系统没有 rebase，sAERO 面值固定，收益只走领取这条线。
未完成项追加到 aero_allocate_failed.csv。
"""

import csv
import os
import random
import sys
import time
from datetime import datetime, timezone

try:
    from web3 import Web3
    from web3.exceptions import ContractLogicError
except ImportError:
    print("需要 web3:  pip install web3")
    sys.exit(1)

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

# ---------- 已链上核实的地址（Base） ----------
DEFAULT_RPC = "https://mainnet.base.org"
BASE_CHAIN_ID = 8453
ALLOCATOR = "0x49d7d4f17ec56ef8fa04e464af5d1a4942cc31e6"
VOTING_ESCROW = "0xbf7977e1521e9a3032bf7243ee4712f311f13915"
DEFAULT_POOL = "0xabb3fb6659e05847631896cb87a6d1b8bc0c6d8c"  # WETH/cbBTC 池
LEAF_VOTER = "0x382409fad8503fbcdbb27a4211551fa03e884078"
FACTORY_REGISTRY = "0x7b2a2c12dc5ea2a31455952a05031c3e4bb28f3e"
COOLDOWN_SECONDS = 47 * 3600
ALLOC_SELECTOR = "0xf02e634e"  # allocate(...)，已用样本逐字节验证

# web3 的 contract(address=) 只接受 EIP-55 校验和地址，统一在此规范化
ALLOCATOR = Web3.to_checksum_address(ALLOCATOR)
VOTING_ESCROW = Web3.to_checksum_address(VOTING_ESCROW)
DEFAULT_POOL = Web3.to_checksum_address(DEFAULT_POOL)
LEAF_VOTER = Web3.to_checksum_address(LEAF_VOTER)
FACTORY_REGISTRY = Web3.to_checksum_address(FACTORY_REGISTRY)

ALLOC_ABI = [
    {"inputs": [
        {"name": "_tokenId", "type": "uint256"},
        {"components": [
            {"name": "chainId", "type": "uint256"},
            {"name": "delta", "type": "uint128"},
            {"name": "gasLimit", "type": "uint256"},
            {"name": "value", "type": "uint256"}],
         "name": "_chainDispatches", "type": "tuple[]"},
        {"components": [
            {"name": "chainId", "type": "uint256"},
            {"name": "gasLimit", "type": "uint256"},
            {"name": "value", "type": "uint256"},
            {"components": [
                {"name": "gauge", "type": "address"},
                {"name": "allocated", "type": "uint128"},
                {"name": "data", "type": "bytes"}],
             "name": "gauges", "type": "tuple[]"}],
         "name": "_gaugeDispatches", "type": "tuple[]"},
        {"name": "_refundRecipient", "type": "address"}],
     "name": "allocate", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "_tokenId", "type": "uint256"}], "name": "tokenStates",
     "outputs": [{"name": "", "type": "uint128"}, {"name": "", "type": "uint48"},
                 {"name": "", "type": "uint48"}, {"name": "", "type": "bool"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "_tokenId", "type": "uint256"}, {"name": "_chainId", "type": "uint256"}],
     "name": "allocationChainAmounts", "outputs": [{"name": "", "type": "uint128"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [
        {"name": "_tokenId", "type": "uint256"},
        {"components": [
            {"name": "chainId", "type": "uint256"},
            {"name": "gasLimit", "type": "uint256"},
            {"name": "value", "type": "uint256"},
            {"name": "recipient", "type": "address"},
            {"components": [
                {"name": "votingRewardsManager", "type": "address"},
                {"name": "maxCheckpoints", "type": "uint256"}],
             "name": "feeClaims", "type": "tuple[]"},
            {"components": [
                {"name": "votingRewardsManager", "type": "address"},
                {"name": "programId", "type": "uint256"},
                {"name": "maxCheckpoints", "type": "uint256"}],
             "name": "incentiveClaims", "type": "tuple[]"}],
         "name": "_claimRewardsParams", "type": "tuple[]"},
        {"name": "_refundRecipient", "type": "address"}],
     "name": "claimRewards", "outputs": [], "stateMutability": "payable", "type": "function"},
]
VE_ABI = [
    {"inputs": [{"name": "a", "type": "address"}], "name": "balanceOf",
     "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "a", "type": "address"}, {"name": "i", "type": "uint256"}],
     "name": "tokenOfOwnerByIndex", "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "id", "type": "uint256"}], "name": "balanceOfNFT",
     "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
]
LEAF_ABI = [
    {"inputs": [{"name": "_tokenId", "type": "uint256"}], "name": "allocatedGauges",
     "outputs": [{"name": "", "type": "address[]"}], "stateMutability": "view", "type": "function"},
]
FR_ABI = [
    {"inputs": [{"name": "_gauge", "type": "address"}], "name": "gaugeToRewards",
     "outputs": [{"name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
]
MGR_ABI = [
    {"inputs": [{"name": "_tokenId", "type": "uint256"}, {"name": "_maxCheckpoints", "type": "uint256"}],
     "name": "earnedFees", "outputs": [{"name": "", "type": "uint256"}, {"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "_tokenId", "type": "uint256"}, {"name": "_programId", "type": "uint256"},
                {"name": "_maxCheckpoints", "type": "uint256"}],
     "name": "earnedIncentives", "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "incentiveCount", "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "MAX_CHECKPOINT_ITERATIONS", "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "token0", "outputs": [{"name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "token1", "outputs": [{"name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"},
]
ERC20_MIN_ABI = [
    {"inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}],
     "stateMutability": "view", "type": "function"},
]


def load_keys(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key = line.split("|")[0].strip()
            if not key.startswith("0x"):
                key = "0x" + key
            out.append((ln, key))
    return out


def find_vote_txt():
    """私钥文件固定为 vote.txt：优先脚本同目录，其次当前工作目录。"""
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "vote.txt"), os.path.join(os.getcwd(), "vote.txt")):
        if os.path.exists(cand):
            return cand
    return None


def fmt_ts(ts):
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _comp(entry, key, idx):
    return entry[key] if isinstance(entry, dict) else entry[idx]


def parse_allocate_inputdata(raw):
    """解析一笔 allocate 的 inputdata，返回 (tokenId, [(池地址, 金额), ...])。
    失败抛 ValueError（带中文原因）。"""
    s = "".join(raw.split()).lower()
    if s.startswith("0x"):
        s = s[2:]
    if len(s) < 8:
        raise ValueError("内容太短，不像 inputdata")
    if "0x" + s[:8] != ALLOC_SELECTOR:
        raise ValueError(f"函数选择器是 0x{s[:8]}，不是 allocate 的 {ALLOC_SELECTOR}——请粘贴一笔「投票/分配」交易的 inputdata")
    try:
        data = bytes.fromhex(s)
    except ValueError:
        raise ValueError("不是合法的十六进制字符串")
    w3 = Web3()
    contract = w3.eth.contract(address=ALLOCATOR, abi=ALLOC_ABI)
    try:
        _fn, params = contract.decode_function_input(data)
    except Exception as e:
        raise ValueError(f"解码失败: {str(e)[:120]}")
    pools = []
    for entry in params["_gaugeDispatches"]:
        gauges = _comp(entry, "gauges", 3)
        for g in gauges:
            addr = _comp(g, "gauge", 0)
            amt = _comp(g, "allocated", 1)
            pools.append((Web3.to_checksum_address(addr), amt))
    if not pools:
        raise ValueError("解码成功但里面没有任何目标池")
    return params["_tokenId"], pools


class Worker(QThread):
    log = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, mode, execute, keys, pool, force, iv_min, iv_max, gas_limit=0):
        super().__init__()
        self.mode = mode            # "allocate" | "claim"
        self.execute = execute
        self.keys = keys            # [(行号, 私钥)]（顺序可能已打乱）
        self.pool = pool
        self.force = force
        self.iv_min = iv_min        # 地址间隔随机区间（秒）
        self.iv_max = iv_max
        self.gas_limit = gas_limit  # 0 = 自动估算
        self._stop = False
        self.results = []

    def stop(self):
        self._stop = True

    # ---------- 基础工具 ----------
    def send_tx(self, w3, key, fn):
        acct = w3.eth.account.from_key(key)
        params = {
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
            "chainId": 8453,
        }
        manual = bool(self.gas_limit)
        if manual:
            params["gas"] = int(self.gas_limit)
        try:
            tx = fn.build_transaction(params)
            if not manual:
                if "gas" in tx:
                    tx["gas"] = int(tx["gas"] * 1.25) + 21000
                else:
                    tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.25) + 21000
        except Exception as e:
            if "gas" in str(e).lower():
                raise Exception(f"{str(e)[:140]}（提示：这家 RPC 的自动估算会失败，去界面 Gas 框填手动值，如 2000000，再重试）")
            raise
        signed = w3.eth.account.sign_transaction(tx, key)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        txh = w3.eth.send_raw_transaction(raw)
        rcpt = w3.eth.wait_for_transaction_receipt(txh, timeout=300)
        return txh.hex(), rcpt.status == 1

    @staticmethod
    def simulate(fn, owner):
        try:
            fn.call({"from": owner})
            return True, ""
        except ContractLogicError as e:
            return False, str(e)[:160]
        except Exception as e:
            return False, str(e)[:160]

    @staticmethod
    def read_retry(fn, want, tries=6, wait=1.5):
        last = None
        for _ in range(tries):
            last = fn()
            if last == want:
                return last
            time.sleep(wait)
        return last

    def enum_token_ids(self, ve, owner):
        n = ve.functions.balanceOf(owner).call()
        return [ve.functions.tokenOfOwnerByIndex(owner, i).call() for i in range(n)]

    # ---------- 主流程 ----------
    def run(self):
        w3 = Web3(Web3.HTTPProvider(DEFAULT_RPC, request_kwargs={"timeout": 30}))
        if not w3.is_connected():
            self.log.emit("RPC 连接失败，请稍后重试")
            self.finished_all.emit()
            return
        alloc = w3.eth.contract(address=ALLOCATOR, abi=ALLOC_ABI)
        ve = w3.eth.contract(address=VOTING_ESCROW, abi=VE_ABI)
        total = len(self.keys)
        for idx, (ln, key) in enumerate(self.keys):
            if self._stop:
                self.log.emit("已停止（未处理的地址未动）")
                break
            try:
                owner = w3.eth.account.from_key(key).address
            except Exception as e:
                self.log.emit(f"[第{ln}行] 私钥无效: {str(e)[:80]}")
                continue
            self.log.emit(f"\n=== [{idx+1}/{total}] {owner}（第{ln}行）===")
            try:
                token_ids = self.enum_token_ids(ve, owner)
            except Exception as e:
                self.log.emit(f"  枚举 sAERO 失败: {str(e)[:120]}")
                self.results.append((owner, "-", 0, f"枚举失败: {str(e)[:100]}"))
                continue
            self.log.emit(f"  sAERO 仓位 {len(token_ids)} 个: {token_ids if token_ids else ''}")
            if self.mode == "allocate":
                self.do_allocate(w3, alloc, ve, key, owner, token_ids)
            else:
                self.do_claim(w3, alloc, ve, key, owner, token_ids)
            if self._stop:
                self.log.emit("已停止")
                break
            if idx < total - 1 and self.iv_max > 0:
                time.sleep(random.uniform(self.iv_min, self.iv_max))
        self.finish()
        self.finished_all.emit()

    def finish(self):
        self.log.emit("\n===== 汇总 =====")
        bad = [r for r in self.results if any(k in r[3] for k in ("失败", "未通过", "不符"))]
        for owner, tid, amt, note in self.results:
            self.log.emit(f"{owner} | tokenId {tid} | {amt} | {note}")
        if bad:
            out = "aero_allocate_failed.csv"
            exists = os.path.exists(out)
            with open(out, "a", newline="", encoding="utf-8") as f:
                wcsv = csv.writer(f)
                if not exists:
                    wcsv.writerow(["address", "tokenId", "amount", "note"])
                for r in bad:
                    wcsv.writerow(r)
            self.log.emit(f"未完成 {len(bad)} 项已追加到 {out}")
        self.log.emit("全部完成。" if self.execute else "试运行完成（未发任何交易）。")

    # ---------- 分配 ----------
    def do_allocate(self, w3, alloc, ve, key, owner, token_ids):
        now = int(time.time())
        for tid in token_ids:
            if self._stop:
                return
            try:
                amount = ve.functions.balanceOfNFT(tid).call()
                current = alloc.functions.allocationChainAmounts(tid, BASE_CHAIN_ID).call()
                state = alloc.functions.tokenStates(tid).call()
                last_ts = state[2]
            except Exception as e:
                self.log.emit(f"  tokenId {tid}: 读取状态失败 {str(e)[:100]}")
                self.results.append((owner, tid, 0, f"读取失败: {str(e)[:100]}"))
                continue
            cool_note = ""
            if last_ts:
                until = last_ts + COOLDOWN_SECONDS
                cool_note = (f" | 上次分配 {fmt_ts(last_ts)}，冷却约至 {fmt_ts(until)}"
                             + ("（已过）" if until <= now else "（未到期）"))
            self.log.emit(f"  tokenId {tid}: 可分配 {amount/1e18:.6f} | 当前链级已分配 {current/1e18:.6f}{cool_note}")
            if amount == 0:
                self.results.append((owner, tid, 0, "余额为 0，跳过"))
                continue
            if current >= amount and not self.force:
                self.results.append((owner, tid, amount / 1e18, "链级已全额分配，跳过（勾选强投可强投）"))
                self.log.emit("    链级已全额分配，跳过（避免无意义刷新冷却）")
                continue
            delta = amount - current
            fn = alloc.functions.allocate(
                tid,
                [(BASE_CHAIN_ID, delta, 0, 0)],
                [(BASE_CHAIN_ID, 0, 0, [(self.pool, amount, b"")])],
                owner,
            )
            ok_sim, err = self.simulate(fn, owner)
            if not ok_sim:
                self.log.emit(f"    模拟未通过（多半是冷却未到）: {err}")
                self.results.append((owner, tid, amount / 1e18, f"模拟未通过: {err}"))
                continue
            if not self.execute:
                self.log.emit(f"    [试运行] 模拟通过 —— 将把 {amount/1e18:.6f} 全额投给目标池（delta={delta/1e18:.6f}）")
                self.results.append((owner, tid, amount / 1e18, "dry-run 可分配"))
                continue
            try:
                txh, ok_tx = self.send_tx(w3, key, fn)
                self.log.emit(f"    allocate 已发送 tx={txh} status={'成功' if ok_tx else '失败'}")
                after = self.read_retry(
                    lambda: alloc.functions.allocationChainAmounts(tid, BASE_CHAIN_ID).call(), amount)
                if ok_tx and after == amount:
                    self.log.emit("    ✓ 分配已生效")
                    self.results.append((owner, tid, amount / 1e18, "已分配"))
                else:
                    self.results.append((owner, tid, amount / 1e18, f"tx 后链级分配额={after/1e18:.6f}，与目标不符"))
            except Exception as e:
                self.results.append((owner, tid, amount / 1e18, f"发送失败: {str(e)[:120]}"))

    # ---------- 领取 ----------
    def do_claim(self, w3, alloc, ve, key, owner, token_ids):
        leaf = w3.eth.contract(address=LEAF_VOTER, abi=LEAF_ABI)
        freg = w3.eth.contract(address=FACTORY_REGISTRY, abi=FR_ABI)
        sym_cache = {}

        def sym(addr):
            if addr not in sym_cache:
                try:
                    sym_cache[addr] = w3.eth.contract(address=addr, abi=ERC20_MIN_ABI).functions.symbol().call()
                except Exception:
                    sym_cache[addr] = addr[:10] + "…"
            return sym_cache[addr]

        for tid in token_ids:
            if self._stop:
                return
            try:
                gauges = leaf.functions.allocatedGauges(tid).call()
            except Exception as e:
                self.results.append((owner, tid, 0, f"领取-读分配池失败: {str(e)[:100]}"))
                continue
            if not gauges:
                self.log.emit(f"  tokenId {tid}: 无分配中的池，跳过")
                self.results.append((owner, tid, 0, "领取-无分配，跳过"))
                continue
            fee_claims, inc_claims, desc = [], [], []
            for g in gauges:
                try:
                    mgr_addr = freg.functions.gaugeToRewards(g).call()
                    if int(mgr_addr, 16) == 0:
                        self.log.emit(f"  tokenId {tid} 池 {g}: 无 rewards manager，跳过")
                        continue
                    mgr = w3.eth.contract(address=mgr_addr, abi=MGR_ABI)
                    try:
                        max_cp = mgr.functions.MAX_CHECKPOINT_ITERATIONS().call()
                    except Exception:
                        max_cp = 1000
                    f0, f1 = mgr.functions.earnedFees(tid, max_cp).call()
                    if f0 or f1:
                        fee_claims.append((mgr_addr, max_cp))
                        t0 = mgr.functions.token0().call()
                        t1 = mgr.functions.token1().call()
                        desc.append(f"手续费 {f0/1e18:.6f} {sym(t0)} + {f1/1e18:.6f} {sym(t1)}（池 {g[:10]}…）")
                    for pid in range(mgr.functions.incentiveCount().call()):
                        amt = mgr.functions.earnedIncentives(tid, pid, max_cp).call()
                        if amt > 0:
                            inc_claims.append((mgr_addr, pid, max_cp))
                            desc.append(f"激励 program {pid}: {amt/1e18:.6f}（池 {g[:10]}…）")
                except Exception as e:
                    self.log.emit(f"  tokenId {tid} 池 {g}: 读待领奖励失败 {str(e)[:100]}")
                    self.results.append((owner, tid, 0, f"领取-读待领失败: {str(e)[:100]}"))
            if not fee_claims and not inc_claims:
                self.log.emit(f"  tokenId {tid}: 无可领奖励")
                self.results.append((owner, tid, 0, "领取-无可领奖励"))
                continue
            self.log.emit(f"  tokenId {tid} 可领: " + "；".join(desc))
            fn = alloc.functions.claimRewards(
                tid, [(BASE_CHAIN_ID, 0, 0, owner, fee_claims, inc_claims)], owner)
            ok_sim, err = self.simulate(fn, owner)
            if not ok_sim:
                self.log.emit(f"    模拟未通过: {err}")
                self.results.append((owner, tid, 0, f"领取-模拟未通过: {err}"))
                continue
            if not self.execute:
                self.log.emit("    [试运行] 模拟通过 —— 执行时将派发领取")
                self.results.append((owner, tid, 0, "领取-dry-run 可领取"))
                continue
            try:
                txh, ok_tx = self.send_tx(w3, key, fn)
                self.log.emit(f"    claimRewards 已发送 tx={txh} status={'成功' if ok_tx else '失败'}")
                if not ok_tx:
                    self.results.append((owner, tid, 0, "领取-tx 失败"))
                    continue
                time.sleep(30)  # 处理异步，等一会再复读确认
                still = 0
                for (mgr_addr, max_cp) in fee_claims:
                    mgr = w3.eth.contract(address=mgr_addr, abi=MGR_ABI)
                    a0, a1 = mgr.functions.earnedFees(tid, max_cp).call()
                    still += a0 + a1
                if still == 0:
                    self.log.emit("    ✓ 已处理，奖励应已到账（激励部分请看钱包余额）")
                    self.results.append((owner, tid, 0, "已领取"))
                else:
                    self.results.append((owner, tid, 0, "已派发，处理中"))
            except Exception as e:
                self.results.append((owner, tid, 0, f"领取-发送失败: {str(e)[:120]}"))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aero sAERO 批量分配 / 领取 v3")
        self.resize(1020, 680)
        self.worker = None
        self.target_pool = DEFAULT_POOL

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # inputdata 粘贴框（显示）：粘贴一笔 allocate 交易的 inputdata 解析目标池
        row = QHBoxLayout()
        row.addWidget(QLabel("inputdata:"))
        self.inputdata_edit = QTextEdit()
        self.inputdata_edit.setPlaceholderText("粘贴一笔「投票/分配」交易的 inputdata（0x 开头），点右侧解析，目标池会显示在日志里")
        self.inputdata_edit.setFixedHeight(56)
        row.addWidget(self.inputdata_edit, 1)
        btn_parse = QPushButton("解析目标池")
        btn_parse.clicked.connect(self.parse_inputdata)
        row.addWidget(btn_parse)
        layout.addLayout(row)

        # 按钮行：运行/执行 + 间隔 + 打乱/强投
        row = QHBoxLayout()
        self.btn_alloc_dry = QPushButton("分配・试运行")
        self.btn_alloc_dry.clicked.connect(lambda: self.start_task("allocate", False))
        row.addWidget(self.btn_alloc_dry)
        self.btn_alloc_exec = QPushButton("分配・执行")
        self.btn_alloc_exec.clicked.connect(lambda: self.start_task("allocate", True))
        row.addWidget(self.btn_alloc_exec)
        self.btn_claim_dry = QPushButton("领取・试运行")
        self.btn_claim_dry.clicked.connect(lambda: self.start_task("claim", False))
        row.addWidget(self.btn_claim_dry)
        self.btn_claim_exec = QPushButton("领取・执行")
        self.btn_claim_exec.clicked.connect(lambda: self.start_task("claim", True))
        row.addWidget(self.btn_claim_exec)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_task)
        row.addWidget(self.btn_stop)
        row.addWidget(QLabel("间隔"))
        self.iv_min = QSpinBox()
        self.iv_min.setRange(0, 600)
        self.iv_min.setValue(1)
        row.addWidget(self.iv_min)
        row.addWidget(QLabel("~"))
        self.iv_max = QSpinBox()
        self.iv_max.setRange(0, 600)
        self.iv_max.setValue(5)
        row.addWidget(self.iv_max)
        row.addWidget(QLabel("秒"))
        self.shuffle_check = QCheckBox("随机打乱")
        self.shuffle_check.setChecked(True)
        row.addWidget(self.shuffle_check)
        self.force_check = QCheckBox("强投")
        row.addWidget(self.force_check)
        row.addWidget(QLabel("Gas"))
        self.gas_spin = QSpinBox()
        self.gas_spin.setRange(0, 30000000)
        self.gas_spin.setSingleStep(100000)
        self.gas_spin.setValue(0)
        self.gas_spin.setSpecialValueText("自动")
        self.gas_spin.setFixedWidth(105)
        row.addWidget(self.gas_spin)
        layout.addLayout(row)

        # 日志框（占满剩余空间）
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Menlo", 11))
        layout.addWidget(self.log_box, 1)

        self.action_buttons = [self.btn_alloc_dry, self.btn_alloc_exec,
                               self.btn_claim_dry, self.btn_claim_exec]

        self.log("界面 v3 已加载（带自定义 Gas：显示「自动」= 自动估算）")
        self.log(f"默认目标池: {DEFAULT_POOL}（WETH/cbBTC 池；粘贴 inputdata 解析可更换）")
        path = find_vote_txt()
        if path:
            try:
                n = len(load_keys(path))
                self.log(f"已找到私钥文件 {path}：{n} 个地址（每次运行前会重新读取）")
            except Exception as e:
                self.log(f"vote.txt 读取失败: {str(e)[:120]}")
        else:
            self.log("⚠ 未找到 vote.txt：请把 vote.txt 放在脚本同目录，然后重新打开本程序")

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.append(f"[{ts}] {msg}")

    def parse_inputdata(self):
        raw = self.inputdata_edit.toPlainText().strip()
        if not raw:
            self.log("inputdata 框是空的：先粘贴一笔 allocate 交易的 inputdata")
            return
        try:
            tid, pools = parse_allocate_inputdata(raw)
        except ValueError as e:
            self.log(f"解析失败：{e}")
            return
        self.target_pool = pools[0][0]
        detail = "；".join(f"{addr}（{amt/1e18:.4f}）" for addr, amt in pools)
        self.log(f"✓ 解析成功（样本 tokenId {tid}）：目标池 = {detail} —— 已设为分配目标池")

    def start_task(self, mode, execute):
        path = find_vote_txt()
        if not path:
            QMessageBox.warning(self, "未找到 vote.txt", "请把 vote.txt 放在脚本同目录")
            return
        try:
            keys = load_keys(path)
        except Exception as e:
            QMessageBox.warning(self, "vote.txt 读取失败", str(e)[:200])
            return
        if not keys:
            QMessageBox.warning(self, "vote.txt 为空", "vote.txt 里没有可用的私钥行")
            return
        if self.shuffle_check.isChecked():
            keys = list(keys)
            random.shuffle(keys)
        iv_min = min(self.iv_min.value(), self.iv_max.value())
        iv_max = max(self.iv_min.value(), self.iv_max.value())
        if execute:
            action = "分配" if mode == "allocate" else "领取"
            extra = f"\n目标池: {self.target_pool}" if mode == "allocate" else ""
            if QMessageBox.question(
                    self, "确认执行",
                    f"将对 {len(keys)} 个地址执行【{action}】并发送真实交易{extra}，继续？") != QMessageBox.StandardButton.Yes:
                return
        gas_val = self.gas_spin.value()
        self.worker = Worker(mode, execute, keys, self.target_pool,
                             self.force_check.isChecked(), iv_min, iv_max, gas_val)
        self.worker.log.connect(self.log)
        self.worker.finished_all.connect(self.task_done)
        for b in self.action_buttons:
            b.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log(f"开始{'领取' if mode == 'claim' else '分配'}（{'执行' if execute else '试运行'}）：{len(keys)} 个地址"
                 + ("，顺序已随机打乱" if self.shuffle_check.isChecked() else "")
                 + (f"，目标池 {self.target_pool}" if mode == "allocate" else "；池与奖励合约按各仓位链上分配自动识别")
                 + (f"，地址间隔 {iv_min}~{iv_max} 秒随机" if iv_max > 0 else "")
                 + (f"，Gas 手动 {gas_val:,}" if gas_val > 0 else "，Gas 自动估算"))
        self.worker.start()

    def stop_task(self):
        if self.worker:
            self.worker.stop()
            self.log("正在停止（当前地址处理完即停）…")
            self.btn_stop.setEnabled(False)

    def task_done(self):
        for b in self.action_buttons:
            b.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.worker = None


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
