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

    python3 voters.py
    



