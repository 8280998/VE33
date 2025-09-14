# VE33voters
当前支持op网络的velo和base的aero批量投票

## 1 安装支持环境
安装 Python，tkinter（GUI 库）， web3（区块链交互库）

    sudo apt update && sudo apt install python3 python3-pip
    sudo apt install python3-tk
    pip3 install web3

## 2 准备私匙文件
程序读取vote.txt内容，一行一个。格式为 私匙｜NFTID 类似如下：

0x123456....|1234


## 3 运行脚本
运行前，先确定哪个投票交易对，取得data后并复制到程序中进行解析。所有投票地址将对这个交易对池投票。如下边示图

    python3 voters.py
    
## 4 运行截图如下

<img width="1988" height="1226" alt="image" src="https://github.com/user-attachments/assets/ce741dc2-67a6-4157-a8e0-02385cd9da71" />



