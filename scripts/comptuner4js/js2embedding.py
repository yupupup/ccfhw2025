import torch
import torch.nn.functional as F
import numpy as np
from transformers import AutoTokenizer, AutoModel

class JSEmbedding:
    def __init__(self, model_name="Qwen/Qwen3-Embedding-8B", embedding_dim=64):
        """
        初始化JSEmbedding类，加载Qwen3-Embedding-8B模型和分词器，并设置一个线性投影层。
        """
        print(f"正在加载 {model_name}...")
        # 加载模型和分词器，trust_remote_code=True是必要的，因为它会执行模型仓库中的自定义代码
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
        self.device = torch.device("cuda")
        self.model.to(self.device)
        
        # Qwen3-Embedding-8B的原始维度是4096
        original_dim = 4096
        self.projection = torch.nn.Linear(original_dim, embedding_dim)
        self.projection.to(self.device)
        
        self.model.eval()
        self.projection.eval()  # 将投影层也设置为评估模式
        print(f"模型已加载到 {self.device}")
        self.embedding_dim = embedding_dim

    def get_embedding(self, code_string: str) -> np.ndarray:
        """
        为输入的JS代码字符串生成指定维度的嵌入向量。

        Args:
            code_string: 要编码的JavaScript代码。

        Returns:
            一个形状为 (self.embedding_dim,) 的NumPy数组。
        """
        # 对输入代码进行分词
        inputs = self.tokenizer(code_string, padding=True, truncation=True, max_length=512, return_tensors="pt").to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)

        # 改用最后一个有效 Token 的嵌入（Last Token Pooling）
        # 或者是 Mean Pooling，取决于你的任务。
        # 下面是简单的 Last Token 提取（假设没有 Padding 或 Batch Size 为 1）
        last_token_embedding = outputs.last_hidden_state[:, -1]

        # 转换为 float32 进行降维投影
        projected_embedding = self.projection(last_token_embedding.float())

        # 对投影后的向量进行L2归一化
        normalized_embedding = F.normalize(projected_embedding, p=2, dim=1)

        # 返回 numpy 数组
        #return projected_embedding.detach().cpu().numpy().flatten()
        return normalized_embedding.detach().flatten()

'''
if __name__ == '__main__':
    # 用于快速测试的示例代码
    js_code = """
    function calculateSum(a, b) {
        if (a < 0 || b < 0) {
            console.error("Invalid input");
            return 0;
        }
        return a + b;
    }
    """
    print("正在初始化 JSEmbedding 工具...")
    # 初始化JSEmbedding，指定嵌入维度为128
    embedder = JSEmbedding(embedding_dim=128)
    
    print("\n正在为示例JS代码生成嵌入向量...")
    embedding_vector = embedder.get_embedding(js_code)
    
    print("\n=== 提取结果 ===")
    print(f"最终 Embedding 向量形状: {embedding_vector.shape}")
    print(f"Embedding 前 5 个维度的数值:\n{embedding_vector[:5]}")
'''