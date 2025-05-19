import argparse  
import json  
import os  
from typing import Dict, List  
from combine import extract_benchmark_links_from_paper, setup_llm, save_json  

def process_local_pdf(pdf_path: str, output_file: str, use_llm: bool = False, api_key: str = None) -> None:  
    """处理本地PDF文件，提取数据集和基准测试链接  
    
    Args:  
        pdf_path: 本地PDF文件路径  
        output_file: 输出JSON文件路径  
        use_llm: 是否使用LLM辅助判断  
        api_key: OpenAI API密钥  
    """  
    if not os.path.exists(pdf_path):  
        print(f"错误: 文件 {pdf_path} 不存在")  
        return  
    
    print(f"开始处理本地PDF: {pdf_path}")  
    
    # 如果启用LLM，进行设置  
    if use_llm:  
        if setup_llm(api_key):  
            print("使用LLM辅助判断已启用")  
        else:  
            print("LLM设置失败，将仅使用规则方法")  
    
    # 提取PDF中的基准测试链接  
    # 注意：这里需要修改extract_benchmark_links_from_paper函数来处理本地文件  
    benchmark_links = extract_benchmark_links_from_local_pdf(pdf_path)  
    
    if benchmark_links:  
        # 为每个链接创建记录  
        all_benchmarks = []  
        for url, contexts in benchmark_links.items():  
            all_benchmarks.append({  
                "url": url,  
                "pdf_path": pdf_path,  
                "contexts": contexts  
            })  
        
        print(f"找到 {len(benchmark_links)} 个数据集/基准测试链接")  
        
        # 保存结果  
        save_json(output_file, all_benchmarks)  
    else:  
        print("未找到数据集/基准测试链接")  
        save_json(output_file, [])  

def extract_benchmark_links_from_local_pdf(pdf_path: str) -> Dict[str, List[str]]:  
    """从本地PDF文件提取数据集和基准测试相关链接"""  
    # 这个函数需要修改原来的extract_benchmark_links_from_paper函数  
    # 让它支持本地文件而不是URL  
    import PyPDF2  
    import io  
    from combine import extract_urls_from_text, is_benchmark_or_dataset_link  
    
    try:  
        # 打开本地PDF文件  
        with open(pdf_path, 'rb') as file:  
            reader = PyPDF2.PdfReader(file)  
            
            text = ""  
            for page_num in range(len(reader.pages)):  
                page_text = reader.pages[page_num].extract_text()  
                if page_text:  
                    text += page_text + "\n"  
        
        if not text:  
            print(f"警告: 无法从PDF提取文本: {pdf_path}")  
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
        
    except Exception as e:  
        print(f"处理PDF失败: {str(e)}")  
        return {}  

def main():  
    """主函数，处理命令行参数"""  
    parser = argparse.ArgumentParser(description='从本地PDF文件提取数据集和基准测试链接')  
    parser.add_argument('pdf_path', type=str, help='本地PDF文件路径')  
    parser.add_argument('-o', '--output', type=str, required=True, help='输出JSON文件路径')  
    parser.add_argument('--use-llm', action='store_true', help='是否使用LLM辅助判断，需要OpenAI API密钥')  
    parser.add_argument('--openai-key', type=str, help='OpenAI API密钥')  
    
    args = parser.parse_args()  
    
    # 处理本地PDF  
    process_local_pdf(args.pdf_path, args.output, args.use_llm, args.openai_key)  

if __name__ == "__main__":  
    main()