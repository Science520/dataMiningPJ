import json  
import os  
import time  
import re  
import argparse  
import tempfile  
import subprocess  
import html  
import sys  
from typing import List, Dict, Any, Set, Optional  
from urllib.parse import urlparse, urlunparse  
import requests  
import PyPDF2  
import io  
import logging  
from bs4 import BeautifulSoup  
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type  

# 导入原始函数  
from pdf_url import pdf_find_url
# can_access, is_url, find_node_with_url, process_pdf, process_text, find_context
from openreview import fetch_paper  
from combine import is_benchmark_or_dataset_link, _on_error, _log, setup_llm, extract_text_from_pdf, extract_urls_from_text, save_json
# verify_dataset_candidate, is_benchmark_or_dataset_link_llm, is_benchmark_or_dataset_link_rule, call_llm_with_retry 

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


def extract_benchmark_links_from_paper(pdf_url: str) -> Dict[str, List[str]]:  
    """从论文中提取数据集和基准测试相关链接，整合pdf_find_url功能"""  
    try:  
        # 下载PDF并保存到临时文件  
        response = requests.get(pdf_url)  
        response.raise_for_status()  
        
        # 创建临时文件  
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:  
            temp_pdf.write(response.content)  
            temp_pdf_path = temp_pdf.name  
        
        logger.info(f"PDF已下载到临时文件: {temp_pdf_path}")  
        
        # 使用pdf_find_url提取所有URL及上下文  
        all_urls_from_pdf_find = pdf_find_url(temp_pdf_path)  
        
        # 修改上下文格式，确保与extract_urls_from_text一致  
        all_urls = {}  
        for url, contexts in all_urls_from_pdf_find.items():  
            all_urls[url] = contexts  
        
        # 如果pdf_find_url返回为空或结果非常少，尝试使用原始方法作为补充  
        if len(all_urls) < 5:  # 阈值可以调整  
            logger.warning(f"pdf_find_url仅找到 {len(all_urls)} 个URL，尝试补充使用原始方法")  
            text = extract_text_from_pdf(pdf_url)  
            additional_urls = extract_urls_from_text(text)  
            
            # 将原始方法找到的URL合并到结果中  
            for url, contexts in additional_urls.items():  
                if url not in all_urls:  
                    all_urls[url] = contexts  
                else:  
                    all_urls[url].extend(contexts)  
        
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
        
        # 清理临时文件  
        try:  
            os.unlink(temp_pdf_path)  
            text_file = re.sub(r'\.pdf$', r'.txt', temp_pdf_path)  
            if os.path.exists(text_file):  
                os.unlink(text_file)  
        except Exception as e:  
            logger.warning(f"清理临时文件失败: {str(e)}")  
        
        return benchmark_links  
    
    except Exception as e:  
        _on_error(f"处理PDF失败: {str(e)}")  
        return {}  


def process_conference(url: str, output_file: str, limit: int = None) -> None:  # 逻辑和 combine.py 一样，只不过不能调用 combine.py 内此函数，不然没用新的 extract_benchmark_links_from_paper
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
            
            # 提取论文中的基准测试链接 - 使用整合了pdf_find_url的新函数  
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

def process_local_pdf(pdf_path: str, output_file: str) -> None:  
    """处理本地PDF文件，提取数据集和基准测试链接"""  
    print(f"开始处理本地PDF: {pdf_path}")  
    
    # 确保文件存在  
    if not os.path.exists(pdf_path):  
        _on_error(f"文件不存在: {pdf_path}")  
        save_json(output_file, [])  
        return  
    
    # 使用pdf_find_url提取所有URL及上下文  
    all_urls_from_pdf_find = pdf_find_url(pdf_path)  
    
    # 补充使用extract_text_from_local_pdf方法  
    text = extract_text_from_local_pdf(pdf_path)  
    additional_urls = extract_urls_from_text(text)  
    
    # 合并结果  
    all_urls = {}  
    for url, contexts in all_urls_from_pdf_find.items():  
        all_urls[url] = contexts  
    
    for url, contexts in additional_urls.items():  
        if url not in all_urls:  
            all_urls[url] = contexts  
        else:  
            all_urls[url].extend(contexts)  
    
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
    
    # 创建结果记录  
    all_benchmarks = []  
    for url, contexts in benchmark_links.items():  
        all_benchmarks.append({  
            "url": url,  
            "pdf_path": pdf_path,  
            "contexts": contexts  
        })  
    
    # 保存结果  
    save_json(output_file, all_benchmarks)  
    print(f"处理完成。找到 {len(benchmark_links)} 个唯一数据集/基准测试链接")  

def extract_text_from_local_pdf(pdf_path: str) -> str:  
    """从本地PDF文件提取文本内容"""  
    try:  
        # 使用PyPDF2提取文本  
        with open(pdf_path, 'rb') as file:  
            reader = PyPDF2.PdfReader(file)  
            
            text = ""  
            for page_num in range(len(reader.pages)):  
                page_text = reader.pages[page_num].extract_text()  
                if page_text:  
                    text += page_text + "\n"  
            
            return text  
    except Exception as e:  
        _on_error(f"本地PDF处理失败: {str(e)}")  
        return ""  

def main():  
    """主函数，处理命令行参数"""  
    parser = argparse.ArgumentParser(description='从OpenReview会议或本地PDF提取数据集和基准测试链接')  
    
    # 创建互斥组，要么处理会议，要么处理本地PDF  
    source_group = parser.add_mutually_exclusive_group(required=True)  
    source_group.add_argument('--conference', type=str, help='OpenReview会议URL')  
    source_group.add_argument('--pdf', type=str, help='本地PDF文件路径')  
    
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
    
    # 根据参数选择处理会议或本地PDF  
    if args.conference:  
        process_conference(args.conference, args.output, args.limit)  
    elif args.pdf:  
        process_local_pdf(args.pdf, args.output)  

if __name__ == "__main__":  
    main()