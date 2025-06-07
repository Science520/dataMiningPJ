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
from openreview import fetch_paper  
from combine import is_benchmark_or_dataset_link, _on_error, _log, setup_llm, extract_text_from_pdf, extract_urls_from_text, save_json  

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


def extract_paper_title_from_pdf(pdf_path: str) -> str:  
    """从PDF文件中提取论文标题"""  
    try:  
        with open(pdf_path, 'rb') as file:  
            reader = PyPDF2.PdfReader(file)  
            if len(reader.pages) > 0:  
                first_page_text = reader.pages[0].extract_text()  
                
                # 尝试提取标题（通常在第一页的前几行）  
                lines = first_page_text.split('\n')[:10]  # 取前10行  
                
                # 移除空行和过短的行  
                potential_titles = [line.strip() for line in lines if len(line.strip()) > 10]  
                
                if potential_titles:  
                    # 通常标题是最长的行，或者第一个非空的长行  
                    title_candidates = []  
                    for line in potential_titles[:3]:  # 只考虑前3行  
                        # 清理标题文本  
                        clean_line = re.sub(r'[^\w\s\-:()]', ' ', line)  
                        clean_line = ' '.join(clean_line.split())  
                        if len(clean_line) > 15:  # 标题通常比较长  
                            title_candidates.append(clean_line)  
                    
                    if title_candidates:  
                        # 选择最长的候选标题  
                        return max(title_candidates, key=len)  
        
        # 如果无法提取标题，使用文件名  
        filename = os.path.basename(pdf_path)  
        return os.path.splitext(filename)[0]  
        
    except Exception as e:  
        logger.warning(f"提取论文标题失败: {str(e)}")  
        filename = os.path.basename(pdf_path)  
        return os.path.splitext(filename)[0]  


def extract_dataset_name_from_context(url: str, context: str) -> str:  
    """从上下文中提取数据集名称"""  
    try:  
        # 先尝试从URL中提取名称  
        if 'github.com' in url:  
            # GitHub链接格式: https://github.com/user/repo  
            parts = url.split('/')  
            if len(parts) >= 5:  
                repo_name = parts[4].replace('-', ' ').replace('_', ' ')  
                if repo_name.lower() not in ['main', 'master', 'blob', 'tree']:  
                    return repo_name.title()  
        
        elif 'huggingface.co' in url:  
            # HuggingFace链接格式  
            parts = url.split('/')  
            if len(parts) >= 4:  
                dataset_name = parts[-1].replace('-', ' ').replace('_', ' ')  
                return dataset_name.title()  
        
        # 从上下文中提取数据集名称  
        context_lower = context.lower()  
        
        # 常见数据集名称模式  
        dataset_patterns = [  
            r'\b([A-Z][a-zA-Z]*(?:[A-Z][a-z]*)*)\s+(?:dataset|benchmark|corpus)',  
            r'(?:dataset|benchmark|corpus)\s+([A-Z][a-zA-Z]*(?:[A-Z][a-z]*)*)',  
            r'\b([A-Z]{2,}(?:[A-Z][a-z]*)*)\b',  # 全大写或首字母大写的缩写  
            r'"([^"]+)"',  # 引号中的内容  
            r"'([^']+)'",   # 单引号中的内容  
        ]  
        
        for pattern in dataset_patterns:  
            matches = re.findall(pattern, context)  
            if matches:  
                candidate = matches[0].strip()  
                # 过滤掉太常见的词  
                if len(candidate) > 2 and candidate.lower() not in ['the', 'and', 'for', 'with', 'data', 'test', 'train']:  
                    return candidate  
        
        # 如果都没找到，尝试从URL的最后部分提取  
        url_parts = url.rstrip('/').split('/')  
        if url_parts:  
            last_part = url_parts[-1]  
            if '.' not in last_part or last_part.endswith('.git'):  
                name = last_part.replace('.git', '').replace('-', ' ').replace('_', ' ')  
                return name.title()  
        
        return "Unknown Dataset"  
        
    except Exception as e:  
        logger.warning(f"提取数据集名称失败: {str(e)}")  
        return "Unknown Dataset"  


def extract_dataset_description(url: str, contexts: List[str]) -> str:  
    """提取数据集描述"""  
    try:  
        # 合并所有上下文  
        full_context = ' '.join(contexts)  
        
        # 寻找描述性文本  
        description_patterns = [  
            r'(?:is|are)\s+([^.!?]{20,100}[.!?])',  # "is/are ..."的描述  
            r'(?:contains?|includes?)\s+([^.!?]{20,100}[.!?])',  # "contains/includes ..."  
            r'(?:consists? of|comprises?)\s+([^.!?]{20,100}[.!?])',  # "consists of/comprises ..."  
        ]  
        
        for pattern in description_patterns:  
            matches = re.findall(pattern, full_context, re.IGNORECASE)  
            if matches:  
                description = matches[0].strip()  
                # 清理描述文本  
                description = re.sub(r'\s+', ' ', description)  
                if len(description) > 10:  
                    return description  
        
        # 如果找不到描述，返回基于URL类型的默认描述  
        if 'github.com' in url:  
            return "GitHub repository containing dataset or benchmark code"  
        elif 'huggingface.co' in url:  
            return "Dataset hosted on Hugging Face platform"  
        elif any(domain in url for domain in ['kaggle.com', 'data.gov', 'zenodo.org']):  
            return"Dataset from public data repository"  
        else:  
            return "Research dataset or benchmark"  
            
    except Exception as e:  
        logger.warning(f"提取数据集描述失败: {str(e)}")  
        return "Dataset for research purposes"  


def classify_dataset_source(url: str) -> str:  
    """分类数据集来源"""  
    if 'github.com' in url:  
        return 'git'  
    elif 'huggingface.co' in url:  
        return 'huggingface'  
    elif 'kaggle.com' in url:  
        return 'kaggle'  
    elif any(domain in url for domain in ['data.gov', 'zenodo.org', 'figshare.com']):  
        return 'data_repository'  
    else:  
        return 'web'  


def extract_benchmark_links_from_paper(pdf_path: str) -> Dict[str, List[str]]:  
    """从本地PDF文件中提取数据集和基准测试相关链接"""  
    try:  
        logger.info(f"Processing PDF: {pdf_path}")  
        
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
        
        return benchmark_links  
    
    except Exception as e:  
        _on_error(f"处理PDF失败: {str(e)}")  
        return {}  


def extract_text_from_local_pdf(pdf_path: str) -> str:  
    """从本地PDF文件提取文本内容"""  
    try:  
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


def process_pdf_directory(pdf_dir: str, output_file: str, limit: int = None) -> None:  
    """处理PDF目录，提取数据集和基准测试链接"""  
    print(f"开始处理PDF目录: {pdf_dir}")  
    
    # 确保目录存在  
    if not os.path.exists(pdf_dir):  
        _on_error(f"目录不存在: {pdf_dir}")  
        save_json(output_file, {})  
        return  
    
    # 获取所有PDF文件  
    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]  
    
    if not pdf_files:  
        _on_error(f"目录中没有找到PDF文件: {pdf_dir}")  
        save_json(output_file, {})  
        return  
    
    print(f"找到 {len(pdf_files)} 个PDF文件")  
    
    # 如果设置了limit，只处理指定数量的文件  
    if limit and limit > 0:  
        pdf_files = pdf_files[:limit]  
        print(f"根据限制，将只处理前 {limit} 个PDF文件")  
    
    # 处理每个PDF文件  
    results = {}  
    
    for i, pdf_file in enumerate(pdf_files):  
        pdf_path = os.path.join(pdf_dir, pdf_file)  
        print(f"处理PDF {i+1}/{len(pdf_files)}: {pdf_file}")  
        
        try:  
            # 提取论文标题  
            paper_title = extract_paper_title_from_pdf(pdf_path)  
            print(f"  论文标题: {paper_title}")  
            
            # 提取基准测试链接  
            benchmark_links = extract_benchmark_links_from_paper(pdf_path)  
            
            if benchmark_links:  
                # 为这篇论文创建数据集记录  
                paper_datasets = {}  
                
                for url, contexts in benchmark_links.items():  
                    # 提取数据集名称  
                    dataset_name = extract_dataset_name_from_context(url, ' '.join(contexts))  
                    
                    # 分类数据集来源  
                    source_type = classify_dataset_source(url)  
                    
                    # 提取描述  
                    description = extract_dataset_description(url, contexts)  
                    
                    # 存储数据集信息  
                    paper_datasets[dataset_name] = [  
                        source_type,  
                        url,  
                        description  
                    ]  
                
                results[paper_title] = paper_datasets  
                print(f"  找到 {len(benchmark_links)} 个数据集/基准测试链接")  
            else:  
                print("  未找到数据集/基准测试链接")  
                
        except Exception as e:  
            print(f"  处理失败: {str(e)}")  
        
        # 避免处理过于频繁  
        time.sleep(0.5)  
    
    # 保存结果  
    save_json(output_file, results)  
    print(f"处理完成。总共处理了 {len(results)} 篇包含数据集链接的论文")  


def process_single_pdf(pdf_path: str, output_file: str) -> None:  
    """处理单个PDF文件"""  
    print(f"开始处理PDF文件: {pdf_path}")  
    
    if not os.path.exists(pdf_path):  
        _on_error(f"文件不存在: {pdf_path}")  
        save_json(output_file, {})  
        return  
    
    try:  
        # 提取论文标题  
        paper_title = extract_paper_title_from_pdf(pdf_path)  
        print(f"论文标题: {paper_title}")  
        
        # 提取基准测试链接  
        benchmark_links = extract_benchmark_links_from_paper(pdf_path)  
        
        results = {}  
        
        if benchmark_links:  
            paper_datasets = {}  
            
            for url, contexts in benchmark_links.items():  
                # 提取数据集名称  
                dataset_name = extract_dataset_name_from_context(url, ' '.join(contexts))  
                
                # 分类数据集来源  
                source_type = classify_dataset_source(url)  
                
                # 提取描述  
                description = extract_dataset_description(url, contexts)  
                
                # 存储数据集信息  
                paper_datasets[dataset_name] = [  
                    source_type,  
                    url,  
                    description  
                ]  
            
            results[paper_title] = paper_datasets  
            print(f"找到 {len(benchmark_links)} 个数据集/基准测试链接")  
        else:  
            print("未找到数据集/基准测试链接")  
        
        # 保存结果  
        save_json(output_file, results)  
        print("处理完成")  
        
    except Exception as e:  
        print(f"处理失败: {str(e)}")  
        save_json(output_file, {})  


def main():  
    """主函数，处理命令行参数"""  
    parser = argparse.ArgumentParser(description='从PDF文件或目录提取数据集和基准测试链接')  
    
    # 创建互斥组  
    source_group = parser.add_mutually_exclusive_group(required=True)  
    source_group.add_argument('--pdf', type=str, help='单个PDF文件路径')  
    source_group.add_argument('--pdf-dir', type=str, help='包含PDF文件的目录路径')  
    source_group.add_argument('--conference', type=str, help='OpenReview会议URL')  
    
    parser.add_argument('-o', '--output', type=str, required=True, help='输出JSON文件路径')  
    parser.add_argument('-l', '--limit', type=int, help='限制处理的文件数量')  
    parser.add_argument('--use-llm', action='store_true', help='是否使用LLM辅助判断')  
    parser.add_argument('--openai-key', type=str, help='OpenAI API密钥')  
    
    args = parser.parse_args()  
    
    # 检查是否启用LLM  
    if args.use_llm:  
        if setup_llm(args.openai_key):  
            print("使用LLM辅助判断已启用")  
        else:  
            print("LLM设置失败，将仅使用规则方法")  
    
    # 根据参数选择处理方式  
    if args.pdf:  
        process_single_pdf(args.pdf, args.output)  
    elif args.pdf_dir:  
        process_pdf_directory(args.pdf_dir, args.output, args.limit)  
    elif args.conference:  
        # 这里需要实现会议处理逻辑，保持原有格式  
        print("会议处理功能需要单独实现")  


if __name__ == "__main__":  
    main()