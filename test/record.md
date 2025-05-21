## 运行所需依赖

- linux环境
- python版本大于等于3.9

```bash
sudo apt-get update  
sudo apt-get install poppler-utils
pip install langchain-openai angchain-core langchain  
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
1|ICLR 2025 Oral|odjMSBSWRt|9|15
2|ICLR 2025 Oral|QEHrmQPBdd|5|50
3|ICLR 2025 Oral|aWXnKanInf|6|57
4|ICLR 2025 Oral|XmProj9cPs|4|7
5|ICLR 2025 Oral|eHehzSDUFp|14|37
6|ICLR 2025 Poster|PwxYoMvmvy|3|11
7|ICLR 2025 Poster|ONfWFluZBI|1|9
8|ICLR 2025 Poster|imT03YXlG2|5|8
9|ICLR 2025 Poster|w7P92BEsb2|3|4
10|ICLR 2025 Poster|FDimWzmcWn|5|12
11|ICLR 2025 Spotlight|NGKQoaqLpo|4|21
12|ICLR 2025 Spotlight|rpwGUtTeA5|26|42
13|ICLR 2025 Spotlight|1qP3lsatCR|0|1
14|ICLR 2025 Spotlight|L14sqcrUC3|50|92
15|ICLR 2025 Spotlight|gcouwCx7dG|0|1
16|NIPS 2024 Oral|aVh9KRZdRk|4|20
17|NIPS 2024 Oral|REIK4SZMJt|3|8
18|NIPS 2024 Oral|gojL67CfS8|3|11
19|NIPS 2024 Oral|bCMpdaQCNW|3|10
20|NIPS 2024 Oral|wpGJ2AX6SZ|3|11
21|ICML 2024 Oral|frA0NNBS1n|0|7
22|ICML 2024 Oral|Bc4vZ2CX7E|0|28
23|ICML 2024 Oral|dVpFKfqF3R|0|3
24|ICML 2024 Oral|RbiBKPtuHp|5|7
25|ICML 2024 Oral|QBj7Uurdwf|1|4

- 具体结果见:
    - iclr_2025_oral.json
    - iclr_2025_oral_llm.json
    - iclr_2025_poster.json
    - iclr_2025_poster_llm.json
    - iclr_2025_spotlight.json
    - iclr_2025_spotlight_llm.json
    - nips_2024_oral.json
    - nips_2024_oral_llm.json
    - icml_2024_oral.json
    - icml_2024_oral_llm.json