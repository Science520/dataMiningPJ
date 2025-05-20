import os  
import logging  
from typing import Optional, List  
import re  
import json  
from openai import OpenAI  

logging.basicConfig(level=logging.INFO)  
logger = logging.getLogger(__name__)  

# 创建 OpenAI 客户端  
client = OpenAI(  
    api_key="sk-x",  # 你的 API 密钥  
    base_url="https://ai.nengyongai.cn/v1"  # 使用 nengyongai.cn 的 API 端点  
)  

def can_access(url: str) -> bool:  
    """  
    检查 URL 是否形式上有效  
    
    Args:  
        url: 要检查的 URL  
    
    Returns:  
        bool: URL 是否有效  
    """  
    # 去除首尾空白字符  
    url = url.strip()  
    
    # 排除以 '-' 结尾的 URL  
    if url.endswith('-'):  
        return False  
    
    # 排除包含多个 http:// 或 https:// 的 URL  
    res = re.findall(r'https?://', url)  
    if len(res) > 1:  
        return False  
    
    # 检查 URL 是否有基本的有效格式  
    if not re.match(r'^https?://[^\s/$.?#].[^\s]*$', url):  
        return False  
    
    return True  

def is_benchmark_or_dataset_link(url: str, context_text: str) -> bool:  
    """  
    使用 o1-mini 模型判断链接是否为 Benchmark/Dataset 链接  
    
    Args:  
        url: 链接地址  
        context_text: 链接周围的上下文文本  
    
    Returns:  
        bool: 是否为 Benchmark/Dataset 链接  
    """  
    # 先检查 URL 形式是否有效  
    if not can_access(url):  
        return False  
    
    try:  
        # 构建提示  
        messages = [  
            {"role": "system", "content": "你是一个专业的链接分析助手，帮助识别机器学习/数据挖掘中的基准测试和数据集链接。"},  
            {"role": "user", "content": f"""  
            请分析以下文本中的链接，判断它是否指向一个可直接下载或访问的 Benchmark 或 Dataset。  
            
            链接: {url}  
            链接上下文: {context_text}  
            
            判断标准:  
            1. 链接应该直接指向下载页或官方仓库（如GitHub）  
            2. 不是项目主页、博客或一般介绍页面  
            3. 链接目标应该是可用于机器学习/数据挖掘任务的基准测试或数据集  
            
            请仔细思考后直接回答 'YES' 或 'NO'，并简要说明理由。  
            """}  
        ]  
        
        # 调用模型 - 注意这里使用的是 o1-mini，但实际上可能需要使用 nengyongai.cn 支持的模型  
        response = client.chat.completions.create(  
            model="gpt-4",  # 使用示例中确认支持的模型  
            messages=messages,  
            temperature=0.1  
        )
        
        # 获取回复文本  
        response_text = response.choices[0].message.content  
        
        # 判断是否为 Benchmark/Dataset 链接  
        is_benchmark = "YES" in response_text.upper()  
        
        # 记录结果  
        logger.info(f"Classification for {url}: {is_benchmark}")  
        logger.info(f"Response: {response_text}")  
        
        return is_benchmark  
    
    except Exception as e:  
        logger.error(f"Error in model processing for {url}: {str(e)}")  
        return False  

def process_paper_links(paper_text: str, window_size: int = 200) -> List[str]:  
    """  
    处理论文文本，提取并验证所有潜在的 Benchmark/Dataset 链接  
    
    Args:  
        paper_text: 论文文本内容  
        window_size: 链接上下文窗口大小（字符数）  
    
    Returns:  
        List[str]: 验证为 Benchmark/Dataset 的链接列表  
    """  
    # 使用正则表达式提取所有 URL  
    url_pattern = r'https?://[^\s)>"}\']*'  
    matches = re.finditer(url_pattern, paper_text)  
    
    benchmark_dataset_links = []  
    
    for match in matches:  
        url = match.group(0)  
        
        # 获取链接周围的上下文  
        start_pos = max(0, match.start() - window_size // 2)  
        end_pos = min(len(paper_text), match.end() + window_size // 2)  
        context = paper_text[start_pos:end_pos]  
        
        # 判断链接是否为 Benchmark/Dataset  
        if is_benchmark_or_dataset_link(url, context):  
            benchmark_dataset_links.append(url)  
            logger.info(f"Found Benchmark/Dataset link: {url}")  
    
    return benchmark_dataset_links  

# 使用示例  
if __name__ == "__main__":  
    # 示例论文文本  
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