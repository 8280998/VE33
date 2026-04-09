# VE33_tools
支持op网络的velo和base的aero批量投票,批量领取奖励。
Supports batch voting for OP's Velo and Base's Aero, and batch  claim rewards。

## 无责声明：本程序为明文代码，运行前请先审核代码安全性。确定使用后，运行时产生任何损失均与本代码无关
## Disclaimer: This program is plain text code. Please review the code security before running it. After confirming your use, any losses incurred during operation are not related to this code.


## 使用说明：
### 1 投票需要取得inputdata，并粘贴到data框，由程序解析出投票对象地址。点击投批量票按钮后执行。
### 2 自动领取扫描领取需要在config.json中指定代币的合约地址奖励池地址。当前已有默认几个地址，可以根据自身需要修改。
### 3 Rebase无需填写任何，程序读取vote.txt地址后自动执行。

## 1 安装支持环境
安装 Python，qt， web3（区块链交互库）

    sudo apt update && sudo apt install python3 python3-pip
    pip install PyQt6 web3

## 2 准备私匙文件
程序读取vote.txt内容，一行一个。格式为 私匙｜NFTID 类似如下：

0x123456....|1234

## 3 config.json配置说明

BASE链的AERO领取投票奖励，是通过投票合约0x16613524e02ad97eDfeF371bC883F2F5d6C480A5（BASE）和0x41c914ee0c7e1a5edcd0295623e6dc557b5abf3c（OP）调用其他代币奖励合约进行领取。但投票合约上没有查询所有奖励代币和数量的功能，只有领取奖励功能。查询投票所得代币和数量是在调用其他合约来完成。因此需要在config.json配置已知的奖励池合约（LP）和代币合约地址。

当前已支持批量领取多个代币，如果在领取过程出现RPC错误，把config.json的RPC修改为其他，建议采用alchemy的。投票功能测试不会报错。

## 4 运行脚本
运行前，先确定BASE或OP网络，及哪个投票交易对，取得data后并复制到程序中进行解析。所有投票地址将对这个交易对池投票。


    python3 ve33_tools.py
    
## 5 运行截图如下

<img width="1800" height="1456" alt="QQ_1775712216499" src="https://github.com/user-attachments/assets/29c5d2b6-bf6c-435d-82b3-4734f9c6fb20" />

