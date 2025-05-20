import json  
import os  
import time  
import re  
import argparse  
from typing import List, Dict, Any, Set, Optional  
from urllib.parse import urlparse  
import requests  
import PyPDF2  
import io  
import logging  
from bs4 import BeautifulSoup  
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type  

# 导入原始函数  
from pdf_url import can_access  
from openreview import fetch_paper  

# LangChain相关导入  
try:  
    from langchain_openai import OpenAI  
    from langchain_core.prompts import PromptTemplate  
    from langchain.chains.llm import LLMChain  
    LANGCHAIN_AVAILABLE = True  
except ImportError:  
    LANGCHAIN_AVAILABLE = False  

# 设置日志  
logging.basicConfig(level=logging.INFO)  
logger = logging.getLogger(__name__)  

# 全局变量  
USE_LLM = False  
llm = None  
prompt_link = None  
RATE_LIMIT_DELAY = 3  
LAST_API_CALL_TIME = 0  

def setup_llm(api_key=None):  
    """设置LLM相关组件"""  
    global llm, prompt_link, USE_LLM  
    
    if not LANGCHAIN_AVAILABLE:  
        logger.warning("LangChain库未安装，将仅使用规则方法")  
        return False  
    
    # 设置API密钥  
    if api_key:  
        os.environ["OPENAI_API_KEY"] = api_key  
    elif "OPENAI_API_KEY" not in os.environ:  
        logger.warning("未设置OpenAI API密钥，将仅使用规则方法")  
        return False  
    
    try:  
        # 初始化LLM  
        llm = OpenAI(temperature=0.1, request_timeout=30, max_retries=2)  
        
        # 创建提示模板  
        prompt_link = PromptTemplate(  
            input_variables=["url", "context_text"],   
            template="""  
            请分析以下文本中的链接 {url}，判断它是否指向一个可直接下载或访问的 Benchmark 或 Dataset。  

            链接上下文: {context_text}  

            判断标准:  
            1. 链接应该直接指向数据集下载页面或包含数据集的仓库  
            2. 不是框架官网（如PyTorch、TensorFlow）、项目主页、博客或一般介绍页面  
            3. 链接目标应该是可用于机器学习/数据挖掘任务的基准测试或数据集  
            4. 链接应该指向实际存在的资源，不是占位符或示例URL  

            请仔细分析后回答 'YES' 或 'NO'，并简要说明理由。  
            """  
        )  
        
        USE_LLM = True  
        return True  
    except Exception as e:  
        logger.error(f"LLM设置失败: {str(e)}")  
        return False  

def _on_error(msg: str):  
    """打印错误信息"""  
    print("\033[01;31m[!]\033[0;m", msg)  
    logger.error(msg)  

def _log(msg: str):  
    """打印日志信息"""  
    print("\033[01;92m[!]\033[0;m", msg)  
    logger.info(msg)  

def verify_dataset_candidate(url: str, context_text: str) -> bool:  
    """二次验证疑似数据集链接"""  
    # 解析URL  
    parsed = urlparse(url)  
    domain = parsed.netloc.lower()  
    path = parsed.path.lower()  
    
    # 排除已知的框架网站和一般性网站  
    exclude_sites = [  
        "pytorch.org", "tensorflow.org", "keras.io",  
        "wikipedia.org", "youtube.com", "twitter.com", "facebook.com",  
        "linkedin.com", "medium.com", "arxiv.org", "google.com"  
    ]  
    if any(site in domain for site in exclude_sites):  
        # 特例：如果是arxiv.org/data 或 google.com/dataset 这类路径，仍然可能是数据集  
        dataset_paths = ["dataset", "data", "benchmark", "corpus"]  
        if not any(keyword in path for keyword in dataset_paths):  
            return False  
    
    # 排除示例/占位符URL  
    exclude_terms = ["username", "example", "sample", "placeholder", "yourname"]  
    if any(term in url.lower() for term in exclude_terms):  
        return False  
    
    # 检查上下文是否强烈暗示这是数据集  
    dataset_indicators = [  
        "dataset", "benchmark", "corpus", "data available at",   
        "download from", "available at", "code and data"  
    ]  
    context_lower = context_text.lower()  
    has_dataset_indicator = any(indicator in context_lower for indicator in dataset_indicators)  
    
    # 如果上下文没有明确指示这是数据集，但URL看起来可能是  
    # 例如，GitHub仓库但不是明确的数据集  
    if "github.com" in domain and not has_dataset_indicator:  
        # 检查路径中是否有数据集相关关键词  
        github_dataset_terms = ["dataset", "data", "benchmark", "corpus"]  
        if not any(term in path for term in github_dataset_terms):  
            # 可能是代码库而不是数据集  
            return False  
    
    # 通过所有检查，认为是有效的数据集候选  
    return True

def extract_page_content(url: str) -> Optional[str]:  
    """尝试获取链接内容"""  
    try:  
        headers = {  
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'  
        }  
        response = requests.get(url, headers=headers, timeout=10)  
        response.raise_for_status()  
        
        soup = BeautifulSoup(response.text, 'html.parser')  
        
        for script in soup(["script", "style"]):  
            script.extract()  
        
        text = soup.get_text(separator=' ', strip=True)  
        
        text = re.sub(r'\s+', ' ', text).strip()  
        
        return text[:4000] if text else None  
    
    except Exception as e:  
        logger.warning(f"Failed to retrieve content from {url}: {str(e)}")  
        return None  

@retry(  
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),  
    wait=wait_exponential(multiplier=1, min=2, max=20),  
    stop=stop_after_attempt(3)  
)  
def call_llm_with_retry(url: str, context_text: str) -> str:  
    """使用重试机制调用LLM"""  
    global LAST_API_CALL_TIME  
    
    if not USE_LLM or not llm or not prompt_link:  
        return "NO"  
    
    # 实现速率限制  
    current_time = time.time()  
    time_since_last_call = current_time - LAST_API_CALL_TIME  
    
    if time_since_last_call < RATE_LIMIT_DELAY:  
        sleep_time = RATE_LIMIT_DELAY - time_since_last_call  
        logger.info(f"Rate limiting: Waiting {sleep_time:.2f} seconds before next API call")  
        time.sleep(sleep_time)  
    
    # 更新上次调用时间  
    LAST_API_CALL_TIME = time.time()  
    
    try:  
        # 使用新的invoke方法  
        chain = prompt_link | llm  # prompt 不能改成 chain，不然写的二次调用没用
        result = chain.invoke({"url": url, "context_text": context_text})  
        model_info = llm.model_name if hasattr(llm, 'model_name') else "Unknown model"  
        logger.info(f"API call successful using model: {model_info}")  
        return result  
    except Exception as e:  
        logger.error(f"API call failed: {str(e)}")  
        raise e  

def is_benchmark_or_dataset_link_llm(url: str, context_text: str) -> bool:  
    """使用LLM判断链接是否为Benchmark/Dataset链接"""  
    if not USE_LLM:  
        return False  
        
    # 先检查URL形式是否有效  
    if not can_access(url):  
        return False  
    
    # 使用LLM分析链接及其上下文  
    try:  
        logger.info(f"Analyzing link with LLM: {url}")  
        response = call_llm_with_retry(url, context_text)  
        
        initial_result = 'YES' in response.upper()  
        
        logger.info(f"LLM classification for {url}: {initial_result}")  
        
        if initial_result:  
            # 进行二次验证  
            if verify_dataset_candidate(url, context_text):  
                return True  
            else:  
                logger.info(f"Link initially classified as dataset but rejected in verification: {url}")  
                return False  
        
        return initial_result  
    
    except Exception as e:  
        logger.error(f"Error in LLM processing for {url}: {str(e)}")  
        return False  

def is_benchmark_or_dataset_link_rule(url: str, context: str = "") -> bool:  
    """使用规则判断URL是否是数据集或基准测试相关的链接"""  
    # 解析URL  
    parsed = urlparse(url)  
    domain = parsed.netloc.lower()  
    path = parsed.path.lower()  
    
    # 数据集相关域名和路径关键词  
    dataset_domains = {  
        'github.com': ['dataset', 'benchmark', 'data', 'corpus', 'evaluation'],  
        'huggingface.co': ['datasets'],  
        'kaggle.com': ['datasets'],  
        'paperswithcode.com': ['datasets', 'benchmarks'],  
        'tensorflow.org': ['datasets', 'data'],  
        'pytorch.org': ['data', 'datasets'],  
        'zenodo.org': [],  # 整个域名都是数据集相关  
        'figshare.com': [],  
        'data.mendeley.com': [],  
        'datadryad.org': [],  
        'dataverse.harvard.edu': [],  
        'catalog.ldc.upenn.edu': [],  
        'archive.ics.uci.edu': []  
    }  
    
    # 检查域名  
    if domain in dataset_domains:  
        if not dataset_domains[domain]:  # 空列表表示整个域名都是数据集相关  
            return True  
        for keyword in dataset_domains[domain]:  
            if keyword in path:  
                return True  
    
    # 检查路径中的关键词  
    dataset_keywords = [  
        'dataset', 'benchmark', 'corpus', 'data-download',   
        'download-data', 'data/download', 'download/data',  
        'evaluate', 'evaluation', 'metrics', 'performance',  
        'leaderboard', 'competition', 'challenge'  
    ]  
    for keyword in dataset_keywords:  
        if keyword in path:  
            return True  
    
    # 检查上下文中的关键词  
    context_lower = context.lower()  
    context_keywords = [  
        'dataset', 'data set', 'benchmark', 'corpus', 'repository',   
        'evaluation', 'metric', 'leaderboard', 'test set',  
        'training data', 'test data', 'evaluation data',  
        'repository for', 'official implementation', 'code for'  
    ]  
    for keyword in context_keywords:  
        if keyword in context_lower:  
            # 上下文中包含关键词，并且URL看起来不是博客或主页  
            if not any(x in path for x in ['blog', 'post', 'article', 'news', 'about']):  
                return True  
    
    return False  

def is_benchmark_or_dataset_link(url: str, context: str = "") -> bool:  
    """结合规则和LLM判断URL是否是数据集或基准测试相关的链接"""  
    # 先用规则方法判断  
    rule_result = is_benchmark_or_dataset_link_rule(url, context)  
    
    # 如果规则方法判断为True，直接返回  
    if rule_result:  
        logger.info(f"Rule-based method classified {url} as dataset/benchmark")  
        return True  
    
    # 如果规则方法判断为False且LLM可用，使用LLM方法进一步判断  
    if USE_LLM:  
        llm_result = is_benchmark_or_dataset_link_llm(url, context)  
        if llm_result:  
            logger.info(f"LLM method classified {url} as dataset/benchmark")  
            return True  
    
    return False  

def extract_text_from_pdf(pdf_url: str) -> str:  
    """从URL下载PDF并提取文本内容"""  
    try:  
        response = requests.get(pdf_url)  
        response.raise_for_status()  
        
        # 使用PyPDF2提取文本  
        pdf_file = io.BytesIO(response.content)  
        reader = PyPDF2.PdfReader(pdf_file)  
        
        text = ""  
        for page_num in range(len(reader.pages)):  
            page_text = reader.pages[page_num].extract_text()  
            if page_text:  
                text += page_text + "\n"  
        
        return text  
    except Exception as e:  
        _on_error(f"PDF处理失败: {str(e)}")  
        return ""  

def extract_urls_from_text(text: str, validate_urls: bool = False) -> Dict[str, List[str]]:  
    """从文本中提取URL及其上下文"""  
    if not text:  
        return {}  
    
    # 分行处理  
    lines = text.split('\n')  
    
    # 提取URL及上下文  
    url_pattern = r"https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_+.~#?&/=]*)"  
    result = {}  
    
    # 遍历每一行  
    for i, line in enumerate(lines):  
        urls = re.findall(url_pattern, line)  
        
        for url in urls:  
            # 清理URL（移除尾部的点）  
            url = re.sub(r'^(.*?)\.*$', r'\1', url)  
            
            # 验证URL是否可访问（可选）  
            if validate_urls and not can_access(url):  
                continue  
                
            if url not in result:  
                result[url] = []  
            
            # 获取上下文(当前行及前后1行)  
            start_idx = max(0, i - 1)  
            end_idx = min(len(lines), i + 2)  
            context = "\n".join(lines[start_idx:end_idx])  
            result[url].append(context)  
    
    return result  

def extract_benchmark_links_from_paper(pdf_url: str) -> Dict[str, List[str]]:  
    """从论文中提取数据集和基准测试相关链接"""  
    # 提取PDF文本  
    text = extract_text_from_pdf(pdf_url)  
    if not text:  
        return {}  
    
    # 从文本中提取所有URL及上下文  
    all_urls = extract_urls_from_text(text)  
    
    # 筛选数据集和基准测试相关链接  
    benchmark_links = {}  
    for url, contexts in all_urls.items():  
        # 对URL的所有上下文进行检查  
        relevant_contexts = []  
        for context in contexts:  
            if is_benchmark_or_dataset_link(url, context):  
                relevant_contexts.append(context)  
        
        # 如果该URL被识别为数据集/基准测试链接，保存所有相关上下文  
        if relevant_contexts:  
            benchmark_links[url] = relevant_contexts  
    
    return benchmark_links  

def save_json(file_path: str, data: list) -> None:  
    """将数据以JSON格式保存到文件"""  
    with open(file_path, 'w', encoding='utf-8') as f:  
        json.dump(data, f, ensure_ascii=False, indent=2)  
    _log(f"结果已保存到 {file_path}")  

def process_conference(url: str, output_file: str, limit: int = None) -> None:  
    """处理会议论文，提取数据集和基准测试链接  
    
    Args:  
        url: OpenReview会议URL  
        output_file: 输出JSON文件路径  
        limit: 限制处理的论文数量，None表示处理全部  
    """  
    print(f"开始处理会议: {url}")  
    
    # 获取所有论文PDF链接，这里使用try-except来捕获fetch_paper可能出现的错误  
    try:  
        paper_urls = fetch_paper(url)  
        print(f"找到 {len(paper_urls)} 篇论文")  
    except Exception as e:  
        _on_error(f"获取论文失败: {str(e)}")  
        # 如果fetch_paper失败，我们创建一个空列表  
        paper_urls = []  
    
    # 如果找不到论文或者出错，直接保存空结果并退出  
    if not paper_urls:  
        _on_error("未找到论文，请检查会议URL是否正确")  
        save_json(output_file, [])  
        print(f"处理完成。找到 0 个唯一数据集/基准测试链接")  
        return  
    
    # 如果设置了limit，只处理指定数量的论文  
    if limit and limit > 0:  
        paper_urls = paper_urls[:limit]  
        print(f"根据限制，将只处理前 {limit} 篇论文")  
    
    # 处理每篇论文  
    all_benchmarks = []  
    
    for i, pdf_url in enumerate(paper_urls):  
        print(f"处理论文 {i+1}/{len(paper_urls)}: {pdf_url}")  
        
        try:  
            print(f"  分析论文中的数据集链接")  
            
            # 提取论文中的基准测试链接  
            benchmark_links = extract_benchmark_links_from_paper(pdf_url)  
            
            if benchmark_links:  
                paper_id = pdf_url.split('id=')[-1] if 'id=' in pdf_url else f"paper_{i+1}"  
                
                # 为每个链接创建记录  
                for url, contexts in benchmark_links.items():  
                    all_benchmarks.append({  
                        "url": url,  
                        "paper_url": pdf_url,  
                        "paper_id": paper_id,  
                        "contexts": contexts  
                    })  
                
                print(f"  找到 {len(benchmark_links)} 个数据集/基准测试链接")  
            else:  
                print("  未找到数据集/基准测试链接")  
                
        except Exception as e:  
            print(f"  处理失败: {str(e)}")  
        
        # 避免请求过于频繁  
        time.sleep(1)  
    
    # 去重处理  
    unique_urls = {}  
    for item in all_benchmarks:  
        url = item["url"]  
        if url not in unique_urls:  
            unique_urls[url] = item  
        else:  
            # 合并上下文和来源论文  
            unique_urls[url]["contexts"].extend(item["contexts"])  
            # 去除重复上下文  
            unique_urls[url]["contexts"] = list(set(unique_urls[url]["contexts"]))  
            # 添加源论文记录  
            if "source_papers" not in unique_urls[url]:  
                unique_urls[url]["source_papers"] = [unique_urls[url]["paper_id"]]  
            if item["paper_id"] not in unique_urls[url]["source_papers"]:  
                unique_urls[url]["source_papers"].append(item["paper_id"])  
    
    # 转换为列表并保存  
    result = list(unique_urls.values())  
    save_json(output_file, result)  
    print(f"处理完成。找到 {len(result)} 个唯一数据集/基准测试链接")  

def main():  
    """主函数，处理命令行参数"""  
    parser = argparse.ArgumentParser(description='从OpenReview会议提取数据集和基准测试链接')  
    parser.add_argument('url', type=str, help='OpenReview会议URL')  
    parser.add_argument('-o', '--output', type=str, required=True, help='输出JSON文件路径')  
    parser.add_argument('-l', '--limit', type=int, default=10, help='限制处理的论文数量，默认为10')  
    parser.add_argument('--use-llm', action='store_true', help='是否使用LLM辅助判断，需要OpenAI API密钥')  
    parser.add_argument('--openai-key', type=str, help='OpenAI API密钥')  
    
    args = parser.parse_args()  
    
    # 检查是否启用LLM  
    if args.use_llm:  
        if setup_llm(args.openai_key):  
            print("使用LLM辅助判断已启用")  
        else:  
            print("LLM设置失败，将仅使用规则方法")  
    
    # 处理会议  
    process_conference(args.url, args.output, args.limit)  

if __name__ == "__main__":  
    main()