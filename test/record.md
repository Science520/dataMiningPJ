## 运行所需依赖

- linux环境
- python版本大于等于3.9

```bash
sudo apt-get update  
sudo apt-get install poppler-utilsl
pip install langchain-openai langchain-core langchain  
pip install selenium PyPDF2 bs4 tenacity
```

- 虚拟机连接梯子，需要clash打开TUN模式或者
```bash
nano ~/.bashrc
```
添加你的ipv4地址和端口号例如
```
export http_proxy="192.168.1.101:7890"
export https_proxy="192.168.1.101:7890"
```
ctrl+O保存，enter，ctrl+X退出
```bash
source ~/.bashrc
```


## 运行命令

python final.py --conference "input_conference_url" -o output_filename.json -l limit_paper_num --use-llm --openai-key your_key


## 链接统计

序号|会议|论文ID|不使用LLM|使用LLM
-|-|-|-|-
1|ICLR 2025 Oral|odjMSBSWRt|2|6
2|ICLR 2025 Oral|QEHrmQPBdd|5|51
3|ICLR 2025 Oral|aWXnKanInf|5|57
4|ICLR 2025 Oral|XmProj9cPs|0|6
5|ICLR 2025 Oral|eHehzSDUFp|6|32

按照助教api的结果计算：

不使用LLM：
论文|参考|预测|precision|recall
-|-|-|-|-
odjMSBSWRt|2|2|0.5|0.5
QEHrmQPBdd|3|5|0.4|0.66

使用LLM：
论文|参考|预测|precision|recall
-|-|-|-|-
odjMSBSWRt|2|6|0.167|0.5
QEHrmQPBdd|3|51|0.059|1