# dataMiningPJ
## 主题：期末挑战作业——AI Agent 设计：顶会论文数据集链接自动化挖掘 
## 目标：开发AI Agent 从指定顶会论文中自动提取开源数据集链接，提升数据获取效率
## 问题背景与数据特征
### 核心难点：Benchmark 数据集链接散落于论文各处，
### 链接可能位置
- 论文首页脚注、摘要（ABSTRACT）、引言（INTRODUCTION）等文本区域
### 示例场景
- 论文首页的脚注、论文abstract中、论文abstract之前
## 具体技术要求
- 输入规范
  - 目标输入：CCF-A 类或同级别顶会（如ICLR/NeurIPS/CVPR）的OpenReview会议主页URL
  - 示例格式
    - https://openreview.net/group?id=ICLR.cc/2025/Conference#tab-accept-oral
    - 需支持oral/poster/workshop 等不同论文列表页
- 输出要求
  - 内容：提取所有有效Benchmark/Dataset 链接，直接指向下载页或官方仓库（如GitHub），排除项目主页、博客等
  - 格式：JSON 格式，去重处理，使用指定保存函数
    - defsaveJson(filePath: str, datas: list) -> None: # 代码逻辑见文档段落3-45

### 评分标准与执行约束
- 召回率：小组结果与参考答案重合链接数/ 参考答案总链接数（首要指标）
- 有效链接率：可访问且符合定义的链接占比（次要指标）
### 提交与执行要求：
- 代码部署：将Agent 模型和脚本存储至实验室指定路径
- 全自动化：禁止人工干预输出（如手动增删链接），重复链接仅保留一次
### 工具与框架建议
- 爬虫与解析工具：
    - 网页解析：Beautiful Soup（基础HTML 解析）、Scrapy（动态内容/ 大规模爬取）
    - PDF 处理：PyMuPDF（轻量文本提取）、pdfplumber（复杂排版调试）
- AI 辅助工具：
    - LangChain：快速搭建基于LLM 的Agent 流程，处理自然语言中的链接识别

### 提交规范
- 交付物：
    - 可执行脚本及报告文档（说明输入输出格式、环境依赖等）
- 评估流程：
    - 评委使用基准Agent 生成参考答案，通过召回率和有效链接率排名



