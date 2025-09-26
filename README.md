# VE33_tools
支持op网络的velo和base的aero批量投票,批量领取奖励。批量领取奖励当前仅配置了BASE的AERO项目并测试通过。OP的VELO代码还没完善

Supports batch voting for OP's Velo and Base's Aero, and batch  claim rewards。Currently, only BASE's AERO project has been configured and tested for batch rewards. OP's VELO code is not yet complete.

## 无责声明：本程序为明文代码，运行前请先审核代码安全性。确定使用后，运行时产生任何损失均与本代码无关
## Disclaimer: This program is plain text code. Please review the code security before running it. After confirming your use, any losses incurred during operation are not related to this code.

## 1 安装支持环境
安装 Python，tkinter（GUI 库）， web3（区块链交互库）

    sudo apt update && sudo apt install python3 python3-pip
    sudo apt install python3-tk
    pip3 install web3

## 2 准备私匙文件
程序读取vote.txt内容，一行一个。格式为 私匙｜NFTID 类似如下：

0x123456....|1234

## 3 config.json配置说明

经过研究，BASE链的AERO领取投票奖励，是通过投票合约0x16613524e02ad97eDfeF371bC883F2F5d6C480A5调用其他代币奖励合约进行领取。但投票合约上没有查询所有奖励代币和数量的功能，只有领取奖励功能。查询投票所得代币和数量是在调用其他合约来完成。因此需要在config.json配置已知的调用合约，包括BribeVotingReward和FeesVotingReward。把已知的调用合约补充到config.json，命名如下截图所示。并且每个地址所得的投票奖励代币和数量都不同的话，需要调用合约来获取并传递给主投票合约领取。

因为没有找到查询地址的所有奖励代币和数量的合约函数，只能指定领取代币合约地址。比如2025-09-17投票给synd，那么奖励的是synd对应在代币合约填写synd的合约地址：0x11dc28d01984079b7efe7763b533e6ed9e3722b9.如果查询到指定代币在所有 BribeVotingReward 和 FeesVotingReward 合约中都没有可领取金额（earned 函数返回 0），程序会返回 "无领取金额" 并记录在日志中，然后自动继续处理下一个地址。所以需要尽量完善补充config.json中的BribeVotingReward 和 FeesVotingReward 合约地址。

当前仅支持领取一种代币合约地址，如果投票奖励中包括多种代币，需要运行多次。（这个一次领取多种代币奖励功能等后面补充完善了。）

如果在领取过程出现RPC错误，把config.json的RPC修改为其他，建议采用alchemy的。投票功能测试不会报错。
<img width="918" height="398" alt="image" src="https://github.com/user-attachments/assets/ead8a3c8-ec1c-459d-8be7-ecb9e6f297c6" />

## 4 运行脚本
运行前，先确定BASE或OP网络，及哪个投票交易对，取得data后并复制到程序中进行解析。所有投票地址将对这个交易对池投票。


    python3 ve33_tools.py
    
## 5 运行截图如下

voters.py只有投票功能运行：
<img width="1988" height="1226" alt="image" src="https://github.com/user-attachments/assets/ce741dc2-67a6-4157-a8e0-02385cd9da71" />

ve33_tools添加领取奖励功能运行：
<img width="1420" height="1374" alt="image" src="https://github.com/user-attachments/assets/02cfec47-f58e-4697-aa73-d54babac6d7a" />

