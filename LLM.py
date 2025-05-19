import os  
from typing import Optional, List  
import re  
import time  # 添加time模块用于延迟  
from langchain_openai import OpenAI  
# from langchain.prompts import PromptTemplate  
from langchain.chains.llm import LLMChain  

# 或者使用新的RunnableSequence方式（推荐）  
from langchain_core.prompts import PromptTemplate  
from langchain_openai import OpenAI  
import requests  
from bs4 import BeautifulSoup  
import logging  
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type  # 添加重试机制  

# 设置日志  
logging.basicConfig(level=logging.INFO)  
logger = logging.getLogger(__name__)  

# 设置 OpenAI API 密钥  
os.environ["OPENAI_API_KEY"] = "sk-x"  # 替换为你的 API 密钥  

# 初始化 LLM 并添加超时设置  
llm = OpenAI(temperature=0.1, request_timeout=30, max_retries=2)  

# 创建提示模板  
prompt_link = PromptTemplate(input_variables=["url", "context_text"], template="""  
    请分析以下文本中的链接 {url}，判断它是否指向一个可直接下载或访问的 Benchmark 或 Dataset。  

    链接上下文: {context_text}  

    判断标准:  
    1. 链接应该直接指向数据集下载页面或包含数据集的仓库  
    2. 不是框架官网（如PyTorch、TensorFlow）、项目主页、博客或一般介绍页面  
    3. 链接目标应该是可用于机器学习/数据挖掘任务的基准测试或数据集  
    4. 链接应该指向实际存在的资源，不是占位符或示例URL  

    请仔细分析后回答 'YES' 或 'NO'，并简要说明理由。  
    """  )  

# 创建 LLM Chain  
llm_chain = LLMChain(llm=llm, prompt=prompt_link)  

# 添加速率限制变量  
RATE_LIMIT_DELAY = 3  # 每次API调用之间等待的秒数  
LAST_API_CALL_TIME = 0  # 上次API调用的时间戳  

def can_access(url: str) -> bool:  
    """  
    检查 URL 是否形式上有效  
    """  
    # 原有代码保持不变  
    url = url.strip()  
    
    if url.endswith('-'):  
        return False  
    
    res = re.findall(r'https?://', url)  
    if len(res) > 1:  
        return False  
    
    if not re.match(r'^https?://[^\s/$.?#].[^\s]*$', url):  
        return False  
    
    return True  

def verify_dataset_candidate(url: str, description: str) -> bool:  
    """二次验证疑似数据集链接"""  
    # 排除已知的框架网站  
    framework_sites = ["pytorch.org", "tensorflow.org", "keras.io"]  
    if any(site in url.lower() for site in framework_sites):  
        return False  
        
    # 排除示例/占位符URL  
    if "username" in url.lower() or "example" in url.lower():  
        return False  
        
    # 返回原始分类结果  
    return True  

def extract_page_content(url: str) -> Optional[str]:  
    """  
    尝试获取链接内容  
    """  
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

# 添加重试装饰器  
@retry(  
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),  
    wait=wait_exponential(multiplier=1, min=2, max=20),  
    stop=stop_after_attempt(3)  
)  
def call_llm_with_retry(prompt, **kwargs):  # prompt 不能改成 chain，不然写的二次调用没用
    """使用重试机制调用LLM"""  
    global LAST_API_CALL_TIME  
    
    # 实现速率限制  
    current_time = time.time()  
    time_since_last_call = current_time - LAST_API_CALL_TIME  
    
    if time_since_last_call < RATE_LIMIT_DELAY:  
        sleep_time = RATE_LIMIT_DELAY - time_since_last_call  
        logger.info(f"Rate limiting: Waiting {sleep_time:.2f} seconds before next API call")  
        time.sleep(sleep_time)  
    
    # 更新上次调用时间  
    LAST_API_CALL_TIME = time.time()  
    
    # 设置超时，如果30秒内没有响应则抛出异常  
    try:  
        # 使用新的invoke方法  
        chain = prompt | llm  
        result = chain.invoke(kwargs)  
        model_info = llm.model_name if hasattr(llm, 'model_name') else "Unknown model"  
        logger.info(f"API call successful using model: {model_info}")  
        # logger.info("API call successful")  
        return result  
    except Exception as e:  
        logger.error(f"API call failed: {str(e)}")  
        raise e  

def is_benchmark_or_dataset_link(url: str, context_text: str, verify_content: bool = False) -> bool:  
    """  
    使用 LLM 判断链接是否为 Benchmark/Dataset 链接  
    """  
    # 先检查 URL 形式是否有效  
    if not can_access(url):  
        return False  
    
    # 使用 LLM 分析链接及其上下文  
    try:  
        # 使用带重试和速率限制的API调用  
        logger.info(f"Analyzing link: {url}")  
        response = call_llm_with_retry(prompt_link, url=url, context_text=context_text)  
        
        initial_result = 'YES' in response.upper()  
        
        logger.info(f"Initial classification for {url}: {initial_result}")  
        
        # 如果需要进一步验证且初步判断为 Benchmark/Dataset  
        if verify_content and initial_result:  
            page_content = extract_page_content(url)  
            
            if page_content:  
                # 创建内容验证的提示模板  
                content_verification_template = PromptTemplate(  
                    input_variables=["url", "page_content"],  
                    template="""  
                    请分析以下链接 {url} 的内容，判断它是否为 Benchmark 或 Dataset 资源页面。  
                    
                    页面内容摘要: {page_content}  
                    
                    判断标准:  
                    1. 页面应该包含数据集下载信息、代码仓库、或基准测试相关资源  
                    2. 不是纯粹的博客文章、新闻、或一般的项目主页  
                    
                    请回答 'YES' 或 'NO'，并简要说明理由。  
                    """  
                )  
                
                content_verification_chain = LLMChain(llm=llm, prompt=content_verification_template)  
                # 同样使用带重试和速率限制的API调用  
                content_response = call_llm_with_retry(  
                    content_verification_chain,   
                    url=url,   
                    page_content=page_content  
                )  
                
                final_result = 'YES' in content_response.upper()  
                logger.info(f"Content verification for {url}: {final_result}")  
                
                return final_result  
        
        return initial_result  
    
    except Exception as e:  
        logger.error(f"Error in LLM processing for {url}: {str(e)}")  
        # 如果API调用失败，返回False而不是继续尝试  
        return False  

def process_paper_links(paper_text: str, window_size: int = 200) -> List[str]:  
    """  
    处理论文文本，提取并验证所有潜在的 Benchmark/Dataset 链接  
    """  
    # 使用正则表达式提取所有 URL  
    url_pattern = r'https?://[^\s)>"}\']*'  
    matches = list(re.finditer(url_pattern, paper_text))  
    total_urls = len(matches)  
    
    logger.info(f"Found {total_urls} URLs to analyze")  
    benchmark_dataset_links = []  
    
    for i, match in enumerate(matches):  
        url = match.group(0)  
        logger.info(f"Processing URL {i+1}/{total_urls}: {url}")  
        
        # 获取链接周围的上下文  
        start_pos = max(0, match.start() - window_size // 2)  
        end_pos = min(len(paper_text), match.end() + window_size // 2)  
        context = paper_text[start_pos:end_pos]  
        
        # 判断链接是否为 Benchmark/Dataset  
        if is_benchmark_or_dataset_link(url, context):  
            if verify_dataset_candidate(url, context):  
                benchmark_dataset_links.append(url)  
                logger.info(f"Found Benchmark/Dataset link: {url}")  
            else:  
                logger.info(f"Link initially classified as dataset but rejected in verification: {url}")  
    
    return benchmark_dataset_links  

# 使用示例  
if __name__ == "__main__":  
    # 示例论文文本（这里只是一个简化示例）  
    sample_paper_text = """  
    We evaluated our method on the CIFAR-10 dataset (https://www.cs.toronto.edu/~kriz/cifar.html)  
    which is widely used for image classification tasks. Additionally, we compared our results with  
    the state-of-the-art methods using the ImageNet dataset (http://image-net.org/download).  
    
    Our implementation is available on GitHub (https://github.com/username/project) and uses  
    the PyTorch framework (https://pytorch.org).  
    
    For text classification experiments, we used the AG News dataset   
    (https://github.com/mhjabreel/CharCnn_Keras/tree/master/data/ag_news_csv).  
    """  
    
    # 处理论文中的链接  
    benchmark_links = process_paper_links(sample_paper_text)  
    
    print("Identified Benchmark/Dataset links:")  
    for link in benchmark_links:  
        print(f"- {link}")