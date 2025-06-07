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

# 设置日志  
logging.basicConfig(level=logging.INFO)  
logger = logging.getLogger(__name__)  

# 全局变量  
USE_LLM = False  
RATE_LIMIT_DELAY = 3  
LAST_API_CALL_TIME = 0  
API_KEY = None  
USE_FREE_API = False  # 是否使用免费校园网API  

# 通用数据集列表页面，应该被过滤掉  
GENERIC_DATASET_PAGES = {  
    'paperswithcode.com/datasets',  
    'kaggle.com/datasets',   
    'huggingface.co/datasets',  
    'github.com/datasets',  
    'data.gov',  
    'zenodo.org',  
    'figshare.com',  
    'nips.cc/public',  
    'neurips.cc/public',  
    'iclr.cc',  
    'icml.cc'  
}  

def setup_llm(api_key: str = None, use_free: bool = False) -> bool:  
    """设置LLM API"""  
    global USE_LLM, API_KEY, USE_FREE_API  
    
    if use_free:  
        # 使用免费校园网API  
        USE_FREE_API = True  
        USE_LLM = True  
        logger.info("使用免费校园网API")  
        return True  
    elif api_key:  
        # 使用收费API  
        API_KEY = api_key  
        USE_FREE_API = False  
        USE_LLM = True  
        logger.info("使用收费API")  
        return True  
    else:  
        logger.warning("未提供API密钥且未启用免费API")  
        return False  

def qwen_by_api(prompt: str, engine_name: str = "chatgpt-4o-latest") -> tuple:  
    """收费API调用 - 添加错误处理"""  
    global API_KEY  
    
    if not API_KEY:  
        raise ValueError("API密钥未设置")  
    
    if "#" in engine_name:  
        temp = engine_name.split("#")  
        engine_name = temp[0]  
        temperature = float(temp[1])  
        params = {  
            "messages": [{"role": "user", "content": prompt}],  
            "model": engine_name,  
            "temperature": temperature,  
        }  
    else:  
        params = {  
            "messages": [{"role": "user", "content": prompt}],  
            "model": engine_name,  
        }  
    
    headers = {  
        "Authorization": "Bearer " + API_KEY,  
    }  
    
    try:  
        response = requests.post(  
            "https://api.openai.com/v1/chat/completions",  
            headers=headers,  
            json=params,  
            stream=False,  
        )  
        
        # 检查HTTP状态码  
        if response.status_code != 200:  
            logger.error(f"API HTTP错误: {response.status_code}")  
            logger.error(f"响应内容: {response.text}")  
            raise Exception(f"API HTTP错误: {response.status_code}")  
        
        # 尝试解析JSON  
        try:  
            res = response.json()  
        except json.JSONDecodeError as e:  
            logger.error(f"JSON解析错误: {str(e)}")  
            logger.error(f"响应内容: {response.text}")  
            raise Exception(f"JSON解析错误: {str(e)}")  
        
        # 打印完整响应进行调试  
        logger.info(f"API完整响应: {res}")  
        
        # 检查是否有错误信息  
        if "error" in res:  
            error_msg = res.get("error", {}).get("message", "未知错误")  
            logger.error(f"API返回错误: {error_msg}")  
            raise Exception(f"API错误: {error_msg}")  
        
        # 检查必要字段  
        if "choices" not in res:  
            logger.error(f"响应中缺少choices字段: {res}")  
            raise Exception("API响应格式错误：缺少choices字段")  
        
        if len(res["choices"]) == 0:  
            logger.error("choices字段为空")  
            raise Exception("API响应choices为空")  
        
        if "message" not in res["choices"][0]:  
            logger.error(f"choices[0]中缺少message字段: {res['choices'][0]}")  
            raise Exception("API响应格式错误：缺少message字段")  
        
        message = res["choices"][0]["message"]["content"]  
        usage = res.get("usage", {})  
        
        logger.info(f"API调用成功")  
        logger.debug(f"使用量: {usage}")  
        
        return message, usage  
        
    except requests.exceptions.RequestException as e:  
        logger.error(f"网络请求错误: {str(e)}")  
        raise Exception(f"网络请求错误: {str(e)}")  
    except Exception as e:  
        logger.error(f"API调用失败: {str(e)}")  
        raise e  

def free_api(prompt: str) -> str:  
    """免费校园网API调用 - 通过中转地址，添加错误处理"""  
    try:  
        # 使用和付费API类似的方式，通过中转地址调用  
        params = {  
            "messages": [  
                {"role": "system", "content": "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."},  
                {"role": "user", "content": prompt}  
            ],  
            "model": "chatgpt-4o-latest",  # 或者使用免费API对应的模型名  
            "temperature": 0  
        }  
        
        headers = {  
            "Authorization": "sk-TYsWUFGG51c2eF5a6E37T3BLbkFJ226a6C034d01449a98e7",  # 免费API的密钥  
        }  
        
        response = requests.post(  
            "https://aigptx.top/v1/chat/completions",  # 同样的中转地址  
            headers=headers,  
            json=params,  
            stream=False,  
        )  
        
        # 检查HTTP状态码  
        if response.status_code != 200:  
            logger.error(f"免费API HTTP错误: {response.status_code}")  
            logger.error(f"响应内容: {response.text}")  
            raise Exception(f"免费API HTTP错误: {response.status_code}")  
        
        # 尝试解析JSON  
        try:  
            res = response.json()  
        except json.JSONDecodeError as e:  
            logger.error(f"免费API JSON解析错误: {str(e)}")  
            logger.error(f"响应内容: {response.text}")  
            raise Exception(f"免费API JSON解析错误: {str(e)}")  
        
        # 打印完整响应进行调试  
        logger.info(f"免费API完整响应: {res}")  
        
        # 检查是否有错误信息  
        if "error" in res:  
            error_msg = res.get("error", {}).get("message", "未知错误")  
            logger.error(f"免费API返回错误: {error_msg}")  
            raise Exception(f"免费API错误: {error_msg}")  
        
        # 检查必要字段  
        if "choices" not in res:  
            logger.error(f"免费API响应中缺少choices字段: {res}")  
            raise Exception("免费API响应格式错误：缺少choices字段")  
        
        if len(res["choices"]) == 0:  
            logger.error("免费API choices字段为空")  
            raise Exception("免费API响应choices为空")  
        
        message = res["choices"][0]["message"]["content"]  
        
        logger.info(f"免费API调用成功")  
        return message  
        
    except Exception as e:  
        logger.error(f"免费API调用失败: {str(e)}")  
        raise e  


@retry(  
    retry=retry_if_exception_type((Exception,)),  # 修正：捕获所有异常类型  
    wait=wait_exponential(multiplier=1, min=2, max=20),  
    stop=stop_after_attempt(3)  
)  
def call_llm_with_retry(url: str, context_text: str) -> str:  
    """使用重试机制调用LLM"""  
    global LAST_API_CALL_TIME, USE_FREE_API  
    
    if not USE_LLM:  
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
    
    # 构建prompt  
    prompt = f"""  
请分析以下URL和上下文，判断是否指向数据集或基准测试资源。  

URL: {url}  
上下文: {context_text}  

判断标准：  
1. URL是否指向具体的数据集或基准测试？  
2. 上下文是否在讨论数据收集、评估或基准测试？  
3. URL是否提供可下载的数据或基准测试工具？  
4. 这是否是学术论文中常用的研究数据集？  

如果这是数据集/基准测试链接，请回答"YES"；如果不是，请回答"NO"。  
只回答YES或NO，不要包含其他文本。  
"""  
    
    try:  
        if USE_FREE_API:  
            # 使用免费校园网API  
            result = free_api(prompt)  
        else:  
            # 使用收费API  
            result, usage = qwen_by_api(prompt)  
        
        logger.info(f"API call successful")  
        return result  
        
    except Exception as e:  
        logger.error(f"API call failed: {str(e)}")  
        raise e

def can_access(url: str) -> bool:  
    """检查URL是否可访问"""  
    try:  
        # 基本URL格式检查  
        if not url or not isinstance(url, str):  
            return False  
        
        # 检查是否为有效URL格式  
        parsed = urlparse(url)  
        if not parsed.scheme or not parsed.netloc:  
            return False  
        
        # 过滤明显无关的URL  
        irrelevant_patterns = [  
            r'\.pdf$',  
            r'\.png$', r'\.jpg$', r'\.jpeg$', r'\.gif$',  
            r'mailto:',  
            r'javascript:',  
            r'#',  
        ]  
        
        for pattern in irrelevant_patterns:  
            if re.search(pattern, url.lower()):  
                return False  
        
        return True  
        
    except Exception:  
        return False  

def verify_dataset_candidate(url: str, context_text: str) -> bool:  
    """二次验证数据集候选"""  
    try:  
        # 构建验证prompt  
        verify_prompt = f"""  
请再次检查这个URL和上下文是否真的指向一个具体的数据集或基准测试资源。  

URL: {url}  
上下文: {context_text}  

只有满足以下条件时才回答"YES"：  
1. 指向一个具体的、有名称的数据集或基准测试  
2. 资源可下载或可访问用于研究  
3. 这不只是一个通用网站、政策页面或指南  

如果是以下情况请回答"NO"：  
1. 通用网站或首页  
2. 政策/指南/伦理文档  
3. 只是代码库首页而没有具体数据集  
4. 上下文没有明确指示数据集使用  

回答：只回答YES或NO。  
"""  
        
        if USE_FREE_API:  
            result = free_api(verify_prompt)  
        else:  
            result, _ = qwen_by_api(verify_prompt)  
        
        return 'YES' in result.upper()  
        
    except Exception as e:  
        logger.warning(f"验证失败: {str(e)}")  
        return False  

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

def is_benchmark_or_dataset_link_rules(url: str, context_text: str) -> bool:  
    """使用规则方法判断链接是否为Benchmark/Dataset链接"""  
    
    # URL关键词检查  
    dataset_url_keywords = [  
        'github.com', 'huggingface.co/datasets', 'kaggle.com/datasets',  
        'zenodo.org', 'figshare.com', 'data.gov', 'archive.ics.uci.edu',  
        'paperswithcode.com/dataset', 'openml.org', 'tensorflow.org/datasets',  
        'pytorch.org/vision/datasets', 'scikit-learn.org/datasets'  
    ]  
    
    url_lower = url.lower()  
    url_match = any(keyword in url_lower for keyword in dataset_url_keywords)  
    
    if url_match:  
        logger.info(f"Rule-based method classified {url} as dataset/benchmark")  
        return True  
    
    # 上下文关键词检查  
    context_lower = context_text.lower()  
    dataset_context_keywords = [  
        'dataset', 'benchmark', 'corpus', 'data', 'evaluation',  
        'test set', 'training set', 'validation set', 'ground truth',  
        'baseline', 'metric', 'score', 'performance', 'accuracy'  
    ]  
    
    context_matches = sum(1 for keyword in dataset_context_keywords if keyword in context_lower)  
    
    if context_matches >= 2:  
        logger.info(f"Rule-based method classified {url} as dataset/benchmark based on context")  
        return True  
    
    return False  

def is_benchmark_or_dataset_link(url: str, context_text: str) -> bool:  
    """综合判断链接是否为Benchmark/Dataset链接"""  
    
    # 首先使用规则方法  
    rules_result = is_benchmark_or_dataset_link_rules(url, context_text)  
    
    if rules_result:  
        return True  
    
    # 如果规则方法判断为否，且启用了LLM，则使用LLM进行判断  
    if USE_LLM:  
        return is_benchmark_or_dataset_link_llm(url, context_text)  
    
    return False  

def is_generic_dataset_page(url: str) -> bool:  
    """检查是否为通用数据集列表页面，而非具体数据集"""  
    url_lower = url.lower().strip('/')  
    
    # 检查是否为通用页面  
    for generic_page in GENERIC_DATASET_PAGES:  
        if generic_page in url_lower:  
            # 但是如果是具体的数据集路径，则不过滤  
            if 'paperswithcode.com/dataset/' in url_lower:  # 具体数据集  
                return False  
            if 'huggingface.co/datasets/' in url_lower and len(url_lower.split('/')) > 4:  # 具体数据集  
                return False  
            if 'github.com/' in url_lower and len(url_lower.split('/')) >= 5:  # 具体仓库  
                return False  
            return True  
    
    # 检查其他通用模式  
    generic_patterns = [  
        r'/datasets/?$',  # 以/datasets结尾  
        r'/data/?$',      # 以/data结尾  
        r'guides?/',      # 包含guides  
        r'policy',        # 包含policy  
        r'ethics',        # 包含ethics  
        r'submission',    # 包含submission  
    ]  
    
    for pattern in generic_patterns:  
        if re.search(pattern, url_lower):  
            return True  
    
    return False  

def _on_error(message: str):  
    """错误处理"""  
    logger.error(message)  

def _log(message: str):  
    """日志记录"""  
    logger.info(message)  

def save_json(filename: str, data: dict):  
    """保存JSON文件"""  
    try:  
        with open(filename, 'w', encoding='utf-8') as f:  
            json.dump(data, f, ensure_ascii=False, indent=2)  
        logger.info(f"结果已保存到 {filename}")  
        print(f"[!] 结果已保存到 {filename}")  
        # 打印结果内容  
        print(json.dumps(data, ensure_ascii=False, indent=2))  
    except Exception as e:  
        logger.error(f"Failed to save results: {str(e)}")  

def extract_text_from_pdf(pdf_path: str) -> str:  
    """从PDF提取文本"""  
    try:  
        with open(pdf_path, 'rb') as file:  
            reader = PyPDF2.PdfReader(file)  
            text = ""  
            for page in reader.pages:  
                text += page.extract_text() + "\n"  
            return text  
    except Exception as e:  
        logger.error(f"Failed to extract text from PDF: {str(e)}")  
        return ""  

def extract_urls_from_text(text: str) -> Dict[str, List[str]]:  
    """从文本中提取URL"""  
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'  
    urls = re.findall(url_pattern, text)  
    
    result = {}  
    for url in urls:  
        # 简单的上下文提取  
        url_index = text.find(url)  
        start = max(0, url_index - 100)  
        end = min(len(text), url_index + len(url) + 100)  
        context = text[start:end]  
        
        if url not in result:  
            result[url] = []  
        result[url].append(context)  
    
    return result  

def extract_paper_title_from_pdf(pdf_path: str) -> str:  
    """改进的论文标题提取函数"""  
    try:  
        with open(pdf_path, 'rb') as file:  
            reader = PyPDF2.PdfReader(file)  
            if len(reader.pages) == 0:  
                return os.path.splitext(os.path.basename(pdf_path))[0]  
            
            # 提取前两页文本，因为标题可能跨页  
            text_pages = []  
            for i in range(min(2, len(reader.pages))):  
                page_text = reader.pages[i].extract_text()  
                if page_text:  
                    text_pages.append(page_text)  
            
            if not text_pages:  
                return os.path.splitext(os.path.basename(pdf_path))[0]  
            
            full_text = ' '.join(text_pages)  
            
            # 清理文本，移除多余空格和换行  
            cleaned_text = re.sub(r'\s+', ' ', full_text.strip())  
            
            # 尝试多种标题提取方法  
            title_candidates = []  
            
            # 方法1：寻找大写字母开头的长句子（通常是标题）  
            sentences = re.split(r'[.!?]\s+', cleaned_text[:2000])  # 只看前2000字符  
            for sentence in sentences[:10]:  # 只看前10个句子  
                sentence = sentence.strip()  
                if (len(sentence) > 15 and len(sentence) < 200 and   
                    sentence[0].isupper() and   
                    not sentence.lower().startswith(('abstract', 'introduction', 'figure', 'table'))):  
                    title_candidates.append(sentence)  
            
            # 方法2：寻找第一行的长文本  
            lines = cleaned_text.split('\n')[:20]  # 前20行  
            for line in lines:  
                line = line.strip()  
                if (len(line) > 20 and len(line) < 200 and  
                    not re.match(r'^\d+', line) and  # 不以数字开头  
                    not line.lower().startswith(('abstract', 'introduction', 'keywords'))):  
                    title_candidates.append(line)  
            
            # 选择最佳标题候选  
            if title_candidates:  
                # 优先选择长度适中的标题  
                title_candidates.sort(key=lambda x: abs(len(x) - 80))  # 理想长度80字符  
                
                # 进一步过滤  
                for candidate in title_candidates:  
                    candidate = candidate.strip()  
                    # 确保不是页眉页脚或其他无关内容  
                    if (not re.search(r'\b(?:page|pp|vol|volume|journal|conference|proceedings)\b', candidate.lower()) and  
                        not re.match(r'.*\d{4}.*', candidate) and  # 不包含年份  
                        candidate.count(' ') >= 2):  # 至少3个词  
                        return candidate  
                
                # 如果所有候选都被过滤，返回第一个  
                return title_candidates[0].strip()  
        
        # 如果都失败了，使用文件名  
        return os.path.splitext(os.path.basename(pdf_path))[0]  
        
    except Exception as e:  
        logger.warning(f"提取论文标题失败: {str(e)}")  
        return os.path.splitext(os.path.basename(pdf_path))[0]  

def extract_dataset_name_from_context(url: str, context: str) -> str:  
    """改进的数据集名称提取函数"""  
    try:  
        context_lower = context.lower()  
        
        # 先尝试从上下文中提取，即使是通用页面  
        dataset_patterns = [  
            # 引号中的内容（最可靠）  
            r'"([A-Za-z][A-Za-z0-9\-_\s]{2,30})"',  
            r"'([A-Za-z][A-Za-z0-9\-_\s]{2,30})'",  
            
            # 大写开头的专有名词  
            r'\b([A-Z][a-z]+(?:[A-Z][a-z]*)*)\s+(?:dataset|benchmark|corpus|data)',  
            r'(?:dataset|benchmark|corpus|data)\s+([A-Z][A-Za-z0-9\-_]{2,20})',  
            
            # 常见数据集命名模式  
            r'\b([A-Z]{2,}(?:-[A-Z0-9]+)*)\b',  # 全大写缩写  
            r'\b([A-Za-z]+Eval|[A-Za-z]+QA|[A-Za-z]+NLI)\b',  # 常见后缀  
        ]  
        
        candidates = set()  
        
        # 从上下文中提取候选名称  
        for pattern in dataset_patterns:  
            matches = re.findall(pattern, context, re.IGNORECASE)  
            for match in matches:  
                candidate = match.strip()  
                if (len(candidate) > 2 and   
                    candidate.lower() not in ['the', 'and', 'for', 'with', 'data', 'test', 'train', 'dataset', 'benchmark', 'corpus']):  
                    candidates.add(candidate)  
        
        # 从URL中提取候选名称  
        if 'github.com' in url:  
            parts = url.split('/')  
            if len(parts) >= 5:  
                repo_name = parts[4]  
                if repo_name not in ['main', 'master', 'blob', 'tree', 'datasets']:  
                    candidates.add(repo_name.replace('-', ' ').replace('_', ' ').title())  
        
        elif 'huggingface.co/datasets' in url:  
            parts = url.split('/')  
            if len(parts) >= 5:  
                dataset_name = parts[4]  
                candidates.add(dataset_name.replace('-', ' ').replace('_', ' ').title())  
        
        elif 'paperswithcode.com' in url:  
            # 对于Papers with Code，尝试提取更具体的信息  
            if 'dataset/' in url:  
                parts = url.split('dataset/')  
                if len(parts) > 1:  
                    dataset_name = parts[1].split('/')[0]  
                    candidates.add(dataset_name.replace('-', ' ').replace('_', ' ').title())  
        
        # 如果还是没有找到好的候选，基于上下文生成名称  
        if not candidates:  
            if 'nlp' in context_lower or 'natural language' in context_lower:  
                candidates.add("NLP Dataset")  
            elif 'vision' in context_lower or 'image' in context_lower:  
                candidates.add("Vision Dataset")  
            elif 'benchmark' in context_lower:  
                candidates.add("Benchmark Dataset")  
            else:  
                # 使用URL的域名  
                parsed_url = urlparse(url)  
                domain = parsed_url.netloc.replace('www.', '')  
                if 'paperswithcode' in domain:  
                    candidates.add("Papers with Code Dataset")  
                elif 'github' in domain:  
                    candidates.add("GitHub Repository")  
                elif 'huggingface' in domain:  
                    candidates.add("Hugging Face Dataset")  
                else:  
                    candidates.add("Research Dataset")  
        
        # 选择最佳候选  
        if candidates:  
            # 优先选择较短但不太短的名称  
            sorted_candidates = sorted(candidates, key=lambda x: (len(x) < 5, len(x)))  
            return sorted_candidates[0]  
        
        return "Research Dataset"  # 确保总是返回非空字符串  
        
    except Exception as e:  
        logger.warning(f"提取数据集名称失败: {str(e)}")  
        return "Research Dataset"  

def extract_paper_title_from_pdf(pdf_path: str) -> str:  
    """改进的论文标题提取函数"""  
    try:  
        with open(pdf_path, 'rb') as file:  
            reader = PyPDF2.PdfReader(file)  
            if len(reader.pages) == 0:  
                return os.path.splitext(os.path.basename(pdf_path))[0]  
            
            # 只提取第一页文本（标题通常在第一页）  
            first_page_text = reader.pages[0].extract_text()  
            if not first_page_text:  
                return os.path.splitext(os.path.basename(pdf_path))[0]  
            
            # 清理文本，移除多余空格和换行  
            cleaned_text = re.sub(r'\s+', ' ', first_page_text.strip())  
            
            # 按行分割，查找标题  
            lines = first_page_text.split('\n')  
            
            # 过滤掉明显的页眉页脚和无关内容  
            filtered_lines = []  
            for line in lines:  
                line = line.strip()  
                if (line and   
                    len(line) > 10 and   
                    not re.match(r'^\d+$', line) and  # 不是纯数字  
                    not line.lower().startswith(('page', 'pp.', 'vol.', 'arxiv:', 'doi:', 'http', 'www.')) and  
                    not re.search(r'\d{4}', line) and  # 不包含年份  
                    not line.lower() in ['abstract', 'introduction', 'keywords', 'references']):  
                    filtered_lines.append(line)  
            
            # 寻找最可能的标题  
            title_candidates = []  
            
            for i, line in enumerate(filtered_lines[:10]):  # 只看前10行  
                line = line.strip()  
                
                # 标题的特征：  
                # 1. 长度适中 (15-200字符)  
                # 2. 包含多个词  
                # 3. 不是纯大写（除非是缩写）  
                # 4. 位置靠前  
                
                if (15 <= len(line) <= 200 and   
                    line.count(' ') >= 2 and  # 至少3个词  
                    not line.isupper() and  # 不是全大写  
                    line[0].isupper()):  # 首字母大写  
                    
                    # 给位置靠前的行更高权重  
                    weight = 10 - i  
                    title_candidates.append((line, weight))  
            
            if title_candidates:  
                # 按权重排序，选择最佳候选  
                title_candidates.sort(key=lambda x: x[1], reverse=True)  
                best_title = title_candidates[0][0]  
                
                # 进一步清理标题  
                best_title = re.sub(r'\s+', ' ', best_title).strip()  
                
                # 去掉前面的数字（按用户要求）  
                best_title = re.sub(r'^\d+\.?\s*', '', best_title)  
                
                return best_title  
        
        # 如果都失败了，使用文件名（去掉.pdf扩展名）  
        filename = os.path.splitext(os.path.basename(pdf_path))[0]  
        # 去掉文件名前面的数字  
        filename = re.sub(r'^\d+[-_\s]*', '', filename)  
        return filename  
        
    except Exception as e:  
        logger.warning(f"提取论文标题失败: {str(e)}")  
        filename = os.path.splitext(os.path.basename(pdf_path))[0]  
        # 去掉文件名前面的数字  
        filename = re.sub(r'^\d+[-_\s]*', '', filename)  
        return filename

def extract_dataset_description(url: str, contexts: List[str]) -> str:  
    """使用上下文作为数据集描述"""  
    try:  
        if not contexts:  
            return "数据集或基准测试"  
        
        # 合并所有上下文，去重  
        unique_contexts = []  
        seen = set()  
        for context in contexts:  
            context_clean = re.sub(r'\s+', ' ', context.strip())  
            if context_clean and context_clean not in seen:  
                unique_contexts.append(context_clean)  
                seen.add(context_clean)  
        
        if not unique_contexts:  
            return "数据集或基准测试"  
        
        # 如果有多个上下文，用分号分隔  
        if len(unique_contexts) == 1:  
            description = unique_contexts[0]  
        else:  
            description = '; '.join(unique_contexts)  
        
        # 限制长度，避免描述过长  
        if len(description) > 500:  
            description = description[:500] + "..."  
        
        return description  
            
    except Exception as e:  
        logger.warning(f"提取数据集描述失败: {str(e)}")  
        return "数据集或基准测试"

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

def extract_benchmark_links_from_paper(pdf_path: str) -> Dict[str, List[str]]:  
    """从本地PDF文件中提取数据集和基准测试相关链接，过滤通用页面"""  
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
        
        print(f"[!] len(r1) = {len(all_urls_from_pdf_find)}, len(r2) = {len(additional_urls)}")  
        
        # 筛选数据集和基准测试相关链接，暂时不过滤通用页面（降低严格程度）  
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
                    
                    print(f"    找到数据集: {dataset_name}")  
                
                if paper_datasets:  # 只有找到有效数据集才添加论文  
                    results[paper_title] = paper_datasets  
                    print(f"  总共找到 {len(paper_datasets)} 个数据集")  
                else:  
                    print("  过滤后未找到有效数据集")  
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
                
                print(f"找到数据集: {dataset_name}")  
            
            if paper_datasets:  
                results[paper_title] = paper_datasets  
                print(f"总共找到 {len(paper_datasets)} 个数据集")  
            else:  
                print("过滤后未找到有效数据集")  
        else:  
            print("未找到数据集/基准测试链接")  
        
        # 保存结果  
        save_json(output_file, results)  
        print("处理完成")  
        
    except Exception as e:  
        print(f"处理失败: {str(e)}")  
        save_json(output_file, {})  

def main():  
    """主函数"""  
    parser = argparse.ArgumentParser(description='从PDF文件或目录提取数据集和基准测试链接')  
    
    # 创建互斥组  
    source_group = parser.add_mutually_exclusive_group(required=True)  
    source_group.add_argument('--pdf', type=str, help='单个PDF文件路径')  
    source_group.add_argument('--pdf-dir', type=str, help='包含PDF文件的目录路径')  
    
    parser.add_argument('-o', '--output', type=str, required=True, help='输出JSON文件路径')  
    parser.add_argument('-l', '--limit', type=int, help='限制处理的文件数量')  
    parser.add_argument('--use-llm', action='store_true', help='是否使用LLM辅助判断')  
    parser.add_argument('--openai-key', type=str, help='收费API密钥')  
    parser.add_argument('--use-free', action='store_true', help='使用免费校园网API')  
    
    args = parser.parse_args()  
    
    # 检查是否启用LLM  
    if args.use_llm:  
        if setup_llm(args.openai_key, args.use_free):  
            if args.use_free:  
                print("使用免费校园网API已启用")  
            else:  
                print("使用收费API已启用")  
        else:  
            print("LLM设置失败，将仅使用规则方法")  
    
    # 处理逻辑  
    if args.pdf:  
        process_single_pdf(args.pdf, args.output)  
    elif args.pdf_dir:  
        process_pdf_directory(args.pdf_dir, args.output, args.limit)  

if __name__ == "__main__":  
    main()