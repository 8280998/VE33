# SAERO_tools
支持升级后的aero批量投票,领取奖励。

## 无责声明：本程序为明文代码，运行前请先审核代码安全性。确定使用后，运行时产生任何损失均与本代码无关
## Disclaimer: This program is plain text code. Please review the code security before running it. After confirming your use, any losses incurred during operation are not related to this code.


## 使用说明：
### 1 投票需要取得inputdata，并粘贴到data框，由程序解析出投票对象地址。点击 分配.试运行 测试是否正常。
### 2 测试正常后点击 分配.执行 ，程序读取vote.txt地址后自动执行。
### 3 支持一个地址多个Saero。

## 1 安装支持环境
安装 Python，qt， web3（区块链交互库）

    sudo apt update && sudo apt install python3 python3-pip
    pip install PyQt6 web3

## 2 准备私匙文件
程序读取vote.txt内容，一行一个。格式为 私匙内容

0x123456....

## 3 运行脚本
当前默认BASE网络，运行前先确定BASE或OP网络，取得data后并复制到程序中进行解析。所有投票地址将对这个交易对池投票。


    python3 saero.py
    

